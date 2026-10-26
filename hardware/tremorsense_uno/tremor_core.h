// TremorSense tremor engine for the Arduino Uno (ATmega328P, 2 KB RAM).
//
// Plain C++ with no Arduino calls, so the same file is compiled for the Uno
// and for the host tests in hardware/test/.
//
// Per sample (50 Hz):
//   - remove gravity with a slow running mean per axis,
//   - update Goertzel filters at 0.5 Hz steps from 0.5 to 12 Hz on all three
//     axes (Hann window, 2 s blocks),
//   - run a band-pass at the tracked tremor frequency on the dominant axis and
//     time cues one actuator latency ahead of the next upward zero crossing.
// Per block (every 2 s):
//   - sum power over the three axes (orientation invariant),
//   - find the tremor peak in 3-12 Hz with sub-bin interpolation,
//   - turn band power into peak-to-peak hand displacement with the same physics
//     as the app, d = 2 * sqrt(2 P) / (2 pi f)^2, and map it to the UPDRS bands,
//   - pause cueing while the hand is moving (low-frequency power dominates),
//   - debounce: cue only when 2 of the last 3 blocks agree, at the weaker grade.
#pragma once
#include <math.h>
#include <stdint.h>

namespace ts {

const float FS = 50.0f;
const int N = 100;                  // block length: 2 s, 0.5 Hz bins
const int K_MIN = 1, K_MAX = 24;    // 0.5 .. 12 Hz
const int K_TREMOR_MIN = 6;         // 3 Hz
const int K_LOW_MAX = 5;            // 0.5 .. 2.5 Hz is voluntary movement / gait
const int NK = K_MAX - K_MIN + 1;
const int NLOW = K_LOW_MAX - K_MIN + 1;

// ADXL335 on a GY-61 board: about 0.33 V per g; Uno ADC: 5 V / 1023 counts.
const float G_PER_COUNT = (5.0f / 1023.0f) / 0.33f;
const float ZERO_G_COUNTS = 1.65f / 5.0f * 1023.0f;   // ~338
const float MS2_PER_COUNT = 9.81f * G_PER_COUNT;

// UPDRS 3.17 / 3.18 amplitude bands, peak-to-peak cm.
const float BAND_CM[4] = {0.15f, 1.0f, 3.0f, 10.0f};  // below 0.15 cm = noise floor

struct Result {
  uint8_t grade;        // 0..4
  float freq_hz;        // tremor peak
  float disp_cm;        // peak-to-peak displacement
  bool moving;          // voluntary movement or walking: grade not used
  uint8_t cue;          // 0 = off, else gated intensity 2..4
};

class Engine {
 public:
  float latency_s = 0.04f;    // motor spin-up time
  float min_prominence = 0.25f;
  float move_var = 0.5f;      // (m/s^2)^2 below 3 Hz, about 0.7 m/s^2 RMS
  float move_ratio = 0.5f;    // per-axis movement must also rival the tremor

  Engine() { reset(); }

  void reset() {
    n_ = 0;
    primed_ = 0;
    warm_ = 0;
    for (int a = 0; a < 3; a++) mean_[a] = NAN;
    mean_mag_ = NAN;
    for (int i = 0; i < 3; i++)
      for (int j = 0; j < 2; j++) lp_[i][j][0] = lp_[i][j][1] = lp_[i][j][2] = lp_[i][j][3] = NAN;
    clear_block();
    for (int i = 0; i < 3; i++) hist_[i] = 0;
    res_ = {0, 0, 0, false, 0};
    f_track_ = 5.0f;
    axis_ = 2;
    design_bandpass(f_track_);
    t_ = 0;
    last_cross_ = -1;
    next_fire_ = -1;
    last_fire_ = -1;
    prev_y_ = 0;
  }

  // Feed one sample of raw ADC counts. Returns true when a block finished
  // (a new Result is ready).
  bool push(int cx, int cy, int cz) {
    float c[3] = {(float)cx, (float)cy, (float)cz};
    float a[3];
    // ~1 s time constant: follows posture changes, leaves 3-12 Hz intact.
    // Over the first second a plain average, so the start-up transient
    // isn't taken for movement.
    if (warm_ < 50) warm_++;
    float k = warm_ < 50 ? 1.0f / warm_ : 0.02f;
    for (int i = 0; i < 3; i++) {
      if (isnan(mean_[i])) mean_[i] = c[i];
      mean_[i] += k * (c[i] - mean_[i]);
      a[i] = (c[i] - mean_[i]) * MS2_PER_COUNT;
    }
    // Size of the slow part (< 2.5 Hz) of the total acceleration, gravity
    // included. Tilting the hand only turns gravity, so it leaves this almost
    // unchanged; walking and moving the arm change it. Low-passing first
    // keeps the tremor itself out of it.
    float mag2 = 0;
    for (int i = 0; i < 3; i++) {
      float v = lowpass(i, (c[i] - ZERO_G_COUNTS) * MS2_PER_COUNT);
      mag2 += v * v;
    }
    float mag = sqrtf(mag2);
    if (isnan(mean_mag_)) mean_mag_ = mag;
    mean_mag_ += k * (mag - mean_mag_);
    float m = mag - mean_mag_;

    t_ += 1.0f / FS;
    track_phase(a[axis_]);

    float w = 0.5f - 0.5f * cosf(2.0f * (float)M_PI * n_ / (N - 1));
    for (int k = 0; k < NK; k++) {
      for (int i = 0; i < 3; i++) {
        float s = a[i] * w + coef_[k] * s1_[k][i] - s2_[k][i];
        s2_[k][i] = s1_[k][i];
        s1_[k][i] = s;
      }
    }
    for (int k = 0; k < NLOW; k++) {
      float s = m * w + coef_[k] * ms1_[k] - ms2_[k];
      ms2_[k] = ms1_[k];
      ms1_[k] = s;
    }
    if (++n_ < N) return false;
    finish_block();
    clear_block();
    return true;
  }

