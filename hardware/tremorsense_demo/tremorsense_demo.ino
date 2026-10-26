// TremorSense demo: runs 12 test cases one after another, without moving the
// sensor. Each case feeds the real tremor engine (the same tremor_core.h as
// the firmware) a synthetic GY-61 signal of known frequency and size, drives
// the motor and buzzer exactly as the firmware does, and checks the result.
//
// For each case the LCD shows:
//   intro   "Test 3 of 12" / the case name                    (6 s)
//   running live grade, frequency, size and cue, as in the firmware
//   result  "Test 3: PASS" / what it showed                   (6 s)
// The Serial Monitor (115200 baud, "New Line") prints the input, the expected
// result, every 2-second reading, the verdict and a summary table at the end.
//
// Serial Monitor commands:
//   p        pause / resume
//   n        skip to the next case
//   r        repeat the current case
//   <1-12>   jump to that case
//   a        run all cases again
//   v        Serial Plotter view on/off (tremor wave and motor pulses)
// The Uno's reset button also starts again from case 1.
#include <LiquidCrystal.h>

#include "demo_cases.h"
#include "pins.h"
#include "tremor_core.h"

const unsigned long SAMPLE_US = 20000;   // 50 Hz, as the firmware samples
const unsigned long INTRO_MS = 6000;
const unsigned long RESULT_MS = 6000;

LiquidCrystal lcd(LCD_RS, LCD_E, LCD_D4, LCD_D5, LCD_D6, LCD_D7);
ts::Engine engine;
demo::Generator gen;
demo::Checker chk;
demo::Case cur;

enum State { INTRO, RUN, RESULT, SUMMARY };
State state;
int idx = 0;
unsigned long state_ms;
unsigned long next_sample_us;
unsigned long pulse_end_ms = 0;
bool pulsing = false;
bool paused = false;
bool plot_mode = false;
uint8_t last_cue = 0;
uint8_t block_no = 0;
bool passed[demo::NCASES];
bool ran[demo::NCASES];
char line[8];
uint8_t line_len = 0;

const __FlashStringHelper* case_name(int i) {
  switch (i) {
    case 0: return F("Hand at rest");
    case 1: return F("Slight tremor");
    case 2: return F("Mild tremor");
    case 3: return F("Moderate tremor");
    case 4: return F("Severe tremor");
    case 5: return F("8 Hz tremor");
    case 6: return F("Walking");
    case 7: return F("Using the arm");
    case 8: return F("Hand tilting");
    case 9: return F("Short burst");
    case 10: return F("Tremor stops");
    default: return F("Walking starts");
  }
}

const __FlashStringHelper* case_input(int i) {
  switch (i) {
    case 0: return F("Hand still, no tremor (sensor noise only)");
    case 1: return F("5 Hz tremor, 0.5 cm peak-to-peak, hand still");
    case 2: return F("5 Hz tremor, 2 cm, hand still");
    case 3: return F("5 Hz tremor, 5 cm, hand still");
    case 4: return F("3.5 Hz tremor, 12 cm, hand still");
    case 5: return F("8 Hz tremor (essential tremor range), 2 cm, hand still");
    case 6: return F("5 Hz tremor, 2 cm, while walking");
    case 7: return F("5 Hz tremor, 2 cm, while moving the arm");
    case 8: return F("5 Hz tremor, 5 cm, hand slowly tilting");
    case 9: return F("5 Hz tremor, 5 cm, for only 2 s, then rest");
    case 10: return F("5 Hz tremor, 5 cm for 12 s, then it stops");
    default: return F("5 Hz tremor, 2 cm; walking starts after 12 s");
  }
}

const __FlashStringHelper* case_expect(int i) {
  switch (i) {
    case 0: return F("No tremor, no cue");
    case 1: return F("Grade 1, 5 Hz: logged, no cue (below grade 2)");
    case 2: return F("Grade 2, 5 Hz, about 2 cm: cue 2, pulses locked to the tremor");
    case 3: return F("Grade 3, 5 Hz, about 5 cm: cue 3, pulses locked");
    case 4: return F("Grade 4, 3.5 Hz, about 12 cm: cue 4 (strongest)");
    case 5: return F("Grade 2, 8 Hz: frequency tracked, cue 2, pulses locked");
    case 6: return F("Grade 2 seen, but 'Moving: paused', no cue at all");
    case 7: return F("Grade 2 seen, but 'Moving: paused', no cue at all");
    case 8: return F("Grade 3, cue 3: tilting is not mistaken for movement");
    case 9: return F("No cue: one block is not enough (2 of 3 must agree)");
    case 10: return F("Cue 3 during the tremor, off within 4 s after it stops");
    default: return F("Cue 2 while still, then 'Moving: paused' and cue off");
  }
}

void print_padded(const char* s) {
  uint8_t i = 0;
  for (; s[i] && i < 16; i++) lcd.write(s[i]);
  for (; i < 16; i++) lcd.write(' ');
}

