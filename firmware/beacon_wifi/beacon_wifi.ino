#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WebServer.h>

// Optional INA219 current sensor library
#if __has_include(<Adafruit_INA219.h>)
  #include <Adafruit_INA219.h>
  #define HAS_INA219 1
#else
  #define HAS_INA219 0
#endif

#if __has_include("wifi_credentials.h")
#include "wifi_credentials.h"
#else
#define WIFI_SSID_DEFAULT ""
#define WIFI_PASS_DEFAULT ""
#define BEACON_NAME_DEFAULT "IR Beacon"
#endif

/********************************************************************
  Wi-Fi IR BEACON DRIVER – Xiao ESP32-C6
  ------------------------------------------------
  * Stores beacon ID, brightness, Wi-Fi credentials in NVS.
  * Simple HTTP API for status + config: /api/status, /api/config, /api/wifi
  * Falls back to SoftAP if STA connect fails (SSID: Beacon-Setup-<id>, pass: beacon1234)
  * Optional sensors: INA219 (current), ESP32-C6 internal temp, fan tach
********************************************************************/

/* ---------- USER CONSTANTS ---------- */
#define BASE_FREQ_HZ   30        // Hz for ID 0
#define FREQ_STEP_HZ   5         // Hz per ID step
#define PULSE_WIDTH_MS 3         // LED ON time (ms)
#define MAX_ID         15

// Sensor pins
constexpr uint8_t PIN_FAN_TACH = 7;   // Optional fan tachometer input

// INA219 configuration
constexpr uint8_t INA219_ADDR = 0x40;  // Default I2C address
constexpr float INA219_SHUNT_OHMS = 0.1f;  // Shunt resistor value (ohms)

/* ---------- DISPLAY ---------- */
#define OLED_W 128
#define OLED_H 64
#define OLED_RESET -1
Adafruit_SSD1306 display(OLED_W, OLED_H, &Wire, OLED_RESET);

/* ---------- PINS (XIAO ESP32-C6) ---------- */
constexpr uint8_t PIN_IRLED   = 6;   // MOSFET gate PWM
constexpr uint8_t PIN_VBAT    = 3;   // Analog read (divider)
constexpr uint8_t PIN_BTN     = 0;   // Single push-button
constexpr uint8_t PIN_SDA     = 4;
constexpr uint8_t PIN_SCL     = 5;

/* ---------- BATTERY ---------- */
const float VBAT_MAX = 4.20;
const float VBAT_MIN = 3.40;         // 0 % display
const float VBAT_CUT = 3.35;         // kill LED + warn

/* ---------- BRIGHTNESS ---------- */
uint8_t lvl[] = {0, 32, 64, 128, 192, 255};  // PWM table 0–100 %
uint8_t lvlIdx = 5;                          // full by default

/* ---------- STATE ---------- */
Preferences prefs;          // flash settings
uint8_t beaconID   = 0;     // loaded from flash
bool    ledEnable  = true;
bool    lowBatt    = false;

/* ---------- WIFI ---------- */
String wifiSsid = WIFI_SSID_DEFAULT;
String wifiPass = WIFI_PASS_DEFAULT;
String beaconName = BEACON_NAME_DEFAULT;
WebServer server(80);
bool wifiReady = false;
String lastTelemetryBody = "{}";
float uiBatteryVoltage = VBAT_MAX;
int uiBatteryPercent = 100;
unsigned long uiLastDrawMs = 0;

struct TelemetrySnapshot {
  float batteryVoltage;
  int batteryPercent;
  float wifiRssiDbm;
  String wifiSsid;
  uint32_t uptimeSeconds;
  uint8_t ledBrightnessPct;
  bool ledEnabled;
  float currentAmps;
  float temperatureC;
  uint32_t fanRpm;
};

/* ---------- BUTTON ---------- */
bool btnPrev = HIGH;        // previous physical state
unsigned long btnStart = 0; // press timer
bool menuMode = false;
uint8_t menuIdx = 0;
unsigned long menuT = 0;

/* ---------- BATTERY HISTORY ---------- */
#define HIST 120            // 120 s history
float vHist[HIST];
uint16_t vPtr = 0;

/* ---------- SENSOR STATE ---------- */
#if HAS_INA219
Adafruit_INA219 ina219(INA219_ADDR);
bool hasINA219 = false;
float ina219_current_amps = 0.0f;
#endif

// ESP32-C6 internal temperature sensor
float internal_temp_c = 0.0f;
bool hasInternalTemp = false;

