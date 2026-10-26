// Host tests for the Uno tremor engine on simulated GY-61 (ADXL335) signals.
//   g++ -std=c++11 -O2 -I hardware/tremorsense_uno hardware/test/test_core.cpp -o /tmp/t && /tmp/t
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <random>
#include <vector>

#include "tremor_core.h"

static int failures = 0;
#define CHECK(cond, ...)              \
  do {                                \
    if (!(cond)) {                    \
      printf("FAIL: " __VA_ARGS__);   \
      printf("\n");                   \
      failures++;                     \
    }                                 \
  } while (0)

struct Sim {
  float f = 5.0f, p2p_cm = 0, walk = 0, voluntary = 0;
  bool handheld = false;   // irregular rhythm, changing size, slow tilting
  float dir[3] = {0.6f, 0.3f, 0.74f};
  std::mt19937 rng{1};
  float t = 0, phase = 0;

  // One sample of ADC counts, with the sensor's +-3.6 g range and 10-bit ADC.
  void sample(int out[3]) {
    std::normal_distribution<float> noise(0, 0.6f);
    float fi = f, gain = 1, tilt = 0;
    if (handheld) {
      fi += 0.35f * sinf(2 * M_PI * 0.13f * t) + 0.2f * sinf(2 * M_PI * 0.31f * t);
      gain += 0.3f * sinf(2 * M_PI * 0.4f * t);
      tilt = 0.25f * sinf(2 * M_PI * 0.5f * t) + 0.15f * sinf(2 * M_PI * 0.9f * t);
    }
    float amp = gain * (p2p_cm / 100.0f / 2.0f) * powf(2 * M_PI * fi, 2);  // m/s^2
    phase += 2 * M_PI * fi / ts::FS;
    float trem = amp * sinf(phase);
    float w = walk * (sinf(2 * M_PI * 1.8f * t) + 0.4f * sinf(2 * M_PI * 3.6f * t + 0.7f));
    float v = voluntary * sinf(2 * M_PI * 0.7f * t) + 0.5f * voluntary * sinf(2 * M_PI * 1.3f * t + 1);
    float g[3] = {9.81f * sinf(tilt), 0, 9.81f * cosf(tilt)};
    for (int i = 0; i < 3; i++) {
      // Walking bounces mostly sideways and up; arm movement goes every way.
      const float vdir[3] = {0.5f, 0.6f, 0.62f};
      float a = g[i] + dir[i] * trem + (i == 0 ? w : i == 1 ? 0 : 0.5f * w) + vdir[i] * v;
      float gs = fmaxf(-3.6f, fminf(3.6f, a / 9.81f));
      float volts = 1.65f + 0.33f * gs;
      int c = (int)lroundf(volts / 5.0f * 1023 + noise(rng));
      out[i] = c < 0 ? 0 : c > 1023 ? 1023 : c;
    }
    t += 1 / ts::FS;
  }
};

static ts::Result run(Sim& s, float seconds, std::vector<float>* fires = nullptr, ts::Engine* eng = nullptr) {
  ts::Engine local;
  ts::Engine& e = eng ? *eng : local;
  int c[3];
  for (int i = 0; i < (int)(seconds * ts::FS); i++) {
    s.sample(c);
    e.push(c[0], c[1], c[2]);
    if (e.should_fire() && fires) fires->push_back(e.clock());
  }
  return e.result();
}