void lcd_line(uint8_t row, const char* s) {
  lcd.setCursor(0, row);
  print_padded(s);
}

void lcd_line(uint8_t row, const __FlashStringHelper* s) {
  lcd.setCursor(0, row);
  uint8_t n = lcd.print(s);
  for (; n < 16; n++) lcd.write(' ');
}

void motor_off() {
  analogWrite(MOTOR, 0);
  digitalWrite(MOTOR, LOW);
  pulsing = false;
}

void pulse(uint8_t duty, uint16_t ms) {
  if (duty == 0 || ms == 0) return;
  analogWrite(MOTOR, duty);
  pulse_end_ms = millis() + ms;
  pulsing = true;
}

void enter(State s) {
  state = s;
  state_ms = millis();
}

void start_case(int i) {
  idx = i;
  motor_off();
  demo::load_case(idx, cur);
  char a[17];
  snprintf_P(a, sizeof a, PSTR("Test %d of %d"), idx + 1, demo::NCASES);
  lcd_line(0, a);
  lcd_line(1, case_name(idx));
  tone(BUZZER, 1500, 80);

  Serial.println();
  Serial.print(F("=== Test "));
  Serial.print(idx + 1);
  Serial.print(F(" of "));
  Serial.print(demo::NCASES);
  Serial.print(F(": "));
  Serial.print(case_name(idx));
  Serial.println(F(" ==="));
  Serial.print(F("Input : "));
  Serial.println(case_input(idx));
  Serial.print(F("Expect: "));
  Serial.println(case_expect(idx));
  enter(INTRO);
}

void begin_run() {
  engine.reset();
  gen.start(cur);
  chk = demo::Checker();
  last_cue = 0;
  block_no = 0;
  next_sample_us = micros();
  enter(RUN);
}

// Same LCD layout as the firmware, with the test number in front.
void show(const ts::Result& r) {
  char a[17], b[17], f[6], d[6];
  dtostrf(r.freq_hz, 3, 1, f);
  dtostrf(r.disp_cm, 3, 1, d);
  if (r.grade == 0) snprintf_P(a, sizeof a, PSTR("T%d No tremor"), idx + 1);
  else snprintf_P(a, sizeof a, PSTR("T%d Grade %d %sHz"), idx + 1, r.grade, f);
  if (r.moving) snprintf_P(b, sizeof b, PSTR("Moving: paused"));
  else if (r.cue) snprintf_P(b, sizeof b, PSTR("%scm  Cue %d"), d, r.cue);
  else if (r.grade) snprintf_P(b, sizeof b, PSTR("%scm  No cue"), d);
  else snprintf_P(b, sizeof b, PSTR("Hand still"));
  lcd_line(0, a);
  lcd_line(1, b);
}

void print_block(const ts::Result& r) {
  Serial.print(F("  t="));
  Serial.print(block_no * 2);
  Serial.print(F("s  grade "));
  Serial.print(r.grade);
  Serial.print(F("  "));
  Serial.print(r.freq_hz, 2);
  Serial.print(F(" Hz  "));
  Serial.print(r.disp_cm, 2);
  Serial.print(r.moving ? F(" cm  moving  ") : F(" cm  still   "));
  Serial.print(F("cue "));
  Serial.print(r.cue);
  Serial.print(F("  pulses "));
  Serial.println(chk.pulses);
}

void finish_case() {
  motor_off();
  const char* why = chk.failure(cur);
  passed[idx] = !why;
  ran[idx] = true;
  const ts::Result& r = chk.last;

  char a[17], b[17];
  snprintf_P(a, sizeof a, why ? PSTR("Test %d: FAIL") : PSTR("Test %d: PASS"), idx + 1);
  if (why) {
    strncpy(b, why, 16);
    b[16] = 0;
  } else if (r.moving) snprintf_P(b, sizeof b, PSTR("Paused: correct"));
  else if (r.cue) snprintf_P(b, sizeof b, PSTR("Cue %d, locked"), r.cue);
  else if (chk.pulses) snprintf_P(b, sizeof b, PSTR("Cue stopped: OK"));
  else snprintf_P(b, sizeof b, PSTR("No cue: correct"));
  lcd_line(0, a);
  lcd_line(1, b);
  if (why) {
    tone(BUZZER, 400, 400);
  } else {
    tone(BUZZER, 2000, 70);
    delay(110);
    tone(BUZZER, 2600, 70);
  }

  Serial.print(F("Result: "));
  Serial.print(why ? F("FAIL (") : F("PASS"));
  if (why) {
    Serial.print(why);
    Serial.print(')');
  }
  Serial.print(F("  grade "));
  Serial.print(r.grade);
  Serial.print(F(", "));
  Serial.print(r.freq_hz, 2);
  Serial.print(F(" Hz, "));
  Serial.print(r.disp_cm, 2);
  Serial.print(F(" cm, "));
  Serial.print(r.moving ? F("moving") : F("still"));
  Serial.print(F(", cue "));
  Serial.print(r.cue);
  Serial.print(F(", "));
  Serial.print(chk.pulses);
  Serial.print(F(" pulses"));
  if (chk.pulses) {
    Serial.print(F(", phase lock "));
    Serial.print(chk.phase_lock(), 2);
  }
  Serial.println();
  enter(RESULT);
}

