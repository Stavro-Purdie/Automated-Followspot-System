#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Preferences.h>          // FLASH‑backed key‑value store

/********************************************************************
  IR BEACON DRIVER – V3.0  (EEPROM + Enhanced UI)
  ------------------------------------------------
  * Unique beacon ID is stored in onboard flash (Preferences).
  * Menu allows brightness, power‑off, and ID change – all saved.
  * Compact 0.96" OLED UI with battery + brightness icons.
********************************************************************/

/* ---------- USER CONSTANTS ---------- */
#define BASE_FREQ_HZ   30        // Hz for ID 0
#define FREQ_STEP_HZ   5         // Hz per ID step
#define PULSE_WIDTH_MS 3         // LED ON time (ms)

/* ---------- DISPLAY ---------- */
#define OLED_W 128
#define OLED_H 64
#define OLED_RESET -1
Adafruit_SSD1306 display(OLED_W, OLED_H, &Wire, OLED_RESET);

/* ---------- PINS (XIAO ESP32‑C3) ---------- */
constexpr uint8_t PIN_IRLED   = 6;   // MOSFET gate PWM
constexpr uint8_t PIN_VBAT    = 3;   // Analog read (divider)
constexpr uint8_t PIN_BTN     = 0;   // Single push‑button
constexpr uint8_t PIN_SDA     = 4;
constexpr uint8_t PIN_SCL     = 5;

/* ---------- BATTERY ---------- */
const float VBAT_MAX = 4.20;
const float VBAT_MIN = 3.40;         // 0 % display
const float VBAT_CUT = 3.35;         // kill LED + warn

/* ---------- BRIGHTNESS ---------- */
uint8_t lvl[] = {0, 32, 64, 128, 192, 255};  // PWM table 0–100 %
uint8_t lvlIdx = 5;                          // full by default

/* ---------- STATE ---------- */
Preferences prefs;          // flash settings
uint8_t beaconID   = 0;     // loaded from flash
bool    ledEnable  = true;
bool    lowBatt    = false;

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
  prefs.end();
}

void saveSettings() {
  prefs.begin("beacon", false);
  prefs.putUChar("id",  beaconID);
  prefs.putUChar("bri", lvlIdx);
  prefs.end();
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
  display.setTextSize(2);
  display.setCursor(0, 20);
  display.print("ID "); display.println(beaconID);
  display.display();
  delay(1200);

  for (uint16_t i=0;i<HIST;i++) vHist[i]=VBAT_MAX;
}

/* ================================================================ */
void loop() {
  /* ---- LED Pulse driver ---- */
  float f = BASE_FREQ_HZ + beaconID*FREQ_STEP_HZ;
  unsigned long intv = 1e6 / f;
  unsigned long nowU = micros();
  if (!menuMode && ledEnable && !lowBatt && (nowU-lastPulseUs)>=intv) {
    lastPulseUs = nowU;
    analogWrite(PIN_IRLED, lvl[lvlIdx]);
    delay(PULSE_WIDTH_MS);
    analogWrite(PIN_IRLED, 0);
  }

  /* ---- Battery sample each second ---- */
  static unsigned long lastBat = 0;
  if (millis()-lastBat>1000) {
    lastBat = millis();
    float v = readVBAT();
    vHist[vPtr] = v; vPtr=(vPtr+1)%HIST;
    if (v<=VBAT_CUT && !lowBatt) { lowBatt=true; analogWrite(PIN_IRLED,0); }
    if (!menuMode) drawMain(v,f);
  }

  /* ---- Button logic ---- */
  buttonHandler();
}

/* ================================================================ */
float readVBAT(){
  uint16_t raw = analogRead(PIN_VBAT);
  return (raw/4095.0f)*3.3f*2.0f;   // 1:1 divider
}

/* ================================================================ */
void buttonHandler(){
  bool cur = digitalRead(PIN_BTN);
  // rising edge → short tap while in menu cycles item/action
  if(btnPrev==LOW && cur==HIGH){
    if(menuMode){ applyMenu(); nextMenu(); }
  }
  // falling edge start timer
  if(btnPrev==HIGH && cur==LOW){ btnStart=millis(); }
  // held 1.5 s -> enter menu
  if(btnPrev==LOW && cur==LOW && !menuMode && millis()-btnStart>1500){
      menuMode=true; menuIdx=0; menuT=millis(); drawMenu(); }
  // auto‑exit after 6 s idle
  if(menuMode && millis()-menuT>6000){ menuMode=false; }
  btnPrev=cur;
}

/* ================================================================ */
void applyMenu(){
  switch(menuIdx){
    case 0: // brightness
      lvlIdx=(lvlIdx+1)% (sizeof(lvl)/sizeof(lvl[0])); break;
    case 1: // power toggle
      ledEnable=!ledEnable; break;
    case 2: // ID ++
      beaconID=(beaconID+1)%16; break;
  }
  saveSettings();           // persist
}

void nextMenu(){ menuIdx=(menuIdx+1)%3; menuT=millis(); drawMenu(); }

/* ================================================================ */
void drawBatteryIcon(int x,int y,int pct){
  display.drawRect(x,y,12,6,SSD1306_WHITE);
  display.drawLine(x+12,y+2,x+12,y+3,SSD1306_WHITE); // terminal
  int fill = map(pct,0,100,0,10);
  display.fillRect(x+1,y+1,fill,4,SSD1306_WHITE);
}

void drawBrightnessIcon(int x,int y,int idx){
  int h = map(idx,0,5,0,6);
  display.drawRect(x,y,4,6,SSD1306_WHITE);
  display.fillRect(x+1,y+6-h,2,h,SSD1306_WHITE);
}

/* ================================================================ */
void drawMain(float v,float f){
  display.clearDisplay();
  // row 0: ID + freq + icons
  display.setTextSize(1);
  display.setCursor(0,0);
  display.print("ID:"); display.print(beaconID);
  display.print(" "); display.print((int)f); display.print("Hz");
  int pct = constrain(map(v*100,VBAT_MIN*100,VBAT_MAX*100,0,100),0,100);
  drawBatteryIcon(108,0,pct);
  drawBrightnessIcon(100,0,lvlIdx);

  // row 1/2: voltage + status
  display.setCursor(0,12);
  display.print("Vbat: "); display.print(v,2); display.println("V");
  display.setCursor(0,22);
  display.print("LED: "); display.println(ledEnable?"ON":"OFF");

  // row 3: runtime estimate
  float oldest=vHist[(vPtr+1)%HIST];
  float d=oldest-v; float minLeft=(d>0.005f)?((v-VBAT_CUT)/d)*(HIST/60.0f):999.0f;
  display.setCursor(0,32);
  display.print("Time: ");
  if(minLeft<998){ display.print(minLeft,0); display.print("m"); }
  else display.println("--");
  display.display();
}

/* ================================================================ */
void drawMenu(){
  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(0,0);
  display.println("-- MENU -- (tap)");
  display.setCursor(0,12);
  display.print(menuIdx==0?"> ":"  "); display.println("Brightness");
  display.print(menuIdx==1?"> ":"  "); display.println(ledEnable?"LED Off":"LED On");
  display.print(menuIdx==2?"> ":"  "); display.print("ID: "); display.println(beaconID);
  display.display();
}
