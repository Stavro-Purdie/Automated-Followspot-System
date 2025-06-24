#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// === OLED display constants ===
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET    -1
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// === Beacon frequency configuration ===
#define BASE_FREQ_HZ   30        // Minimum frequency (Hz)
#define FREQ_STEP_HZ   5         // Steps between IDs
#define PULSE_WIDTH_MS 3         // Pulse width in ms

// === Pin assignments (XIAO ESP32-C3) ===
constexpr uint8_t IR_LED_PIN        = 6;  // Output to IR LED driver
constexpr uint8_t BATTERY_PIN       = 3;  // Analog read from voltage divider
constexpr uint8_t BUTTON_PIN        = 0;  // Momentary push button
constexpr uint8_t I2C_SDA_PIN       = 4;  // I2C SDA
constexpr uint8_t I2C_SCL_PIN       = 5;  // I2C SCL

// === Battery voltage configuration ===
const float MAX_BAT_V = 4.20;             // Full battery voltage
const float MIN_BAT_V = 3.40;             // 0% display threshold
const float CUTOFF_V  = 3.35;             // Critical shutdown voltage

// === Brightness levels (PWM values) ===
uint8_t brightnessLevels[] = { 0, 32, 64, 128, 192, 255 };   // 0% to 100%
uint8_t brightnessIndex = 5;                   // Start at full brightness
uint8_t beaconID = 3;                          // Beacon ID (0–15)

// === Button state ===
bool btnPrev = HIGH;
unsigned long btnMillis = 0;

// === Menu system state ===
bool inMenu = false;
uint8_t menuIndex = 0;
unsigned long menuEntryTime = 0;

// === Battery voltage logging ===
#define HIST_LEN 120                         // 2 minutes @ 1 Hz
float batHist[HIST_LEN];
uint16_t histIdx = 0;
bool lowBattLatch = false;

// === Pulse timing ===
unsigned long lastPulseUs = 0;

void setup() {
  pinMode(IR_LED_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  analogWrite(IR_LED_PIN, 0);
  analogReadResolution(12);
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);

  // Initialize display
  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  display.clearDisplay();
  display.setTextSize(2);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 10);
  display.print("Beacon ");
  display.println(beaconID);
  display.display();
  delay(1500);

  // Fill battery history with full voltage
  for (uint16_t i = 0; i < HIST_LEN; ++i) batHist[i] = MAX_BAT_V;
}

void loop() {
  // Calculate dynamic pulse interval based on ID
  float freq = BASE_FREQ_HZ + (beaconID * FREQ_STEP_HZ);
  unsigned long interval = 1e6 / freq;
  unsigned long nowUs = micros();

  // Pulse IR LED if not in menu and battery is OK
  if (!lowBattLatch && !inMenu && (nowUs - lastPulseUs) >= interval) {
    lastPulseUs = nowUs;
    analogWrite(IR_LED_PIN, brightnessLevels[brightnessIndex]);
    delay(PULSE_WIDTH_MS);
    analogWrite(IR_LED_PIN, 0);
  }

  // Update battery voltage once per second
  static unsigned long lastBatMs = 0;
  if (millis() - lastBatMs >= 1000) {
    lastBatMs = millis();
    float v = readBattery();
    batHist[histIdx] = v;
    histIdx = (histIdx + 1) % HIST_LEN;

    // Shutdown LED if voltage too low
    if (v <= CUTOFF_V && !lowBattLatch) {
      lowBattLatch = true;
      analogWrite(IR_LED_PIN, 0);
    }

    // Update screen unless menu is active
    if (!inMenu) updateDisplay(v, freq);
  }

  // Handle menu and brightness button logic
  handleButton();
}

// === Reads voltage from divider ===
float readBattery() {
  uint16_t raw = analogRead(BATTERY_PIN);
  float v = (raw / 4095.0f) * 3.3f * 2.0f; // 1:1 divider
  return v;
}

// === Handles short and long button press ===
void handleButton() {
  static unsigned long pressStart = 0;
  bool reading = digitalRead(BUTTON_PIN);

  // Start hold detection
  if (btnPrev == HIGH && reading == LOW) {
    pressStart = millis();
  }

  // Trigger menu on long press
  if (btnPrev == LOW && reading == LOW) {
    if ((millis() - pressStart) > 1500 && !inMenu) {
      inMenu = true;
      menuIndex = 0;
      menuEntryTime = millis();
      showMenu();
    }
  }

  // Short tap: apply action, cycle menu
  if (btnPrev == LOW && reading == HIGH && inMenu) {
    applyMenuOption();
    menuIndex = (menuIndex + 1) % 3;
    menuEntryTime = millis();
    showMenu();
  }

  // Exit menu after 6 seconds idle
  if (inMenu && millis() - menuEntryTime > 6000) {
    inMenu = false;
  }

  btnPrev = reading;
}

// === Executes selected menu action ===
void applyMenuOption() {
  switch(menuIndex) {
    case 0: // Toggle brightness
      brightnessIndex = (brightnessIndex + 1) % (sizeof(brightnessLevels) / sizeof(brightnessLevels[0]));
      break;
    case 1: // Turn off beacon
      brightnessIndex = 0;
      break;
    case 2: // Increment beacon ID
      beaconID = (beaconID + 1) % 16;
      break;
  }
}

// === Shows menu selection screen ===
void showMenu() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(0,0);
  display.println("-- MENU --");
  display.setCursor(0, 10);
  display.print((menuIndex == 0) ? "> " : "  "); display.println("Brightness");
  display.print((menuIndex == 1) ? "> " : "  "); display.println("Power Off");
  display.print((menuIndex == 2) ? "> " : "  "); display.print("ID: "); display.println(beaconID);
  display.display();
}

// === Updates standard screen with voltage and status ===
void updateDisplay(float v, float freq) {
  if (lowBattLatch) {
    // Flashing low battery warning
    static bool invert = false;
    invert = !invert;
    display.clearDisplay();
    display.setTextColor(invert ? SSD1306_BLACK : SSD1306_WHITE, invert ? SSD1306_WHITE : SSD1306_BLACK);
    display.setTextSize(2);
    display.setCursor(0, 18);
    display.println("LOW BATT!");
    display.display();
    delay(300);
    return;
  }

  // Battery percentage
  int pct = constrain(map(v * 100, MIN_BAT_V * 100, MAX_BAT_V * 100, 0, 100), 0, 100);

  // Runtime estimate
  float oldest = batHist[(histIdx + 1) % HIST_LEN];
  float delta = oldest - v;
  float estMin = (delta > 0.005f) ? ((v - CUTOFF_V) / delta) * (HIST_LEN / 60.0f) : 999.0f;

  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0,0);
  display.print("ID:" ); display.print(beaconID);
  display.print("  ");
  display.print(freq, 0); display.println("Hz");

  display.setCursor(0,10);
  display.print("Batt: "); display.print(pct); display.println("%");
  display.setCursor(0,20);
  display.print("Volt: "); display.print(v,2); display.println("V");
  display.setCursor(0,30);
  display.print("Time: ");
  if (estMin < 998) { display.print(estMin,0); display.print("m"); }
  else { display.println("--"); }

  // Battery bar
  display.drawRect(0, 54, 128, 10, SSD1306_WHITE);
  int bar = map(pct, 0,100, 0,126);
  display.fillRect(1, 55, bar, 8, SSD1306_WHITE);

  display.display();
}
