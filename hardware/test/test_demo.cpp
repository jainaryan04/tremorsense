// Runs every case of the demo sketch (hardware/tremorsense_demo) on the host
// and checks that each one passes, so the demo can't fail on stage.
//   g++ -std=c++11 -O2 -I hardware/tremorsense_demo hardware/test/test_demo.cpp -o /tmp/d && /tmp/d
#include <cstdio>

#include "demo_cases.h"

int main() {
  int failures = 0;
  for (int i = 0; i < demo::NCASES; i++) {
    demo::Case c;
    demo::load_case(i, c);
    demo::Generator gen;
    demo::Checker chk;
    ts::Engine e;
    gen.start(c);
    int x[3];
    while (!gen.done()) {
      gen.sample(x);
      if (e.push(x[0], x[1], x[2])) chk.on_block(e.result());
      if (e.should_fire()) chk.on_pulse(gen.phase(), gen.hz(), e.latency_s);
    }
    const ts::Result& r = chk.last;
    const char* why = chk.failure(c);
    printf("case %2d: grade %d  %.2f Hz  %.2f cm  moving %d  cue %d  pulses %3d  lock %.2f  %s\n", i + 1, r.grade,
           r.freq_hz, r.disp_cm, r.moving, r.cue, chk.pulses, chk.phase_lock(), why ? why : "PASS");
    if (why) failures++;
  }
  printf(failures ? "%d FAILED\n" : "all passed\n", failures);
  return failures ? 1 : 0;
}