  // Seconds (engine clock) at which to start the next motor pulse, or < 0.
  // Call after each push(); fires at most once per tremor cycle.
  bool should_fire() {
    if (res_.cue == 0 || next_fire_ < 0) return false;
    if (t_ + 0.5f / FS >= next_fire_) {
      last_fire_ = next_fire_;
      next_fire_ = -1;
      return true;
    }
    return false;
  }

  // Pulse length in ms: a third of a cycle at most, longer for stronger cues.
  uint16_t pulse_ms() const {
    float third = 1000.0f / (3.0f * fmaxf(res_.freq_hz, 3.0f));
    float want = res_.cue == 4 ? 45.0f : res_.cue == 3 ? 30.0f : 18.0f;
    return (uint16_t)fminf(want, third);
  }

  // PWM duty for the motor, 0..255, by gated intensity.
  uint8_t pulse_duty() const {
    return res_.cue == 4 ? 255 : res_.cue == 3 ? 210 : res_.cue == 2 ? 160 : 0;
  }

  const Result& result() const { return res_; }
  // Last block's inputs to the decision, for the serial log.
  float diag_low() const { return diag_low_; }
  float diag_tremor() const { return diag_tremor_; }
  float diag_prominence() const { return diag_prominence_; }
  // Band-passed tremor on the dominant axis (m/s^2), the signal the cues lock to.
  float phase_signal() const { return y1_; }
  float clock() const { return t_; }

 private:
  // Block state: Goertzel s1, s2 per bin and axis.
  float s1_[NK][3], s2_[NK][3];
  float coef_[NK];
  float mean_[3];
  float mean_mag_;
  float ms1_[NLOW], ms2_[NLOW];   // Goertzel state for the magnitude, low bins
  float lp_[3][2][4];             // two cascaded low-pass biquads per axis: x1 x2 y1 y2

  // Butterworth low-pass at 2.5 Hz (fs 50 Hz), applied twice (4th order).
  float lowpass(int axis, float x) {
    const float b0 = 0.020083f, b1 = 0.040167f, b2 = 0.020083f, a1 = -1.561018f, a2 = 0.641352f;
    for (int j = 0; j < 2; j++) {
      float* s = lp_[axis][j];
      if (isnan(s[0])) s[0] = s[1] = s[2] = s[3] = x;   // start settled
      float y = b0 * x + b1 * s[0] + b2 * s[1] - a1 * s[2] - a2 * s[3];
      s[1] = s[0];
      s[0] = x;
      s[3] = s[2];
      s[2] = y;
      x = y;
    }
    return x;
  }
  int n_;
  uint8_t primed_, warm_;
  uint8_t hist_[3];
  Result res_;
  float diag_low_ = 0, diag_tremor_ = 0, diag_prominence_ = 0;

  // Phase tracking.
  float f_track_;
  int axis_;
  float b0_, b2_, a1_, a2_;
  float x1_ = 0, x2_ = 0, y1_ = 0, y2_ = 0;
  float prev_y_;
  float t_, last_cross_, next_fire_, last_fire_;

  void clear_block() {
    n_ = 0;
    for (int k = 0; k < NK; k++) {
      coef_[k] = 2.0f * cosf(2.0f * (float)M_PI * (k + K_MIN) / N);
      for (int i = 0; i < 3; i++) s1_[k][i] = s2_[k][i] = 0;
    }
    for (int k = 0; k < NLOW; k++) ms1_[k] = ms2_[k] = 0;
  }

  // |X_k|^2 for bin k on axis i, from the Goertzel state.
  float bin_power(int k, int i) const {
    float s1 = s1_[k][i], s2 = s2_[k][i];
    return s1 * s1 + s2 * s2 - coef_[k] * s1 * s2;
  }

