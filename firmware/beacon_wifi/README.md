# Wi-Fi IR Beacon Firmware (Xiao ESP32-C6)

Network-enabled rewrite of the `IR-Beacon` branch firmware with a minimal HTTP API.

## Features
- Stores beacon ID, brightness, and Wi-Fi credentials in NVS (Preferences).
- HTTP API (default port 80):
  - `GET /api/status` → JSON: `id`, `brightness_pct`, `led_enabled`, `battery_v`, `battery_pct`, `freq_hz`, `uptime_s`, `wifi_rssi`.
  - `POST /api/config` (form/query): `id` (0-15), `brightness` (0-100), `led` (0/1). Returns status JSON.
  - `POST /api/wifi` (form/query): `ssid`, `pass` → saves + restarts.
- STA first; SoftAP fallback `Beacon-Setup-<id>` (password `beacon1234`).
- OLED still shows ID, Hz, Vbat, LED state, Wi-Fi mode/IP.

## Build & Flash (arduino-cli)
1) Install core + libs (once):
```
arduino-cli core install esp32:esp32
arduino-cli lib install "Adafruit SSD1306" "Adafruit GFX Library"
```
2) Populate Wi-Fi defaults:
```
cd firmware/beacon_wifi
cp wifi_credentials.h.example wifi_credentials.h
# edit wifi_credentials.h with your SSID/PASS
```
3) Compile + flash (Xiao ESP32-C6 fqbn):
```
arduino-cli compile --fqbn esp32:esp32:xiao_esp32c6 .
arduino-cli upload  --fqbn esp32:esp32:xiao_esp32c6 -p /dev/tty.usbmodemXYZ .
```
If STA connect fails, the device starts the AP; you can then `POST /api/wifi` with new creds.

## Notes
- PWM/IO pinout matches the legacy C3 sketch (IR gate D6, battery ADC D3, button D0, OLED on D4/D5). Adjust if your wiring differs.
- Brightness table uses 6 steps; the `/api/config` brightness 0-100 is mapped onto that table.
