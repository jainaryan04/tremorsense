// Step 1: LCD test. Wire the JHD162A as in hardware/README.md, step 1.
// The contrast steps through values; note the one where the text is clearest
// (shown in the Serial Monitor at 115200 baud) and put it in CONTRAST_DEFAULT
// in tremorsense_uno/pins.h.
#include <LiquidCrystal.h>

const int LCD_RS = 12, LCD_E = 11, LCD_D4 = 5, LCD_D5 = 4, LCD_D6 = 3, LCD_D7 = 2;
const int LCD_CONTRAST = 6;

LiquidCrystal lcd(LCD_RS, LCD_E, LCD_D4, LCD_D5, LCD_D6, LCD_D7);

void setup() {
  Serial.begin(115200);
  pinMode(LCD_CONTRAST, OUTPUT);
  lcd.begin(16, 2);
  Serial.println("Step 1: LCD test. Watch the screen; note the clearest contrast value.");
}

void loop() {
  for (int c = 0; c <= 140; c += 10) {
    analogWrite(LCD_CONTRAST, c);
    lcd.clear();
    lcd.print("TremorSense LCD");
    lcd.setCursor(0, 1);
    lcd.print("Contrast ");
    lcd.print(c);
    Serial.print("Contrast ");
    Serial.println(c);
    delay(1500);
  }
}
