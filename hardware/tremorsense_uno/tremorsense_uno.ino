// TremorSense firmware for Arduino Uno + GY-61 + JHD162A LCD + coin motor + piezo.
//
// Standalone: grades tremor every 2 s, shows it on the LCD and, when the hand
// is still and the tremor is at least UPDRS grade 2, sends vibration pulses
// timed to the tremor cycle.
//
// With the TremorSense web app (Chrome, "Arduino (USB)" source) the Uno
// streams raw 50 Hz acceleration and the app runs the full model, conformal
// safety gate and medication forecast, sending back motor and buzzer commands.
//
// Serial protocol, 115200 baud, one line per message:
//   Uno -> app  H,TremorSense-Uno,<version>         on boot
//               A,<x>,<y>,<z>                       raw ADC counts, 50 Hz (app mode only)
//               G,<grade>,<Hz*100>,<cm*100>,<moving>,<cue>   every 2 s
//               D,<move power*100>,<tremor power*100>,<peak share %>,<sim grade>
//                                                   every 2 s, why the gate decided
//   app -> Uno  M,1 / M,0     app mode on (repeat at least every 5 s) / off
//               P,<duty 0-255>,<ms>                 vibration pulse now
//               B,<Hz>,<ms>                         buzzer tone
//               T,<text> / L,<text>                 LCD line 1 / line 2 (16 chars)
//               K,<0-255>                           LCD contrast
//               V,1 / V,0    Serial Plotter view on/off: per sample "tremor:<m/s^2*10>
//                            motor:<0|20>" instead of the G/D lines
//               S,<0-4>      built-in test signal: a steady 5 Hz tremor of that
//                            UPDRS grade replaces the sensor (S,0 = sensor again).
//                            The LCD shows "S" in the last column while it runs.
#include <LiquidCrystal.h>

#include "pins.h"
#include "tremor_core.h"

const char VERSION[] = "1";
const unsigned long SAMPLE_US = 20000;   // 50 Hz
const unsigned long APP_TIMEOUT_MS = 5000;

LiquidCrystal lcd(LCD_RS, LCD_E, LCD_D4, LCD_D5, LCD_D6, LCD_D7);
ts::Engine engine;

unsigned long next_sample_us;
unsigned long pulse_end_ms = 0;
bool pulsing = false;
bool app_mode = false;
unsigned long last_app_ms = 0;
uint8_t last_cue = 0;
char line[28];
uint8_t line_len = 0;
char app_text[17] = "";
char app_top[17] = "";

// Built-in test signal (S command): a 5 Hz tremor at the middle of each
// grade's displacement band, along a fixed direction, plus ADC-sized noise.
uint8_t sim_grade = 0;
bool plot_mode = false;
float sim_phase = 0;
const float SIM_P2P_CM[5] = {0, 0.5f, 2.0f, 5.0f, 12.0f};
const float SIM_HZ = 5.0f;

