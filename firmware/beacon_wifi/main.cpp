#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WebServer.h>

#include "wifi_credentials.h"

/********************************************************************
  Wi-Fi IR BEACON DRIVER – Xiao ESP32-C6
  ------------------------------------------------
  * Stores beacon ID, brightness, Wi-Fi credentials in NVS.
  * Simple HTTP API for status + config: /api/status, /api/config, /api/wifi
  * Falls back to SoftAP if STA connect fails (SSID: Beacon-Setup-<id>, pass: beacon1234)
********************************************************************/

/* ---------- USER CONSTANTS ---------- */
#define BASE_FREQ_HZ   30        // Hz for ID 0
#define FREQ_STEP_HZ   5         // Hz per ID step
#define PULSE_WIDTH_MS 3         // LED ON time (ms)
#define MAX_ID         15

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
    0.0f,
    0.0f,
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
  json += "\"fan_rpm\":0,";
  json += "\"last_telemetry\":\"" + escapeJson(lastTelemetryBody) + "\"";
  json += ",\"telemetry\":{";
  json += "\"id\":" + String(beaconID) + ",";
  json += "\"name\":\"" + safe + "\",";
  json += "\"battery_v\":" + String(telemetry.batteryVoltage, 3) + ",";
  json += "\"battery_pct\":" + String(telemetry.batteryPercent) + ",";
  json += "\"current_a\":" + String(telemetry.currentAmps, 3) + ",";
  json += "\"fan_rpm\":0,";
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
  pinMode(PIN_IRLED, OUTPUT);
  pinMode(PIN_BTN, INPUT_PULLUP);
  analogWrite(PIN_IRLED, 0);
  analogReadResolution(12);
  Wire.begin(PIN_SDA, PIN_SCL);

  loadSettings();

  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.print("Name: "); display.println(safeName(beaconName));
  display.setTextSize(2);
  display.setCursor(0, 18);
  display.print("ID "); display.println(beaconID);
  display.display();
  delay(800);

  for (uint16_t i = 0; i < HIST; i++) vHist[i] = VBAT_MAX;

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
}

/* ================================================================ */
void loop() {
  server.handleClient();

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
    if (v <= VBAT_CUT && !lowBatt) { lowBatt = true; analogWrite(PIN_IRLED, 0); }
    if (!menuMode) {
      // quick inline draw (simple to avoid reallocating)
      display.clearDisplay();
      display.setTextSize(1);
      display.setCursor(0, 0);
      display.print("Name: "); display.println(safeName(beaconName));
      display.setCursor(0, 12);
      display.print("ID:"); display.print(beaconID);
      display.print(" "); display.print((int)f); display.print("Hz");
      int pct = constrain(map((int)(v * 1000), (int)(VBAT_MIN * 1000), (int)(VBAT_MAX * 1000), 0, 100), 0, 100);
      display.setCursor(0, 24);
      display.print("Vbat: "); display.print(v, 2); display.println("V");
      display.setCursor(0, 34);
      display.print("LED: "); display.println(ledEnable ? "ON" : "OFF");
      display.setCursor(0, 44);
      display.print("WiFi: "); display.println(WiFi.isConnected() ? WiFi.localIP().toString() : "AP");
      display.display();
    }
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