// Fan tachometer
volatile uint32_t fanPulseCount = 0;
uint32_t fanRpm = 0;
unsigned long lastFanRpmCalc = 0;
bool hasFanTach = false;

/* ---------- BUTTON ---------- */
bool btnPrev = HIGH;        // previous physical state
unsigned long btnStart = 0; // press timer
bool menuMode = false;
uint8_t menuIdx = 0;
unsigned long menuT = 0;

/* ---------- BATTERY HISTORY ---------- */
#define HIST 120            // 120 s history
float vHist[HIST];
uint16_t vPtr = 0;

/* ---------- TIMING ---------- */
unsigned long lastPulseUs = 0;

/* ================================================================ */
void loadSettings() {
  prefs.begin("beacon", false);
  beaconID = prefs.getUChar("id", 0);
  lvlIdx   = prefs.getUChar("bri", 5);
  wifiSsid = prefs.getString("ssid", WIFI_SSID_DEFAULT);
  wifiPass = prefs.getString("pass", WIFI_PASS_DEFAULT);
  beaconName = prefs.getString("name", BEACON_NAME_DEFAULT);
  prefs.end();
}

void saveSettings() {
  prefs.begin("beacon", false);
  prefs.putUChar("id",  beaconID);
  prefs.putUChar("bri", lvlIdx);
  prefs.putString("ssid", wifiSsid);
  prefs.putString("pass", wifiPass);
  prefs.putString("name", beaconName);
  prefs.end();
}

/* ================================================================ */
bool connectSta() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());
  for (int i = 0; i < 80 && WiFi.status() != WL_CONNECTED; i++) {
    delay(125);
  }
  return WiFi.status() == WL_CONNECTED;
}

void startApFallback() {
  String apName = String("Beacon-Setup-") + String(beaconID);
  WiFi.mode(WIFI_AP);
  WiFi.softAP(apName.c_str(), "beacon1234");
}

String safeName(const String &src) {
  String out = src;
  out.replace("\"", "'");
  if (out.length() > 24) {
    out = out.substring(0, 24);
  }
  return out;
}

String escapeJson(const String &src) {
  String out;
  for (size_t i = 0; i < src.length(); i++) {
    char c = src[i];
    switch (c) {
      case '\\': out += "\\\\"; break;
      case '"': out += "\\\""; break;
      case '\n': out += "\\n"; break;
      case '\r': out += "\\r"; break;
      case '\t': out += "\\t"; break;
      default: out += c; break;
    }
  }
  return out;
}

void drawFrameChrome(unsigned long nowMs, bool warningMode) {
  int pulse = (nowMs / 180) % 8;
  int borderInset = warningMode ? 0 : 1;
  display.drawRect(borderInset, borderInset, OLED_W - borderInset * 2, OLED_H - borderInset * 2, SSD1306_WHITE);
  display.drawRect(borderInset + 1, borderInset + 1, OLED_W - (borderInset + 1) * 2, OLED_H - (borderInset + 1) * 2, SSD1306_WHITE);

  for (int x = 6; x < OLED_W - 6; x += 18) {
    display.drawPixel(x, 5 + (pulse % 3), SSD1306_WHITE);
  }

  for (int y = 8; y < OLED_H - 8; y += 16) {
    display.drawPixel(OLED_W - 7 - (pulse % 2), y, SSD1306_WHITE);
  }
}

void drawProgressBar(int x, int y, int w, int h, int pct, bool highlight) {
  pct = constrain(pct, 0, 100);
  display.drawRect(x, y, w, h, SSD1306_WHITE);
  int fillWidth = (w - 2) * pct / 100;
  if (fillWidth > 0) {
    display.fillRect(x + 1, y + 1, fillWidth, h - 2, SSD1306_WHITE);
  }
  if (highlight && fillWidth > 0) {
    display.drawFastVLine(x + 1 + fillWidth - 1, y + 1, h - 2, SSD1306_BLACK);
  }
}

void drawBootScreen() {
  display.clearDisplay();
  display.fillRect(0, 0, OLED_W, 10, SSD1306_WHITE);
  display.setTextColor(SSD1306_BLACK);
  display.setTextSize(1);
  display.setCursor(6, 1);
  display.print("IR BEACON SYSTEM");
  display.setTextColor(SSD1306_WHITE);
  display.drawRect(2, 14, OLED_W - 4, 48, SSD1306_WHITE);
  display.fillRect(6, 18, 24, 24, SSD1306_WHITE);
  display.setTextColor(SSD1306_BLACK);
  display.setTextSize(2);
  display.setCursor(11, 22);
  display.print("B");
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(38, 20);
  display.print("Name:");
  display.setCursor(38, 30);
  display.print(safeName(beaconName));
  display.setCursor(38, 42);
  display.print("ID ");
  display.print(beaconID);
  display.print("  Warming up");
  display.drawFastHLine(6, 54, 116, SSD1306_WHITE);
  display.fillRect(6, 56, 64, 4, SSD1306_WHITE);
  display.display();
}