void sim_counts(int* x, int* y, int* z) {
  sim_phase += 2 * PI * SIM_HZ / ts::FS;
  if (sim_phase > 2 * PI) sim_phase -= 2 * PI;
  float amp = SIM_P2P_CM[sim_grade] / 200.0f * sq(2 * PI * SIM_HZ);   // m/s^2
  float c = amp * sin(sim_phase) / ts::MS2_PER_COUNT;
  *x = constrain((int)(ts::ZERO_G_COUNTS + 0.6f * c) + random(-1, 2), 0, 1023);
  *y = constrain((int)(ts::ZERO_G_COUNTS + 0.3f * c) + random(-1, 2), 0, 1023);
  *z = constrain((int)(ts::ZERO_G_COUNTS + 9.81f / ts::MS2_PER_COUNT + 0.74f * c) + random(-1, 2), 0, 1023);
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

void print_padded(const char* s) {
  // Write exactly 16 characters so old text is cleared.
  uint8_t i = 0;
  for (; s[i] && i < 16; i++) lcd.write(s[i]);
  for (; i < 16; i++) lcd.write(' ');
}

void show(const ts::Result& r) {
  char a[17], b[17];
  char f[6], d[6];
  dtostrf(r.freq_hz, 3, 1, f);
  dtostrf(r.disp_cm, 3, 1, d);
  if (r.grade == 0) snprintf(a, sizeof a, "No tremor");
  else snprintf(a, sizeof a, "Grade %d  %sHz", r.grade, f);
  if (app_mode || sim_grade) {
    // Mark app mode (A) or the test signal (S) in the last column.
    uint8_t n = strlen(a);
    while (n < 15) a[n++] = ' ';
    a[15] = sim_grade ? 'S' : 'A';
    a[16] = 0;
  }
  if (app_mode && app_top[0]) snprintf(a, sizeof a, "%s", app_top);
  if (app_mode && app_text[0]) snprintf(b, sizeof b, "%s", app_text);
  else if (r.moving) snprintf(b, sizeof b, "Moving: paused");
  else if (r.cue) snprintf(b, sizeof b, "%scm  Cue %d", d, r.cue);
  else if (r.grade) snprintf(b, sizeof b, "%scm  No cue", d);
  else snprintf(b, sizeof b, "Hand still");
  lcd.setCursor(0, 0);
  print_padded(a);
  lcd.setCursor(0, 1);
  print_padded(b);
}

void handle_line(char* s) {
  char cmd = s[0];
  char* arg = s[1] == ',' ? s + 2 : s + 1;
  last_app_ms = millis();
  switch (cmd) {
    case 'M':
      app_mode = atoi(arg) == 1;
      if (!app_mode) app_text[0] = app_top[0] = 0;
      break;
    case 'P': {
      int duty = atoi(arg);
      char* c = strchr(arg, ',');
      int ms = c ? atoi(c + 1) : 30;
      pulse(constrain(duty, 0, 255), constrain(ms, 0, 200));
      break;
    }
    case 'B': {
      int hz = atoi(arg);
      char* c = strchr(arg, ',');
      int ms = c ? atoi(c + 1) : 100;
      if (hz > 0) tone(BUZZER, constrain(hz, 100, 8000), constrain(ms, 1, 2000));
      break;
    }
    case 'T':
      strncpy(app_top, arg, 16);
      app_top[16] = 0;
      lcd.setCursor(0, 0);
      print_padded(app_top);
      break;
    case 'L':
      strncpy(app_text, arg, 16);
      app_text[16] = 0;
      lcd.setCursor(0, 1);
      print_padded(app_text);
      break;
    case 'V':
      plot_mode = atoi(arg) == 1;
      break;
    case 'S':
      sim_grade = constrain(atoi(arg), 0, 4);
      engine.reset();
      lcd.setCursor(0, 1);
      print_padded(sim_grade ? "Test signal on" : "Sensor input");
      break;
    case 'K':
      analogWrite(LCD_CONTRAST, constrain(atoi(arg), 0, 255));
      break;
  }
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

void setup() {
  // Motor off before anything else, so it can't twitch at power-up.
  pinMode(MOTOR, OUTPUT);
  digitalWrite(MOTOR, LOW);
  pinMode(BUZZER, OUTPUT);
  pinMode(LCD_CONTRAST, OUTPUT);
  analogWrite(LCD_CONTRAST, CONTRAST_DEFAULT);

  Serial.begin(115200);
  lcd.begin(16, 2);
  lcd.setCursor(0, 0);
  print_padded("TremorSense");
  lcd.setCursor(0, 1);
  print_padded("Hold hand still");
  tone(BUZZER, 1800, 80);
  delay(120);
  tone(BUZZER, 2400, 80);

  Serial.print("H,TremorSense-Uno,");
  Serial.println(VERSION);
  next_sample_us = micros();
}

void loop() {
  read_serial();
  if (app_mode && millis() - last_app_ms > APP_TIMEOUT_MS) {
    app_mode = false;   // app went away: carry on standalone
    app_text[0] = app_top[0] = 0;
  }
  if (pulsing && (long)(millis() - pulse_end_ms) >= 0) motor_off();

  if ((long)(micros() - next_sample_us) < 0) return;
  next_sample_us += SAMPLE_US;

  int x = analogRead(ACC_X);
  int y = analogRead(ACC_Y);
  int z = analogRead(ACC_Z);
  if (sim_grade) sim_counts(&x, &y, &z);
  if (app_mode) {
    Serial.print("A,");
    Serial.print(x);
    Serial.print(',');
    Serial.print(y);
    Serial.print(',');
    Serial.println(z);
  }

  bool block = engine.push(x, y, z);
  if (!app_mode && engine.should_fire()) pulse(engine.pulse_duty(), engine.pulse_ms());
  if (plot_mode && !app_mode) {
    Serial.print("tremor:");
    Serial.print((int)(engine.phase_signal() * 10));
    Serial.print(" motor:");
    Serial.println(pulsing ? 20 : 0);
  }

  if (block) {
    const ts::Result& r = engine.result();
    show(r);
    if (plot_mode && !app_mode) {
      if (!app_mode && r.cue && !last_cue) tone(BUZZER, 2000, 60);
      last_cue = r.cue;
      return;
    }
    Serial.print("G,");
    Serial.print(r.grade);
    Serial.print(',');
    Serial.print((int)(r.freq_hz * 100));
    Serial.print(',');
    Serial.print((int)(r.disp_cm * 100));
    Serial.print(',');
    Serial.print(r.moving ? 1 : 0);
    Serial.print(',');
    Serial.println(r.cue);
    Serial.print("D,");
    Serial.print((long)(engine.diag_low() * 100));
    Serial.print(',');
    Serial.print((long)(engine.diag_tremor() * 100));
    Serial.print(',');
    Serial.print((int)(engine.diag_prominence() * 100));
    Serial.print(',');
    Serial.println(sim_grade);
    // Short beep when standalone cueing switches on.
    if (!app_mode && r.cue && !last_cue) tone(BUZZER, 2000, 60);
    last_cue = r.cue;
  }
}