void show_summary() {
  int n = 0, ok = 0;
  Serial.println();
  Serial.println(F("=== Summary ==="));
  for (int i = 0; i < demo::NCASES; i++) {
    if (!ran[i]) continue;
    n++;
    ok += passed[i];
    Serial.print(F("  Test "));
    if (i < 9) Serial.print(' ');
    Serial.print(i + 1);
    Serial.print(F("  "));
    Serial.print(passed[i] ? F("PASS  ") : F("FAIL  "));
    Serial.println(case_name(i));
  }
  Serial.print(ok);
  Serial.print('/');
  Serial.print(n);
  Serial.println(F(" passed. Type a to run all again."));
  char a[17];
  snprintf_P(a, sizeof a, PSTR("Done: %d/%d PASS"), ok % 100, n % 100);
  lcd_line(0, a);
  lcd_line(1, F("a = run again"));
  enter(SUMMARY);
}

void handle_line(char* s) {
  if (s[0] == 'p') {
    paused = !paused;
    motor_off();
    Serial.println(paused ? F("Paused. Type p to resume.") : F("Resumed."));
    state_ms = millis();
    next_sample_us = micros();
  } else if (s[0] == 'n') {
    if (idx + 1 < demo::NCASES) start_case(idx + 1);
    else show_summary();
  } else if (s[0] == 'r') {
    start_case(idx);
  } else if (s[0] == 'a') {
    for (int i = 0; i < demo::NCASES; i++) ran[i] = passed[i] = false;
    start_case(0);
  } else if (s[0] == 'v') {
    plot_mode = !plot_mode;
  } else {
    int i = atoi(s);
    if (i >= 1 && i <= demo::NCASES) start_case(i - 1);
  }
  if (s[0] != 'p') paused = false;
}

void read_serial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      line[line_len] = 0;
      if (line_len) handle_line(line);
      line_len = 0;
    } else if (line_len < sizeof line - 1) {
      line[line_len++] = c;
    }
  }
}

// Motor and buzzer check before the tests: weak, medium, strong.
void hardware_check() {
  lcd_line(0, F("TremorSense demo"));
  lcd_line(1, F("Motor check"));
  Serial.println(F("TremorSense demo: 12 test cases with a synthetic tremor signal."));
  Serial.println(F("Motor check: weak, medium, strong."));
  const uint8_t duty[3] = {160, 210, 255};
  for (int i = 0; i < 3; i++) {
    analogWrite(MOTOR, duty[i]);
    delay(300);
    motor_off();
    delay(300);
  }
  lcd_line(1, F("Buzzer check"));
  tone(BUZZER, 1800, 100);
  delay(150);
  tone(BUZZER, 2400, 100);
  delay(1500);
}

void setup() {
  pinMode(MOTOR, OUTPUT);
  digitalWrite(MOTOR, LOW);
  pinMode(BUZZER, OUTPUT);
  pinMode(LCD_CONTRAST, OUTPUT);
  analogWrite(LCD_CONTRAST, CONTRAST_DEFAULT);
  Serial.begin(115200);
  lcd.begin(16, 2);
  hardware_check();
  start_case(0);
}

void loop() {
  read_serial();
  if (pulsing && (long)(millis() - pulse_end_ms) >= 0) motor_off();
  if (paused) return;

  switch (state) {
    case INTRO:
      if (millis() - state_ms >= INTRO_MS) begin_run();
      break;

    case RUN: {
      if ((long)(micros() - next_sample_us) < 0) return;
      next_sample_us += SAMPLE_US;
      int x[3];
      gen.sample(x);
      bool block = engine.push(x[0], x[1], x[2]);
      if (engine.should_fire()) {
        pulse(engine.pulse_duty(), engine.pulse_ms());
        chk.on_pulse(gen.phase(), gen.hz(), engine.latency_s);
      }
      if (plot_mode) {
        Serial.print(F("tremor:"));
        Serial.print((int)(engine.phase_signal() * 10));
        Serial.print(F(" motor:"));
        Serial.println(pulsing ? 20 : 0);
      }
      if (block) {
        const ts::Result& r = engine.result();
        block_no++;
        chk.on_block(r);
        show(r);
        if (!plot_mode) print_block(r);
        if (r.cue && !last_cue) tone(BUZZER, 2000, 60);   // cueing switched on
        last_cue = r.cue;
      }
      if (gen.done()) finish_case();
      break;
    }

    case RESULT:
      if (millis() - state_ms >= RESULT_MS) {
        if (idx + 1 < demo::NCASES) start_case(idx + 1);
        else show_summary();
      }
      break;

    case SUMMARY:
      break;
  }
}