void drawDashboardScreen(float batteryVoltage, int batteryPercent, float freqHz) {
  unsigned long nowMs = millis();
  int pulse = (nowMs / 140) % 10;
  int barWidth = 44 + pulse;

  display.clearDisplay();
  drawFrameChrome(nowMs, false);

  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(6, 6);
  display.print(safeName(beaconName));

  display.setCursor(6, 17);
  display.print("ID ");
  display.print(beaconID);
  display.print("  ");
  display.print((int)freqHz);
  display.print("Hz");

  display.fillRect(84, 4, 38, 10, SSD1306_WHITE);
  display.setTextColor(SSD1306_BLACK);
  display.setCursor(87, 6);
  display.print(WiFi.isConnected() ? "LIVE" : "AP");
  display.setTextColor(SSD1306_WHITE);

  display.setCursor(6, 29);
  display.print("BAT");
  display.setCursor(6, 39);
  display.print(batteryVoltage, 2);
  display.print("V");
  drawProgressBar(44, 34, 76, 9, batteryPercent, true);
  display.setCursor(46, 46);
  display.print(batteryPercent);
  display.print("%");

  display.drawRoundRect(6, 50, 38, 10, 3, SSD1306_WHITE);
  display.fillRect(8, 52, constrain(barWidth, 0, 34), 6, SSD1306_WHITE);

  display.setCursor(54, 52);
  display.print(WiFi.isConnected() ? WiFi.localIP().toString() : String("AP:") + String(beaconID));

  // Sensor status line
  display.setCursor(54, 60);
  display.setTextSize(1);
  if (hasInternalTemp) {
    display.print(internal_temp_c, 1);
    display.print("C ");
  }
  if (hasINA219) {
    display.print(ina219_current_amps * 1000, 0);
    display.print("mA ");
  }
  if (hasFanTach) {
    display.print(fanRpm);
    display.print("RPM ");
  }

  display.drawFastHLine(6, 26, 116, SSD1306_WHITE);
  display.drawPixel(123, 6 + pulse % 3, SSD1306_WHITE);
  display.drawPixel(121, 8 + pulse % 2, SSD1306_WHITE);
  display.display();
}

void drawMenuScreen() {
  unsigned long nowMs = millis();
  int pulse = (nowMs / 220) % 2;

  display.clearDisplay();
  display.fillRect(0, 0, OLED_W, 12, SSD1306_WHITE);
  display.setTextColor(SSD1306_BLACK);
  display.setTextSize(1);
  display.setCursor(5, 2);
  display.print("SYSTEM MENU");
  display.setTextColor(SSD1306_WHITE);

  drawFrameChrome(nowMs, false);

  const char *labels[3] = {"BRIGHTNESS", "IR OUTPUT", "BEACON ID"};
  for (int i = 0; i < 3; i++) {
    int y = 18 + i * 13;
    bool selected = (menuIdx == i);
    if (selected) {
      display.fillRoundRect(4, y - 1, 120, 11, 3, SSD1306_WHITE);
      display.setTextColor(SSD1306_BLACK);
    } else {
      display.drawRoundRect(4, y - 1, 120, 11, 3, SSD1306_WHITE);
      display.setTextColor(SSD1306_WHITE);
    }
    display.setCursor(9, y + 1);
    display.print(selected && pulse ? ">" : " ");
    display.print(labels[i]);
    display.setCursor(82, y + 1);
    if (i == 0) {
      display.print(map(lvlIdx, 0, 5, 0, 100));
      display.print("%");
    } else if (i == 1) {
      display.print(ledEnable ? "ARMED" : "OFF");
    } else {
      display.print(beaconID);
    }
  }

  display.setTextColor(SSD1306_WHITE);
  display.setCursor(5, 57);
  display.print("Tap to cycle  Hold to exit");
  display.display();
}