int main() {
  // Grades from displacement, at Parkinsonian and essential tremor frequencies.
  struct Case { float f, p2p; int grade; } cases[] = {
      {5.0f, 0.0f, 0}, {5.0f, 0.5f, 1}, {5.0f, 2.0f, 2}, {5.0f, 5.0f, 3},
      {8.0f, 0.5f, 1}, {8.0f, 2.0f, 2}, {4.0f, 6.0f, 3},
      {5.3f, 2.0f, 2}, {6.7f, 4.0f, 3}, {9.2f, 0.8f, 1},
  };
  for (auto& c : cases) {
    Sim s;
    s.f = c.f;
    s.p2p_cm = c.p2p;
    ts::Result r = run(s, 12);
    printf("f=%.1f p2p=%.1f -> grade %d, f %.2f Hz, d %.2f cm, cue %d\n", c.f, c.p2p, r.grade, r.freq_hz, r.disp_cm, r.cue);
    CHECK(r.grade == c.grade, "grade for %.1f cm at %.1f Hz: got %d want %d", c.p2p, c.f, r.grade, c.grade);
    if (c.p2p > 0) {
      CHECK(fabsf(r.freq_hz - c.f) < 0.25f, "frequency %.2f vs %.2f", r.freq_hz, c.f);
      CHECK(fabsf(logf(r.disp_cm / c.p2p)) < 0.25f, "displacement %.2f vs %.2f cm", r.disp_cm, c.p2p);
    }
    CHECK(r.cue == (c.grade >= 2 ? c.grade : 0), "cue %d for grade %d", r.cue, c.grade);
  }

  // Saturation: a very large tremor still reads at least grade 3.
  {
    Sim s;
    s.f = 4.0f;
    s.p2p_cm = 14.0f;
    ts::Result r = run(s, 12);
    printf("saturating 14 cm at 4 Hz -> grade %d (d %.1f cm), cue %d\n", r.grade, r.disp_cm, r.cue);
    CHECK(r.grade >= 3, "saturated tremor graded %d", r.grade);
    CHECK(r.cue >= 3, "saturated tremor not cued (cue %d)", r.cue);
  }

  // Shaking the sensor by hand: irregular, tilting, but clearly rhythmic.
  for (float p2p : {1.5f, 2.5f, 4.0f, 7.0f}) {
    Sim s;
    s.f = 4.5f;
    s.p2p_cm = p2p;
    s.handheld = true;
    ts::Engine e;
    int cued = 0, blocks = 0;
    int c[3];
    for (int i = 0; i < 30 * 50; i++) {
      s.sample(c);
      if (e.push(c[0], c[1], c[2]) && i > 6 * 50) {
        blocks++;
        cued += e.result().cue > 0;
      }
    }
    printf("hand-shaken %.1f cm at ~4.5 Hz -> cue in %d of %d blocks (low %.2f, tremor %.2f)\n", p2p, cued, blocks, e.diag_low(), e.diag_tremor());
    CHECK(cued >= blocks * 3 / 4, "hand-shaken tremor cued in only %d of %d blocks", cued, blocks);
  }

  // Walking or using the hand pauses cueing, even with tremor present.
  for (int mode = 0; mode < 2; mode++) {
    Sim s;
    s.p2p_cm = 2.0f;
    if (mode == 0) s.walk = 4.0f; else s.voluntary = 5.0f;
    ts::Result r = run(s, 12);
    printf("%s with grade-2 tremor -> moving %d, cue %d\n", mode ? "hand use" : "walking", r.moving, r.cue);
    CHECK(r.moving, "movement not detected (mode %d)", mode);
    CHECK(r.cue == 0, "cue %d while moving", r.cue);
  }

  // Debounce: the cue switches off within two blocks once movement starts.
  {
    Sim s;
    s.p2p_cm = 2.0f;
    ts::Engine e;
    run(s, 10, nullptr, &e);
    CHECK(e.result().cue == 2, "cue before walking %d", e.result().cue);
    s.walk = 4.0f;
    run(s, 4, nullptr, &e);
    CHECK(e.result().cue == 0, "cue still on after 4 s of walking");
  }

  // Phase locking: pulses, delayed by the motor latency, land at the same
  // point of each tremor cycle.
  {
    Sim s;
    s.f = 5.3f;
    s.p2p_cm = 3.0f;
    ts::Engine e;
    std::vector<float> fires;
    run(s, 30, &fires, &e);
    double C = 0, S = 0;
    int n = 0;
    for (float tf : fires) {
      if (tf < 10) continue;
      float ph = 2 * M_PI * s.f * (tf + e.latency_s);
      C += cos(ph);
      S += sin(ph);
      n++;
    }
    double plv = n ? sqrt(C * C + S * S) / n : 0;
    double rate = n / 20.0;
    printf("phase locking: %d pulses in 20 s (%.2f per s at %.1f Hz), PLV %.3f\n", n, rate, s.f, plv);
    CHECK(plv > 0.8, "phase-locking value %.3f", plv);
    CHECK(rate > 0.6 * s.f && rate <= s.f + 0.1, "pulse rate %.2f/s", rate);
  }

  printf(failures ? "%d FAILED\n" : "all passed\n", failures);
  return failures ? 1 : 0;
}
