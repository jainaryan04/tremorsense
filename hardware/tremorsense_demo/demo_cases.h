// Test cases for the TremorSense demo sketch: each one feeds the tremor engine
// a synthetic GY-61 signal of known frequency and size, so the result can be
// checked against what it should be. Plain C++, shared with the host test
// hardware/test/test_demo.cpp.
#pragma once
#include <math.h>
#include <stdint.h>
#include <string.h>

#include "tremor_core.h"

#if defined(__AVR__)
#include <avr/pgmspace.h>
#define DEMO_PROGMEM PROGMEM
#define demo_memcpy memcpy_P
#else
#define DEMO_PROGMEM
#define demo_memcpy memcpy
#endif

namespace demo {

// One stretch of input: tremor frequency and peak-to-peak size, plus walking,
// voluntary arm movement and slow hand tilting.
struct Segment {
  float secs, hz, p2p_cm, walk, voluntary, tilt;
};

enum CueRule : uint8_t {
  NEVER,        // no pulse at any time
  AT_END,       // cueing at the end with the expected strength
  ON_THEN_OFF,  // cued during the case, off by the end
};

struct Case {
  Segment seg[2];
  uint8_t nseg;
  int8_t grade;      // expected final grade, -1 = not checked
  bool moving;       // expected final movement flag
  CueRule rule;
  uint8_t cue;       // expected final cue strength for AT_END
  float hz;          // expected frequency, 0 = not checked
};

const int NCASES = 12;

const Case CASES[NCASES] DEMO_PROGMEM = {
    // 1. Hand at rest: sensor noise only.
    {{{14, 5.0f, 0, 0, 0, 0}}, 1, 0, false, NEVER, 0, 0},
    // 2. Slight tremor (grade 1): logged, not cued.
    {{{14, 5.0f, 0.5f, 0, 0, 0}}, 1, 1, false, NEVER, 0, 5.0f},
    // 3. Mild tremor (grade 2): cue 2.
    {{{14, 5.0f, 2.0f, 0, 0, 0}}, 1, 2, false, AT_END, 2, 5.0f},
    // 4. Moderate tremor (grade 3): cue 3, phase locked.
    {{{14, 5.0f, 5.0f, 0, 0, 0}}, 1, 3, false, AT_END, 3, 5.0f},
    // 5. Severe tremor (grade 4): cue 4.
    {{{14, 3.5f, 12.0f, 0, 0, 0}}, 1, 4, false, AT_END, 4, 3.5f},
    // 6. Essential-tremor frequency (8 Hz): tracked, cue 2.
    {{{14, 8.0f, 2.0f, 0, 0, 0}}, 1, 2, false, AT_END, 2, 8.0f},
    // 7. Walking with tremor: paused.
    {{{14, 5.0f, 2.0f, 4.0f, 0, 0}}, 1, 2, true, NEVER, 0, 0},
    // 8. Using the arm with tremor: paused.
    {{{14, 5.0f, 2.0f, 0, 5.0f, 0}}, 1, 2, true, NEVER, 0, 0},
    // 9. Hand tilting slowly with tremor: not mistaken for movement.
    {{{14, 5.0f, 5.0f, 0, 0, 1.0f}}, 1, 3, false, AT_END, 3, 5.0f},
    // 10. A 2-second burst, then rest: debounce, no cue.
    {{{2, 5.0f, 5.0f, 0, 0, 0}, {12, 5.0f, 0, 0, 0, 0}}, 2, 0, false, NEVER, 0, 0},
    // 11. Tremor stops: cue switches off.
    {{{12, 5.0f, 5.0f, 0, 0, 0}, {8, 5.0f, 0, 0, 0, 0}}, 2, 0, false, ON_THEN_OFF, 0, 0},
    // 12. Walking starts during tremor: cue pauses.
    {{{12, 5.0f, 2.0f, 0, 0, 0}, {8, 5.0f, 2.0f, 4.0f, 0, 0}}, 2, 2, true, ON_THEN_OFF, 0, 0},
};

inline void load_case(int i, Case& c) { demo_memcpy(&c, &CASES[i], sizeof c); }

inline float case_secs(const Case& c) {
  float s = 0;
  for (int i = 0; i < c.nseg; i++) s += c.seg[i].secs;
  return s;
}

// Synthetic GY-61 output, in ADC counts, for one case.
class Generator {
 public:
  // Keeps a pointer to the case: it must outlive the run.
  void start(const Case& c) {
    c_ = &c;
    t_ = 0;
    phase_ = 0;
    seed_ = 12345;
  }

