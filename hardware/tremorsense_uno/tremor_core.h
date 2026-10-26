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

// ADXL335 on a GY-61 board: about 0.33 V per g; Uno ADC: 5 V / 1023 counts.
const float G_PER_COUNT = (5.0f / 1023.0f) / 0.33f;
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

  Engine() { reset(); }

  void reset() {
    n_ = 0;
    primed_ = 0;
    for (int a = 0; a < 3; a++) mean_[a] = NAN;
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
    for (int i = 0; i < 3; i++) {
      if (isnan(mean_[i])) mean_[i] = c[i];
      // ~1 s time constant: follows posture changes, leaves 3-12 Hz intact.
      mean_[i] += 0.02f * (c[i] - mean_[i]);
      a[i] = (c[i] - mean_[i]) * MS2_PER_COUNT;
    }
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
  float clock() const { return t_; }

 private:
  // Block state: Goertzel s1, s2 per bin and axis.
  float s1_[NK][3], s2_[NK][3];
  float coef_[NK];
  float mean_[3];
  int n_;
  uint8_t primed_;
  uint8_t hist_[3];
  Result res_;

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
    float low = 0;
    for (int k = 0; k <= K_LOW_MAX - K_MIN; k++) low += P[k];

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
    float prominence = band > 0 ? peak / band : 0;

    float amp = sqrtf(2.0f * var_tremor);                  // m/s^2
    float w2 = 4.0f * (float)M_PI * (float)M_PI * f * f;   // (2 pi f)^2
    float disp_cm = 2.0f * amp / w2 * 100.0f;

    uint8_t grade = 0;
    if (prominence >= min_prominence)
      for (int b = 0; b < 4; b++)
        if (disp_cm >= BAND_CM[b]) grade = b + 1;

    // Voluntary movement, walking and posture changes put their power below
    // 3 Hz. A still hand, even with strong tremor, has almost none there.
    bool moving = var_low > move_var;

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