void drawWarningScreen(const String &headline, const String &detail) {
  unsigned long nowMs = millis();
  bool flash = ((nowMs / 240) % 2) == 0;

  display.clearDisplay();
  if (flash) {
    display.fillRect(0, 0, OLED_W, OLED_H, SSD1306_WHITE);
    display.setTextColor(SSD1306_BLACK);
  } else {
    display.drawRect(0, 0, OLED_W, OLED_H, SSD1306_WHITE);
    display.setTextColor(SSD1306_WHITE);
  }

  display.setTextSize(1);
  display.setCursor(10, 6);
  display.print("!!! ALERT !!!");
  display.fillRect(10, 16, 108, 18, SSD1306_WHITE);
  display.setTextColor(SSD1306_BLACK);
  display.setTextSize(2);
  display.setCursor(14, 20);
  display.print(headline);
  display.setTextColor(flash ? SSD1306_BLACK : SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(10, 42);
  display.print(detail);
  display.setCursor(10, 54);
  display.print("Keep power stable and recheck link");

  display.drawFastHLine(8, 62, 112, SSD1306_WHITE);
  display.drawPixel(5 + (nowMs / 80) % 118, 61, SSD1306_WHITE);
  display.display();
}

void renderBeaconDisplay(float batteryVoltage, int batteryPercent, float freqHz) {
  if (menuMode) {
    drawMenuScreen();
    return;
  }

  if (lowBatt) {
    drawWarningScreen("LOW BATT", String(batteryVoltage, 2) + "V  IR disabled");
    return;
  }

  if (!wifiReady && !WiFi.isConnected()) {
    drawWarningScreen("NO WIFI", String("AP ") + String(beaconID) + " active");
    return;
  }

  drawDashboardScreen(batteryVoltage, batteryPercent, freqHz);
}

/* ---------- SENSOR INIT ---------- */
void initSensors() {
  // INA219 current sensor
  #if HAS_INA219
  if (ina219.begin()) {
    hasINA219 = true;
    ina219.setCalibration_32V_2A();  // 32V, 2A range
    Serial.println("INA219 found at 0x40");
  } else {
    Serial.println("INA219 not found at 0x40");
  }
  #endif

  // ESP32-C6 internal temperature sensor
  #if CONFIG_IDF_TARGET_ESP32C6
  // ESP32-C6 has internal temperature sensor accessible via temperatureRead()
  hasInternalTemp = true;
  Serial.println("Internal temperature sensor available");
  #endif

  // Fan tachometer
  if (digitalRead(PIN_FAN_TACH) != -1) {
    pinMode(PIN_FAN_TACH, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(PIN_FAN_TACH), fanPulseISR, FALLING);
    hasFanTach = true;
    Serial.println("Fan tachometer enabled on pin " + String(PIN_FAN_TACH));
  }
}

/* ---------- FAN TACH ISR ---------- */
void IRAM_ATTR fanPulseISR() {
  fanPulseCount++;
}

/* ---------- UPDATE SENSOR READINGS ---------- */
void updateSensors() {
  // INA219 current sensor
  #if HAS_INA219
  if (hasINA219) {
    // getCurrent_mA returns current in milliamps
    ina219_current_amps = ina219.getCurrent_mA() / 1000.0f;
  }
  #endif

  // Internal temperature sensor
  if (hasInternalTemp) {
    #if CONFIG_IDF_TARGET_ESP32C6
    internal_temp_c = temperatureRead();
    #endif
  }

  // Fan RPM calculation (2 pulses per revolution for typical 2-wire fan)
  if (hasFanTach) {
    unsigned long now = millis();
    if (now - lastFanRpmCalc >= 1000) {
      // Typical fan: 2 pulses per revolution
      fanRpm = (fanPulseCount * 60) / 2;
      fanPulseCount = 0;
      lastFanRpmCalc = now;
    }
  }
}

/* ================================================================ */
TelemetrySnapshot collectTelemetry() {
  uint16_t raw = analogRead(PIN_VBAT);
  float voltage = (raw / 4095.0f) * 3.3f * 2.0f;
  int pct = constrain(map((int)(voltage * 1000), (int)(VBAT_MIN * 1000), (int)(VBAT_MAX * 1000), 0, 100), 0, 100);
  float rssi = WiFi.isConnected() ? WiFi.RSSI() : -127.0f;
  uint8_t brightnessPct = static_cast<uint8_t>(map(lvlIdx, 0, 5, 0, 100));

  TelemetrySnapshot telemetry = {
    voltage,
    pct,
    rssi,
    WiFi.isConnected() ? WiFi.SSID() : wifiSsid,
    static_cast<uint32_t>(millis() / 1000),
    brightnessPct,
    ledEnable,
    ina219_current_amps,
    internal_temp_c,
    fanRpm,
  };
  return telemetry;
}

String buildStatusJson() {
  TelemetrySnapshot telemetry = collectTelemetry();
  float f = BASE_FREQ_HZ + beaconID * FREQ_STEP_HZ;
  String safe = safeName(beaconName);
  String json = "{";
  json += "\"id\":" + String(beaconID) + ",";
  json += "\"name\":\"" + safe + "\",";
  json += "\"brightness_pct\":" + String(telemetry.ledBrightnessPct) + ",";
  json += "\"led_enabled\":" + String(telemetry.ledEnabled ? "true" : "false") + ",";
  json += "\"battery_v\":" + String(telemetry.batteryVoltage, 3) + ",";
  json += "\"battery_pct\":" + String(telemetry.batteryPercent) + ",";
  json += "\"freq_hz\":" + String(f, 1) + ",";
  json += "\"uptime_s\":" + String(telemetry.uptimeSeconds) + ",";
  json += "\"wifi_rssi\":" + String(telemetry.wifiRssiDbm, 1) + ",";
  json += "\"wifi_rssi_dbm\":" + String(telemetry.wifiRssiDbm, 1) + ",";
  json += "\"wifi_ssid\":\"" + safeName(telemetry.wifiSsid) + "\",";
  json += "\"current_a\":" + String(telemetry.currentAmps, 3) + ",";
  json += "\"temp_c\":" + String(telemetry.temperatureC, 2) + ",";
  json += "\"fan_rpm\":" + String(telemetry.fanRpm) + ",";
  json += "\"last_telemetry\":\"" + escapeJson(lastTelemetryBody) + "\"";
  json += ",\"telemetry\":{";
  json += "\"id\":" + String(beaconID) + ",";
  json += "\"name\":\"" + safe + "\",";
  json += "\"battery_v\":" + String(telemetry.batteryVoltage, 3) + ",";
  json += "\"battery_pct\":" + String(telemetry.batteryPercent) + ",";
  json += "\"current_a\":" + String(telemetry.currentAmps, 3) + ",";
  json += "\"fan_rpm\":" + String(telemetry.fanRpm) + ",";
  json += "\"brightness_pct\":" + String(telemetry.ledBrightnessPct) + ",";
  json += "\"temp_c\":" + String(telemetry.temperatureC, 2) + ",";
  json += "\"uptime_s\":" + String(telemetry.uptimeSeconds) + ",";
  json += "\"wifi_rssi_dbm\":" + String(telemetry.wifiRssiDbm, 1) + ",";
  json += "\"wifi_ssid\":\"" + safeName(telemetry.wifiSsid) + "\",";
  json += "\"led_enabled\":" + String(telemetry.ledEnabled ? "true" : "false");
  json += "}";
  json += "}";
  return json;
}

void sendJson(const String &body, int code = 200) {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Cache-Control", "no-cache");
  server.send(code, "application/json", body);
}

void handleStatus() { sendJson(buildStatusJson()); }

void handleConfig() {
  bool changed = false;
  if (server.hasArg("id")) {
    beaconID = constrain(server.arg("id").toInt(), 0, MAX_ID);
    changed = true;
  }
  if (server.hasArg("brightness")) {
    int pct = constrain(server.arg("brightness").toInt(), 0, 100);
    lvlIdx = map(pct, 0, 100, 0, 5);
    changed = true;
  }
  if (server.hasArg("led")) {
    ledEnable = server.arg("led") != "0";
    changed = true;
  }
  if (server.hasArg("name")) {
    String newName = server.arg("name");
    newName.trim();
    if (newName.length() > 0) {
      beaconName = safeName(newName);
      changed = true;
    }
  }
  if (changed) {
    saveSettings();
  }
  sendJson(buildStatusJson());
}

void handleWifi() {
  if (!server.hasArg("ssid")) {
    sendJson("{\"error\":\"ssid required\"}", 400);
    return;
  }
  wifiSsid = server.arg("ssid");
  wifiPass = server.hasArg("pass") ? server.arg("pass") : "";
  saveSettings();
  sendJson("{\"restart\":true}");
  delay(250);
  ESP.restart();
}

void handleTelemetry() {
  String body = server.hasArg("plain") ? server.arg("plain") : String();
  if (body.length() == 0) {
    body = "{}";
  }
  lastTelemetryBody = body;
  sendJson(String("{\"ok\":true,\"stored_bytes\":") + String(body.length()) + "}");
}

void handleOptions() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "*" );
  server.send(204);
}

