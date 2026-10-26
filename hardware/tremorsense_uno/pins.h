// Pin map shared by the test sketches and the firmware. See hardware/README.md.
#pragma once

// JHD162A 16x2 LCD, 4-bit mode.
const int LCD_RS = 12;
const int LCD_E = 11;
const int LCD_D4 = 5;
const int LCD_D5 = 4;
const int LCD_D6 = 3;
const int LCD_D7 = 2;
const int LCD_CONTRAST = 6;   // PWM into LCD pin 3 (V0); lower = darker

// GY-61 (ADXL335) analog accelerometer.
const int ACC_X = A0;
const int ACC_Y = A1;
const int ACC_Z = A2;

// Coin vibration motor through the IRF540 MOSFET (gate).
const int MOTOR = 9;

// Piezo buzzer.
const int BUZZER = 8;

// Change this if the text is too faint (raise) or shows solid blocks (lower).
const int CONTRAST_DEFAULT = 60;
