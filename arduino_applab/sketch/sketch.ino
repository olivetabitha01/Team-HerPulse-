/*
  HerPulse — UNO Q Sketch (MCU / real-time side) — v2
  Corrected against your actual circuit diagram:
    - 3 motor drivers / 5 motors total (was wrongly modeled as 2/4 before)
    - Parallel HD44780 LCD (was wrongly coded as I2C before)
    - Single battery + rocker switch + buck converter power (not split
      USB-C/12V as I'd guessed earlier)

  ============================================================
  ⚠️  PIN NUMBERS BELOW ARE PLACEHOLDERS — YOUR DIAGRAM'S PIN TEXT
      IS NOT READABLE AT THE RESOLUTION IT WAS EXPORTED AT. I tried an
      8x zoom directly on the header and it's an unreadable blur, not
      something a sharper crop fixes — the detail just isn't in the
      file. Rather than guess wire-color-to-pin mapping and risk you
      flashing something that drives a channel wrong, every #define
      below needs your eyes before upload. Fastest fix: just type out
      the pin list as text (like you did for the first sketch) — much
      more reliable than me reading a diagram.
  ============================================================
*/

#include <Arduino_RouterBridge.h>
#include <Wire.h>
#include <LiquidCrystal.h>          // parallel LCD, not I2C
#include "Adafruit_TCS34725.h"      // RGB sensor — swap if yours differs

// ---------------------------------------------------------------- pins
// TODO: replace every value below with your actual pin from the diagram.

#define PIN_BUTTON        2

// Parallel LCD (HD44780-style, matches the many-pin display in your diagram)
// Standard 6-wire hookup: RS, E, D4, D5, D6, D7
#define LCD_RS  A5
#define LCD_EN  A4
#define LCD_D4  4
#define LCD_D5  5
#define LCD_D6  6
#define LCD_D7  7
LiquidCrystal lcd(LCD_RS, LCD_EN, LCD_D4, LCD_D5, LCD_D6, LCD_D7);

// MOSFET-switched loads (fan + 2 LED strips) — matches the 3 discrete
// TO-220 MOSFETs with series gate resistors visible in your diagram
#define PIN_FAN_GATE       A3
#define PIN_LED1_GATE      A2
#define PIN_LED2_GATE      A1

// Driver A — the two "up" motors (rack & pinion + syringe actuator)
#define PIN_DRVA_IN1       13
#define PIN_DRVA_IN2       A0
#define PIN_DRVA_ENA       3
#define PIN_DRVA_IN3       11
#define PIN_DRVA_IN4       10
#define PIN_DRVA_ENB       9

// Driver B — single motor: RGB sensor scan carriage
// (this is the motor I'd missed entirely in the first version)
#define PIN_DRVB_IN1       8
#define PIN_DRVB_IN2       7
#define PIN_DRVB_ENA       6

// Driver C — the two yellow TT disposal motors
#define PIN_DRVC_IN1       12
#define PIN_DRVC_IN2       A6   // UNO Q may expose extra analog-only pins here
#define PIN_DRVC_ENA       5
#define PIN_DRVC_IN3       A7
#define PIN_DRVC_IN4       A8
#define PIN_DRVC_ENB       A9

// ---------------------------------------------------- timing (TUNE THESE)
#define ROTATE_180_MS      900
#define ROTATE_90_MS       450
#define SYRINGE_RUN_MS     4000
#define RACK_DOWN_MS       3000
#define REACTION_MS        30000
#define LED_WARMUP_MS      10000
#define SCAN_MOVE_MS       1200

Adafruit_TCS34725 tcs = Adafruit_TCS34725(TCS34725_INTEGRATIONTIME_50MS, TCS34725_GAIN_4X);

uint16_t r_hb, g_hb, b_hb;
uint16_t r_protein, g_protein, b_protein;
uint16_t r_ph, g_ph, b_ph;

// -------------------------------------------------------------- lcd helper

void lcdStatus(const char* line) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(line);
}

void lcdTwoLine(const char* line1, const char* line2) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(line1);
  lcd.setCursor(0, 1);
  lcd.print(line2);
}

// ---------------------------------------------------------- motor helpers

void driverA_Motor1(int a, int b) { digitalWrite(PIN_DRVA_IN1, a); digitalWrite(PIN_DRVA_IN2, b); }
void driverA_Motor2(int a, int b) { digitalWrite(PIN_DRVA_IN3, a); digitalWrite(PIN_DRVA_IN4, b); }
void driverA_Stop()               { driverA_Motor1(LOW, LOW); driverA_Motor2(LOW, LOW); }

void driverB_Motor(int a, int b)  { digitalWrite(PIN_DRVB_IN1, a); digitalWrite(PIN_DRVB_IN2, b); }
void driverB_Stop()                { driverB_Motor(LOW, LOW); }

void driverC_Motor1(int a, int b) { digitalWrite(PIN_DRVC_IN1, a); digitalWrite(PIN_DRVC_IN2, b); }
void driverC_Motor2(int a, int b) { digitalWrite(PIN_DRVC_IN3, a); digitalWrite(PIN_DRVC_IN4, b); }
void driverC_Stop()                { driverC_Motor1(LOW, LOW); driverC_Motor2(LOW, LOW); }

// ------------------------------------------------------- sequence steps

void runSyringes() {
  driverA_Motor1(HIGH, LOW);   // rack & pinion down
  delay(RACK_DOWN_MS);
  driverA_Stop();

  driverA_Motor2(HIGH, LOW);   // syringe actuator — dispense 3 reagents
  delay(SYRINGE_RUN_MS);
  driverA_Stop();
}