/* ================================================================ */
void setup() {
  Serial.begin(115200);
  Serial.println("\n=== IR Beacon Starting ===");

  pinMode(PIN_IRLED, OUTPUT);
  pinMode(PIN_BTN, INPUT_PULLUP);
  analogWrite(PIN_IRLED, 0);
  analogReadResolution(12);
  Wire.begin(PIN_SDA, PIN_SCL);

  loadSettings();

  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  drawBootScreen();
  delay(800);

  for (uint16_t i = 0; i < HIST; i++) vHist[i] = VBAT_MAX;

  // Initialize sensors
  initSensors();

  wifiReady = connectSta();
  if (!wifiReady) {
    startApFallback();
  }

  server.on("/api/status", HTTP_GET, handleStatus);
  server.on("/api/config", HTTP_GET, handleConfig);
  server.on("/api/config", HTTP_POST, handleConfig);
  server.on("/api/wifi", HTTP_POST, handleWifi);
  server.on("/api/telemetry", HTTP_POST, handleTelemetry);
  server.onNotFound(handleStatus);
  server.on("/api/status", HTTP_OPTIONS, handleOptions);
  server.on("/api/config", HTTP_OPTIONS, handleOptions);
  server.on("/api/wifi", HTTP_OPTIONS, handleOptions);
  server.on("/api/telemetry", HTTP_OPTIONS, handleOptions);
  server.begin();

  Serial.println("Beacon ready");
}