  void finish_block() {
    float P[NK], Pax[3] = {0, 0, 0};
    for (int k = 0; k < NK; k++) {
      P[k] = 0;
      for (int i = 0; i < 3; i++) P[k] += bin_power(k, i);
    }
    // Hann window: a sinusoid of variance v spreads 3 v N^2 / 16 over its bins.
    const float to_var = 16.0f / (3.0f * N * N);

    int kp = K_TREMOR_MIN - K_MIN;
    float band = 0;
    for (int k = K_TREMOR_MIN - K_MIN; k < NK; k++) {
      band += P[k];
      if (P[k] > P[kp]) kp = k;
    }
    float low = 0, mag_low = 0;
    for (int k = 0; k < NLOW; k++) {
      low += P[k];
      mag_low += ms1_[k] * ms1_[k] + ms2_[k] * ms2_[k] - coef_[k] * ms1_[k] * ms2_[k];
    }

    // Sub-bin peak frequency by parabolic interpolation on log power.
    float delta = 0;
    if (kp > K_TREMOR_MIN - K_MIN && kp < NK - 1) {
      float l = logf(P[kp - 1] + 1e-9f), c = logf(P[kp] + 1e-9f), r = logf(P[kp + 1] + 1e-9f);
      float den = l - 2 * c + r;
      if (den < 0) delta = fmaxf(-0.5f, fminf(0.5f, 0.5f * (l - r) / den));
    }
    float f = (kp + K_MIN + delta) * FS / N;

    // Power within +-2 bins of the peak = the tremor itself.
    float peak = 0;
    for (int k = kp - 2; k <= kp + 2; k++)
      if (k >= 0 && k < NK) peak += P[k];
    float var_tremor = peak * to_var;
    float var_low = low * to_var;
    float var_mag_low = mag_low * to_var;
    float prominence = band > 0 ? peak / band : 0;

    float amp = sqrtf(2.0f * var_tremor);                  // m/s^2
    float w2 = 4.0f * (float)M_PI * (float)M_PI * f * f;   // (2 pi f)^2
    float disp_cm = 2.0f * amp / w2 * 100.0f;

    uint8_t grade = 0;
    if (prominence >= min_prominence)
      for (int b = 0; b < 4; b++)
        if (disp_cm >= BAND_CM[b]) grade = b + 1;

    // Voluntary movement and walking put power below 3 Hz into the size of
    // the acceleration. A resting hand with tremor also tilts slowly, which
    // shows up below 3 Hz on each axis but not in the size, so per-axis
    // power only counts when it rivals the tremor itself.
    // The filters are still settling during the first block after a reset,
    // so movement is judged from the second block on.
    bool moving = primed_ > 0 &&
                  (var_mag_low > move_var || (var_low > move_var && var_low > move_ratio * var_tremor));

    // Dominant axis at the peak, for phase tracking.
    for (int i = 0; i < 3; i++)
      for (int k = kp - 1; k <= kp + 1; k++)
        if (k >= 0 && k < NK) Pax[i] += bin_power(k, i);
    axis_ = Pax[0] >= Pax[1] && Pax[0] >= Pax[2] ? 0 : Pax[1] >= Pax[2] ? 1 : 2;
    if (grade > 0 && fabsf(f - f_track_) > 0.05f) {
      f_track_ = f;
      design_bandpass(f_track_);
    }

    // Gate: still hand and at least grade 2; debounce 2 of the last 3 blocks.
    uint8_t decision = (!moving && grade >= 2) ? grade : 0;
    hist_[0] = hist_[1];
    hist_[1] = hist_[2];
    hist_[2] = decision;
    if (primed_ < 3) primed_++;
    uint8_t cue = 0, agree = 0, weakest = 4;
    for (int i = 0; i < 3; i++)
      if (hist_[i]) {
        agree++;
        if (hist_[i] < weakest) weakest = hist_[i];
      }
    if (decision && agree >= 2) cue = weakest;

    res_ = {grade, f, disp_cm, moving, cue};
    diag_low_ = var_mag_low;
    diag_tremor_ = var_tremor;
    diag_prominence_ = prominence;
  }

  // RBJ constant-0-dB band-pass, Q = 2: zero phase at the centre frequency, so
  // a zero crossing of the output is a zero crossing of the tremor.
  void design_bandpass(float f0) {
    float w0 = 2.0f * (float)M_PI * f0 / FS;
    float alpha = sinf(w0) / (2.0f * 2.0f);
    float a0 = 1 + alpha;
    b0_ = alpha / a0;
    b2_ = -alpha / a0;
    a1_ = -2 * cosf(w0) / a0;
    a2_ = (1 - alpha) / a0;
  }

  void track_phase(float x) {
    float y = b0_ * x + b2_ * x2_ - a1_ * y1_ - a2_ * y2_;
    x2_ = x1_;
    x1_ = x;
    y2_ = y1_;
    y1_ = y;
    if (prev_y_ < 0 && y >= 0) {
      // Interpolate the crossing time between samples.
      float frac = prev_y_ / (prev_y_ - y);
      float tc = t_ - (1 - frac) / FS;
      float T = 1.0f / f_track_;
      last_cross_ = tc;
      // Aim at the next crossing, one latency early; skip if too soon after
      // the last pulse (refractory 0.6 cycle).
      float target = tc + T - latency_s;
      if (last_fire_ < 0 || target - last_fire_ > 0.6f * T) next_fire_ = target;
    }
    prev_y_ = y;
  }
};

}  // namespace ts
