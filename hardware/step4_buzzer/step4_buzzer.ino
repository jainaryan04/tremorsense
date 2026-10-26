// Step 4: piezo buzzer test. You should hear a rising three-note chirp
// every two seconds.
#include <LiquidCrystal.h>

const int LCD_RS = 12, LCD_E = 11, LCD_D4 = 5, LCD_D5 = 4, LCD_D6 = 3, LCD_D7 = 2;
const int LCD_CONTRAST = 6, CONTRAST = 60;   // use your value from step 1
const int BUZZER = 8;

LiquidCrystal lcd(LCD_RS, LCD_E, LCD_D4, LCD_D5, LCD_D6, LCD_D7);

void setup() {
  Serial.begin(115200);
  pinMode(LCD_CONTRAST, OUTPUT);
  analogWrite(LCD_CONTRAST, CONTRAST);
  lcd.begin(16, 2);
  lcd.print("Buzzer test");
}

void loop() {
  const int notes[3] = {1500, 2000, 2500};
  for (int i = 0; i < 3; i++) {
    lcd.setCursor(0, 1);
    lcd.print(notes[i]);
    lcd.print(" Hz   ");
    Serial.println(notes[i]);
    tone(BUZZER, notes[i], 150);
    delay(200);
  }
  delay(2000);
}