void readRGBInto(uint16_t &r, uint16_t &g, uint16_t &b) {
  uint16_t clear, colorTemp;
  tcs.getRawData(&r, &g, &b, &clear);
  (void)colorTemp;
}

void scanPad() {
  delay(300);
  readRGBInto(r_hb, g_hb, b_hb);            // zone 1 — Hb

  driverB_Motor(HIGH, LOW);                 // move to zone 2
  delay(SCAN_MOVE_MS);
  driverB_Stop();
  delay(300);
  readRGBInto(r_protein, g_protein, b_protein);

  driverB_Motor(HIGH, LOW);                 // move to zone 3
  delay(SCAN_MOVE_MS);
  driverB_Stop();
  delay(300);
  readRGBInto(r_ph, g_ph, b_ph);

  driverB_Motor(LOW, HIGH);                 // return carriage home
  delay(SCAN_MOVE_MS * 2);
  driverB_Stop();
}

void runDisposal() {
  driverC_Motor1(HIGH, LOW);   // 180° close
  delay(ROTATE_180_MS);
  driverC_Stop();

  driverC_Motor2(LOW, HIGH);   // 90° dispose
  delay(ROTATE_90_MS);
  driverC_Stop();
}

void runFanAndLED() {
  digitalWrite(PIN_FAN_GATE, HIGH);
  digitalWrite(PIN_LED1_GATE, HIGH);
  digitalWrite(PIN_LED2_GATE, HIGH);
  delay(5000);
  digitalWrite(PIN_FAN_GATE, LOW);
  digitalWrite(PIN_LED1_GATE, LOW);
  digitalWrite(PIN_LED2_GATE, LOW);
}

// --------------------------------------------------------------- bridge

bool push_reading() {
  float ack;
  Bridge.call("receive_reading",
              (float)r_hb, (float)g_hb, (float)b_hb,
              (float)r_protein, (float)g_protein, (float)b_protein,
              (float)r_ph, (float)g_ph, (float)b_ph)
      .result(ack);
  return true;
}

// Called from Python once at startup so the board's own IP shows on the
// LCD — this is what makes it easy to find the device on the network
// without needing a laptop nearby to run `ipconfig`.
bool show_ip(String ip) {
  lcdTwoLine("HerPulse ready", ip.c_str());
  delay(4000);
  lcdStatus("IDLE");
  return true;
}

// --------------------------------------------------------------- setup

void setup() {
  Bridge.begin();
  Monitor.begin(115200);

  pinMode(PIN_BUTTON, INPUT_PULLUP);
  pinMode(PIN_FAN_GATE, OUTPUT);
  pinMode(PIN_LED1_GATE, OUTPUT);
  pinMode(PIN_LED2_GATE, OUTPUT);

  pinMode(PIN_DRVA_IN1, OUTPUT); pinMode(PIN_DRVA_IN2, OUTPUT); pinMode(PIN_DRVA_ENA, OUTPUT);
  pinMode(PIN_DRVA_IN3, OUTPUT); pinMode(PIN_DRVA_IN4, OUTPUT); pinMode(PIN_DRVA_ENB, OUTPUT);
  digitalWrite(PIN_DRVA_ENA, HIGH);
  digitalWrite(PIN_DRVA_ENB, HIGH);

  pinMode(PIN_DRVB_IN1, OUTPUT); pinMode(PIN_DRVB_IN2, OUTPUT); pinMode(PIN_DRVB_ENA, OUTPUT);
  digitalWrite(PIN_DRVB_ENA, HIGH);

  pinMode(PIN_DRVC_IN1, OUTPUT); pinMode(PIN_DRVC_IN2, OUTPUT); pinMode(PIN_DRVC_ENA, OUTPUT);
  pinMode(PIN_DRVC_IN3, OUTPUT); pinMode(PIN_DRVC_IN4, OUTPUT); pinMode(PIN_DRVC_ENB, OUTPUT);
  digitalWrite(PIN_DRVC_ENA, HIGH);
  digitalWrite(PIN_DRVC_ENB, HIGH);

  Wire.begin();
  tcs.begin();

  lcd.begin(16, 2);
  lcdStatus("BOOTING");

  Bridge.provide("show_ip", show_ip);

  lcdStatus("IDLE");
}

// ---------------------------------------------------------------- loop

void loop() {
  Bridge.update();

  if (digitalRead(PIN_BUTTON) == LOW) {
    lcdStatus("DETECTING");
    digitalWrite(PIN_LED1_GATE, HIGH);
    digitalWrite(PIN_LED2_GATE, HIGH);
    delay(LED_WARMUP_MS);

    bool detected = false;
    Bridge.call("check_pad").result(detected);

    if (!detected) {
      lcdStatus("NO PAD");
      digitalWrite(PIN_LED1_GATE, LOW);
      digitalWrite(PIN_LED2_GATE, LOW);
      delay(2000);
      lcdStatus("IDLE");
      return;
    }

    lcdStatus("INJECTING");
    runSyringes();

    lcdStatus("REACTING");
    delay(REACTION_MS);

    lcdStatus("SCANNING");
    scanPad();

    lcdStatus("PROCESSING");
    push_reading();

    lcdStatus("DISPOSING");
    runDisposal();

    lcdStatus("DONE");
    runFanAndLED();
    delay(2000);
    lcdStatus("IDLE");
  }
}
