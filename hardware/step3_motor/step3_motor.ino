// Step 3: vibration motor test through the IRF540 MOSFET.
// The motor should give a weak, medium and strong buzz, then rest.
#include <LiquidCrystal.h>

const int LCD_RS = 12, LCD_E = 11, LCD_D4 = 5, LCD_D5 = 4, LCD_D6 = 3, LCD_D7 = 2;
const int LCD_CONTRAST = 6, CONTRAST = 60;   // use your value from step 1
const int MOTOR = 9;

LiquidCrystal lcd(LCD_RS, LCD_E, LCD_D4, LCD_D5, LCD_D6, LCD_D7);

void show(const char* a, const char* b) {
  lcd.clear();
  lcd.print(a);
  lcd.setCursor(0, 1);
  lcd.print(b);
  Serial.print(a);
  Serial.print(" ");
  Serial.println(b);
}

void setup() {
  pinMode(MOTOR, OUTPUT);
  digitalWrite(MOTOR, LOW);   // motor off first
  Serial.begin(115200);
  pinMode(LCD_CONTRAST, OUTPUT);
  analogWrite(LCD_CONTRAST, CONTRAST);
  lcd.begin(16, 2);
}

void loop() {
  const int duty[3] = {160, 210, 255};
  const char* name[3] = {"Weak (grade 2)", "Medium (grade 3)", "Strong (grade 4)"};
  for (int i = 0; i < 3; i++) {
    show("Motor test", name[i]);
    analogWrite(MOTOR, duty[i]);
    delay(700);
    analogWrite(MOTOR, 0);
    delay(800);
  }
  // Short pulses at 5 per second, like a tremor cue.
  show("Motor test", "Pulses 5/s");
  for (int i = 0; i < 15; i++) {
    analogWrite(MOTOR, 255);
    delay(45);
    analogWrite(MOTOR, 0);
    delay(155);
  }
  show("Motor test", "Rest");
  delay(2000);
}