/* ================================================================ */
void loop() {
  server.handleClient();
  updateSensors();

  /* ---- LED Pulse driver ---- */
  float f = BASE_FREQ_HZ + beaconID * FREQ_STEP_HZ;
  unsigned long intv = 1e6 / f;
  unsigned long nowU = micros();
  const unsigned long pulseWidthUs = PULSE_WIDTH_MS * 1000UL;
  static bool pulseActive = false;
  static unsigned long pulseStartUs = 0;

  if (menuMode || !ledEnable || lowBatt) {
    if (pulseActive) {
      analogWrite(PIN_IRLED, 0);
      pulseActive = false;
    }
  } else {
    if (pulseActive && (nowU - pulseStartUs) >= pulseWidthUs) {
      analogWrite(PIN_IRLED, 0);
      pulseActive = false;
    }
    if (!pulseActive && (nowU - lastPulseUs) >= intv) {
      lastPulseUs = nowU;
      pulseStartUs = nowU;
      pulseActive = true;
      analogWrite(PIN_IRLED, lvl[lvlIdx]);
    }
  }

  /* ---- Battery sample each second ---- */
  static unsigned long lastBat = 0;
  if (millis() - lastBat > 1000) {
    lastBat = millis();
    uint16_t raw = analogRead(PIN_VBAT);
    float v = (raw / 4095.0f) * 3.3f * 2.0f;   // 1:1 divider
    vHist[vPtr] = v; vPtr = (vPtr + 1) % HIST;
    uiBatteryVoltage = v;
    uiBatteryPercent = constrain(map((int)(v * 1000), (int)(VBAT_MIN * 1000), (int)(VBAT_MAX * 1000), 0, 100), 0, 100);
    if (v <= VBAT_CUT && !lowBatt) { lowBatt = true; analogWrite(PIN_IRLED, 0); }
  }

  if (millis() - uiLastDrawMs > 120) {
    uiLastDrawMs = millis();
    renderBeaconDisplay(uiBatteryVoltage, uiBatteryPercent, f);
  }

  /* ---- Button logic ---- */
  bool cur = digitalRead(PIN_BTN);
  if (btnPrev == LOW && cur == HIGH) {
    if (menuMode) { // short tap cycles item/action
      switch (menuIdx) {
        case 0: lvlIdx = (lvlIdx + 1) % (sizeof(lvl) / sizeof(lvl[0])); break;
        case 1: ledEnable = !ledEnable; break;
        case 2: beaconID = (beaconID + 1) % (MAX_ID + 1); break;
      }
      saveSettings();
      menuIdx = (menuIdx + 1) % 3; menuT = millis();
    }
  }
  if (btnPrev == HIGH && cur == LOW) { btnStart = millis(); }
  if (btnPrev == LOW && cur == LOW && !menuMode && millis() - btnStart > 1500) {
    menuMode = true; menuIdx = 0; menuT = millis();
  }
  if (menuMode && millis() - menuT > 6000) { menuMode = false; }
  btnPrev = cur;
}