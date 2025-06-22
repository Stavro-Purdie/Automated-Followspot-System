#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET    -1
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// Pin definitions
const int IR_LED_PIN = 5;         // PWM output to MOSFET gate
const int BATTERY_PIN = A0;       // Analog input for battery voltage
const int BRIGHTNESS_BUTTON = 4;  // Digital input for toggling brightness

// Battery measurement constants
const float MAX_BATTERY_VOLTAGE = 4.2;
const float MIN_BATTERY_VOLTAGE = 3.6;
const float SHUTDOWN_VOLTAGE = 3.5;

// Brightness control
int brightnessLevels[] = {LOW, HIGH};
int currentBrightnessIndex = 0;
bool lastButtonState = HIGH;
unsigned long lastDebounceTime = 0;
const unsigned long debounceDelay = 50;

// Timing control
const int PULSE_FREQ = 60;        // Hz
unsigned long pulse_interval_us = 1000000 / PULSE_FREQ;
unsigned long last_pulse_time = 0;

// Battery logging
#define HISTORY_SIZE 120     // Store last 120 seconds of battery voltage for estimation
float batteryHistory[HISTORY_SIZE];
int historyIndex = 0;
bool warningShown = false;

void setup() {
  pinMode(IR_LED_PIN, OUTPUT);
  analogWrite(IR_LED_PIN, 0);

  pinMode(BRIGHTNESS_BUTTON, INPUT_PULLUP);

  Serial.begin(115200);

  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F("SSD1306 allocation failed"));
    while (true);
  }

  display.clearDisplay();
  display.setTextSize(2);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(10, 20);
  display.println("IR Beacon");
  display.display();
  delay(1500);

  for (int i = 0; i < HISTORY_SIZE; i++) {
    batteryHistory[i] = MAX_BATTERY_VOLTAGE;
  }
}

void loop() {
  updateBrightness();

  float voltage = analogRead(BATTERY_PIN) * (3.3 / 4095.0) * 2.0; // If using 1:1 divider
  batteryHistory[historyIndex] = voltage;
  historyIndex = (historyIndex + 1) % HISTORY_SIZE;

  if (voltage < SHUTDOWN_VOLTAGE) {
    analogWrite(IR_LED_PIN, 0);
    if (!warningShown) showLowBatteryWarning();
    return;
  }

  unsigned long now = micros();
  if (now - last_pulse_time >= pulse_interval_us) {
    last_pulse_time = now;
    pulseIR();
  }

  static unsigned long last_display_update = 0;
  if (millis() - last_display_update > 1000) {
    last_display_update = millis();
    updateDisplay(voltage);
  }
}

void pulseIR() {
  analogWrite(IR_LED_PIN, 255);  // Full duty pulse
  delayMicroseconds(100);        // Short pulse (~100 us)
  analogWrite(IR_LED_PIN, 0);
}

void updateDisplay(float voltage) {
  int batteryPercent = constrain(map(voltage * 100, MIN_BATTERY_VOLTAGE * 100, MAX_BATTERY_VOLTAGE * 100, 0, 100), 0, 100);

  // Estimate battery drain rate
  float oldestVoltage = batteryHistory[(historyIndex + 1) % HISTORY_SIZE];
  float delta = oldestVoltage - voltage;
  float estTimeMin = (delta > 0.01) ? ((voltage - SHUTDOWN_VOLTAGE) / delta) * HISTORY_SIZE / 60.0 : 999.0;

  display.clearDisplay();
  display.setTextSize(2);
  display.setCursor(10, 0);
  display.print(PULSE_FREQ);
  display.print(" Hz");

  display.setTextSize(1);
  display.setCursor(0, 20);
  display.print("Battery: ");
  display.print(batteryPercent);
  display.print("% (v=");
  display.print(voltage, 2);
  display.println("V)");

  display.setCursor(0, 30);
  display.print("Est time left: ");
  if (estTimeMin < 999.0) {
    display.print(estTimeMin, 1);
    display.println(" min");
  } else {
    display.println("--");
  }

  display.drawRect(0, 48, 128, 12, SSD1306_WHITE);
  int barWidth = map(batteryPercent, 0, 100, 0, 126);
  display.fillRect(1, 49, barWidth, 10, SSD1306_WHITE);

  display.display();
}

void updateBrightness() {
  bool reading = digitalRead(BRIGHTNESS_BUTTON);
  if (reading != lastButtonState) {
    lastDebounceTime = millis();
  }

  if ((millis() - lastDebounceTime) > debounceDelay) {
    if (reading == LOW && lastButtonState == HIGH) {
      currentBrightnessIndex = (currentBrightnessIndex + 1) % 2;
      analogWrite(IR_LED_PIN, brightnessLevels[currentBrightnessIndex] ? 255 : 128);
    }
  }

  lastButtonState = reading;
}

void showLowBatteryWarning() {
  warningShown = true;
  for (int i = 0; i < 10; i++) {
    display.clearDisplay();
    display.setTextSize(2);
    display.setTextColor((i % 2) ? SSD1306_BLACK : SSD1306_WHITE, SSD1306_WHITE);
    display.setCursor(10, 20);
    display.println("LOW BATTERY!");
    display.display();
    delay(500);
  }
}