  bool done() const { return t_ >= case_secs(*c_) - 0.5f / ts::FS; }
  const Segment& segment() const {
    float end = 0;
    for (int i = 0; i < c_->nseg; i++) {
      end += c_->seg[i].secs;
      if (t_ < end) return c_->seg[i];
    }
    return c_->seg[c_->nseg - 1];
  }
  // Tremor phase (radians) of the last sample, for the phase-lock check.
  float phase() const { return phase_; }
  float hz() const { return segment().hz; }

  void sample(int out[3]) {
    const Segment& s = segment();
    const float PI2 = 2.0f * (float)M_PI;
    phase_ += PI2 * s.hz / ts::FS;
    if (phase_ > PI2) phase_ -= PI2;
    float amp = (s.p2p_cm / 200.0f) * (PI2 * s.hz) * (PI2 * s.hz);   // m/s^2
    float trem = amp * sinf(phase_);
    float w = s.walk * (sinf(PI2 * 1.8f * t_) + 0.4f * sinf(PI2 * 3.6f * t_ + 0.7f));
    float v = s.voluntary * (sinf(PI2 * 0.7f * t_) + 0.5f * sinf(PI2 * 1.3f * t_ + 1));
    float tilt = s.tilt * (0.25f * sinf(PI2 * 0.5f * t_) + 0.15f * sinf(PI2 * 0.9f * t_));
    float g[3] = {9.81f * sinf(tilt), 0, 9.81f * cosf(tilt)};
    const float dir[3] = {0.6f, 0.3f, 0.74f};    // tremor direction
    const float vdir[3] = {0.5f, 0.6f, 0.62f};   // arm movement direction
    for (int i = 0; i < 3; i++) {
      float a = g[i] + dir[i] * trem + (i == 0 ? w : i == 2 ? 0.5f * w : 0) + vdir[i] * v;
      float gs = fmaxf(-3.6f, fminf(3.6f, a / 9.81f));   // sensor range
      float counts = (1.65f + 0.33f * gs) / 5.0f * 1023.0f + noise();
      int c = (int)lroundf(counts);
      out[i] = c < 0 ? 0 : c > 1023 ? 1023 : c;
    }
    t_ += 1.0f / ts::FS;
  }

 private:
  const Case* c_;
  float t_, phase_;
  uint32_t seed_;

  // About +-1 count of ADC noise (sum of two uniforms).
  float noise() {
    seed_ = seed_ * 1664525u + 1013904223u;
    float u1 = (seed_ >> 8) / 16777216.0f;
    seed_ = seed_ * 1664525u + 1013904223u;
    float u2 = (seed_ >> 8) / 16777216.0f;
    return u1 + u2 - 1.0f;
  }
};

// Collects what happened during a case and decides pass or fail.
struct Checker {
  uint16_t pulses = 0;
  bool cue_seen = false;
  float C = 0, S = 0;
  ts::Result last = {0, 0, 0, false, 0};

  void on_block(const ts::Result& r) {
    last = r;
    if (r.cue) cue_seen = true;
  }

  // Each pulse is timed one latency early; record the tremor phase it aims at.
  void on_pulse(float phase, float hz, float latency_s) {
    float ph = phase + 2.0f * (float)M_PI * hz * latency_s;
    C += cosf(ph);
    S += sinf(ph);
    pulses++;
  }

  // 1 = every pulse at the same point of the cycle, 0 = random timing.
  float phase_lock() const { return pulses ? sqrtf(C * C + S * S) / pulses : 0; }

  // Why it failed, or nullptr when it passed.
  const char* failure(const Case& c) const {
    if (c.grade >= 0 && last.grade != c.grade) return "wrong grade";
    if (c.hz > 0 && fabsf(last.freq_hz - c.hz) > 0.3f) return "wrong frequency";
    if (last.moving != c.moving) return c.moving ? "movement missed" : "false movement";
    switch (c.rule) {
      case NEVER:
        if (pulses || cue_seen) return "cued, should not";
        break;
      case AT_END:
        if (last.cue != c.cue) return "wrong cue";
        if (phase_lock() < 0.8f) return "not phase locked";
        break;
      case ON_THEN_OFF:
        if (!cue_seen || !pulses) return "never cued";
        if (last.cue) return "cue did not stop";
        break;
    }
    return nullptr;
  }
};

}  // namespace demo
