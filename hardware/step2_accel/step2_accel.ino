// Step 2: GY-61 accelerometer test. Keeps the LCD from step 1 connected.
// Lay the sensor flat: Z should read about +1 g, X and Y about 0 g.
// Tilt it to check each axis. Values also go to the Serial Monitor (115200)
// and the Serial Plotter.
#include <LiquidCrystal.h>

const int LCD_RS = 12, LCD_E = 11, LCD_D4 = 5, LCD_D5 = 4, LCD_D6 = 3, LCD_D7 = 2;
const int LCD_CONTRAST = 6, CONTRAST = 0;    // your value from step 1
const int ACC_X = A0, ACC_Y = A1, ACC_Z = A2;

// GY-61 (ADXL335): about 1.65 V at 0 g and 0.33 V per g; Uno ADC is 5 V / 1023.
const float ZERO_G = 1.65 / 5.0 * 1023;   // ~338 counts
const float PER_G = 0.33 / 5.0 * 1023;    // ~67.5 counts per g

LiquidCrystal lcd(LCD_RS, LCD_E, LCD_D4, LCD_D5, LCD_D6, LCD_D7);

float to_g(int counts) { return (counts - ZERO_G) / PER_G; }

void setup() {
  Serial.begin(115200);
  pinMode(LCD_CONTRAST, OUTPUT);
  analogWrite(LCD_CONTRAST, CONTRAST);
  lcd.begin(16, 2);
}

void loop() {
  int x = analogRead(ACC_X), y = analogRead(ACC_Y), z = analogRead(ACC_Z);
  lcd.setCursor(0, 0);
  lcd.print("X");
  lcd.print(x);
  lcd.print(" Y");
  lcd.print(y);
  lcd.print(" Z");
  lcd.print(z);
  lcd.print("   ");
  lcd.setCursor(0, 1);
  lcd.print(to_g(x), 1);
  lcd.print(" ");
  lcd.print(to_g(y), 1);
  lcd.print(" ");
  lcd.print(to_g(z), 1);
  lcd.print(" g    ");
  Serial.print("x_g:");
  Serial.print(to_g(x), 2);
  Serial.print(" y_g:");
  Serial.print(to_g(y), 2);
  Serial.print(" z_g:");
  Serial.println(to_g(z), 2);
  delay(100);
}
