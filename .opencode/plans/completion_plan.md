# Automated Followspot System - Completion Plan

**Status**: Core architecture complete. Remaining work: DMX output pipeline, ML model conversion, beacon sensor integration, validation/testing.

---

## 1. DMX Output Pipeline (HIGH PRIORITY)

### Goal
Enable the front truss node (Pi + IMX477 + RS485 HAT) to drive physical moving-head fixtures from fused spotlight commands.

### Current State
- `SpotlightController` (`control/spotlight_controller.py`): Computes pan/tilt from fused positions → outputs JSON command dict
- `DMXController` (`node/server.py`): HTTP `/dmx` endpoint exists but returns placeholder; `_serialize_frame()` builds JSON but no actual RS485 DMX512 frame generation
- Config (`spotlight_config.json`): DMX addresses, transport modes (`http_bridge`, `rs485_serial`, `stub`)

### Required Work

| Task | File(s) | Details |
|------|---------|---------|
| **1.1 DMX512 frame encoder** | `node/server.py` (DMXController) | Convert pan/tilt/brightness → 512-byte DMX universe frame. Use `struct.pack` for 16-bit pan/tilt at configured addresses. |
| **1.2 RS485 serial transport** | `node/server.py` (DMXController._open_serial) | Implement continuous DMX break + MAB + frame loop at 250kbps. Use `pyserial` with correct timing (break ≥88μs, MAB ≥8μs). |
| **1.3 Art-Net/sACN sender** | New: `node/dmx_transport.py` | Add Ethernet-based DMX. Use `python-sacn` or custom Art-Net. Selectable via `spotlight_config.json → dmx.transport`. |
| **1.4 Transport abstraction** | `node/server.py`, `control/spotlight_controller.py` | Factory pattern: `DMXTransport` base class with `RS485Transport`, `ArtNetTransport`, `StubTransport`. Config selects implementation. |
| **1.5 Control → Node bridge** | `control/spotlight_controller.py._send_command` | Already posts JSON to node `/dmx`. Ensure node accepts both HTTP bridge and direct Art-Net. |
| **1.6 Fixture profile support** | New: `config/fixture_profiles.json` | Define channel maps per fixture type (pan/tilt 16-bit, dimmer, focus, etc.). Generic encoder uses profile. |

### Config Additions (`spotlight_config.json`)
```json
"dmx": {
  "transport": "rs485_serial",    // or "artnet", "sacn", "stub"
  "universe": 1,
  "artnet_ip": "2.0.0.1",
  "artnet_port": 6454,
  "fixture_profile": "generic_moving_head"
}
```

---

## 2. ML/ReID Pipeline - CoreML + TensorRT (HIGH PRIORITY)

### Goal
Enable Neural Engine (ANE) acceleration on Apple Silicon for ReID embeddings, with CUDA TensorRT option for NVIDIA Jetson nodes.

### Current State
- `reid_config.json` → `optimization.coreml_reid_enabled: true`, model path configured
- `OptimizedReIDProcessor._load_coreml_model()`: Loads `.mlpackage` if present, falls back to PyTorch MPS
- **Missing**: `.mlpackage` file, conversion script, TensorRT path

### Required Work

| Task | File(s) | Details |
|------|---------|---------|
| **2.1 OSNet → CoreML converter** | New: `tools/convert_osnet_coreml.py` | Use `coremltools.convert()` with `torchreid` OSNet. Input: `torch.randn(1,3,256,128)`. Set `compute_units=ct.ComputeUnit.CPU_AND_NE` for ANE. Output: `reid/models/osnet_x0_5.mlpackage`. |
| **2.2 Model download helper** | New: `tools/download_reid_weights.py` | Fetch `osnet_x0_5_market1501.pth` from torchreid zoo (or use `torchreid.models.build_model(pretrained=True)`). |
| **2.3 CoreML validation test** | Extend `reid/reid_processor.py` test | Verify numerical parity: PyTorch vs CoreML cosine similarity < 1e-4. |
| **2.4 TensorRT export (Jetson)** | New: `tools/export_tensorrt.py` | ONNX export → `trtexec` build. Configurable in `reid_config.json → optimization.tensorrt_optimization`. |
| **2.5 Runtime device selection** | `reid/reid_processor.py._setup_device()` | Priority: CoreML (ANE) > MPS > CUDA/TensorRT > CPU. Log selected backend at startup. |
| **2.6 Half-precision (FP16)** | `reid_processor.py` | Already has `use_half_precision` flag. Ensure CoreML model uses FP16 weights. |

### Conversion Script Skeleton
```python
# tools/convert_osnet_coreml.py
import torch, coremltools as ct
from torchreid.models import build_model

model = build_model(name='osnet_x0_5', num_classes=1000, pretrained=True)
model.eval()
traced = torch.jit.trace(model, torch.randn(1, 3, 256, 128))
mlmodel = ct.convert(traced, inputs=[ct.TensorType(shape=(1,3,256,128))],
                     compute_units=ct.ComputeUnit.CPU_AND_NE,
                     minimum_deployment_target=ct.target.macOS13)
mlmodel.save("reid/models/osnet_x0_5.mlpackage")
```

---

## 3. Beacon Telemetry - Full Sensor Suite (MEDIUM PRIORITY)

### Goal
Replace placeholder telemetry (current=0, temp=0, fan=0) with real sensor readings.

### Current State
- Firmware (`firmware/beacon_wifi/beacon_wifi.ino`): Fields exist in JSON, hardcoded to 0
- Monitor GUI (`control/beacon_monitor_gui.py`): Displays N/A gracefully
- README documents wiring for INA219 (current), XIAO internal temp, fan tach

### Required Work

| Task | File(s) | Details |
|------|---------|---------|
| **3.1 INA219 current sensor** | `firmware/beacon_wifi/beacon_wifi.ino` | Add `Adafruit_INA219` on I2C (addr 0x40). Read `current_mA` in `collectTelemetry()`. Power rail: LED supply (high-side). |
| **3.2 Internal temperature** | `firmware/beacon_wifi/beacon_wifi.ino` | ESP32-C6 has on-die temp sensor. Use `temperatureRead()` (Arduino ESP32 core ≥3.0). Expose as `temp_c`. |
| **3.3 Fan tachometer** | `firmware/beacon_wifi/beacon_wifi.ino` | Optional: GPIO interrupt counting pulses. `fan_rpm = (pulses * 60) / pulses_per_rev`. Configurable pin. |
| **3.4 Sensor auto-detection** | `firmware/beacon_wifi/beacon_wifi.ino` | Scan I2C at startup. If INA219 found → enable current. If fan pin configured → enable RPM. |
| **3.5 Calibration constants** | `firmware/beacon_wifi/beacon_wifi.ino` | Battery divider ratio, INA219 shunt value, fan pulses/rev as `#define` or NVS config. |
| **3.6 Monitor GUI units** | `control/beacon_monitor_gui.py` | Already handles fields. Verify scaling: mA→A, °C, RPM display correctly. |

### BOM Additions (Optional)
| Sensor | Part | Cost | Purpose |
|--------|------|------|---------|
| Current | INA219 (or INA226) | ~$3 | LED driver current monitoring |
| Temp | ESP32-C6 internal | $0 | Die temperature (proxy for LED junction) |
| Fan | 5V/12V fan with tach | ~$5 | Enclosure cooling verification |

---

## 4. Front Truss Node Integration (HIGH PRIORITY)

### Goal
Production-ready Pi node: IMX477 HQ camera + RS485 HAT → WebRTC stream + DMX output.

### Current State
- Profile `front_truss` in `node/server.py` with 1080p RGB888 config
- RS485 serial port configured (`/dev/ttyAMA0`, 115200)
- DMX endpoint wired but stubbed

### Required Work

| Task | File(s) | Details |
|------|---------|---------|
| **4.1 RS485 GPIO enable** | `node/setup_utils.py`, boot config | Ensure UART4 (`/dev/ttyAMA0`) enabled in `/boot/firmware/config.txt`: `dtoverlay=uart4`. Disable Bluetooth if using UART0. |
| **4.2 DMX timing validation** | `node/server.py` | Verify 250kbps on Pi UART. May need `dtoverlay=pi3-miniuart-bt` + `core_freq=250` for stable baud. |
| **4.3 Front camera calibration** | `config/front_array_config.json` | Run calibration workflow (README §Front Camera Calibration). Store rotation_matrix + translation_vector. |
| **4.4 Systemd service hardening** | `node/setup_utils.py.ensure_autostart_service` | Add `Restart=always`, `WatchdogSec=30`, `Environment=PYTHONUNBUFFERED=1`. |
| **4.5 Health monitoring** | `node/server.py` | Add `/health` endpoint: camera status, DMX link, CPU temp, disk space. |
| **4.6 Network failover** | `node/setup_utils.py` | Static IP + fallback AP mode if Ethernet down (for field config). |

---

## 5. Calibration & Validation Automation (MEDIUM PRIORITY)

### Goal
Reduce manual calibration steps; provide verification tools.

### Required Work

| Task | File(s) | Details |
|------|---------|---------|
| **5.1 Automated extrinsics solver** | New: `tools/calibrate_front_camera.py` | Use stage corners + known reference points → solvePnP → write rotation_matrix/translation_vector to config. |
| **5.2 Spotlight alignment verify** | New: `tools/verify_spotlight.py` | Move fused target → log commanded pan/tilt vs actual fixture position (via DMX loopback or operator feedback). |
| **5.3 Fusion accuracy metrics** | `fusion/data_fusion.py` | Add RMSE tracking: IR vs ReID vs fused position over time. Log to CSV for post-show analysis. |
| **5.4 Regression test suite** | New: `tests/test_fusion.py`, `test_reid.py` | Synthetic data tests: known trajectories → verify tracker IDs persist, fusion weights correct. |
| **5.5 CI pipeline** | `.github/workflows/ci.yml` | Lint (ruff), type-check (mypy), unit tests on push. Requires mock camera/server fixtures. |

---

## 6. Missing Utilities & Polish (LOW-MEDIUM PRIORITY)

| Task | File(s) | Details |
|------|---------|---------|
| **6.1 Requirements split** | `requirements-control.txt`, `requirements-node.txt` | Separate heavy deps (torch, torchreid, coremltools) from node-only (aiortc, picamera2). |
| **6.2 Type hints / mypy** | All `.py` | Add `py.typed`, strict mypy config. Fix `Optional` vs `None` issues. |
| **6.3 Logging standardization** | All modules | Structured JSON logging (`python-json-logger`). Correlation IDs for request tracing. |
| **6.4 Config schema validation** | New: `config/schemas/` | JSON Schema for each config file. Validate at load time with `jsonschema`. |
| **6.5 Beacon OTA updates** | `firmware/beacon_wifi/` | Add `/api/ota` endpoint → fetch `.bin` from HTTPS → `Update.writeStream()`. |
| **6.6 Documentation sync** | `README.md`, `docs/` | Auto-generate config docs from schemas. Add architecture diagram (Mermaid). |

---

## Implementation Order (Recommended)

```
Phase 1 (Core Show-Readiness)
├── 1.1-1.4  DMX512 frame + RS485 transport + Art-Net + abstraction
├── 2.1-2.3  CoreML converter + download + validation
├── 4.1-4.3  Front node UART + DMX timing + calibration

Phase 2 (Robustness)
├── 3.1-3.4  Beacon sensors (INA219, temp, fan)
├── 4.4-4.6  Systemd hardening + health + failover
├── 5.1-5.2  Automated calibration + spotlight verify

Phase 3 (Quality)
├── 2.4-2.6  TensorRT + device selection + FP16
├── 5.3-5.5  Fusion metrics + test suite + CI
├── 6.1-6.6  Requirements split + types + logging + schemas + OTA + docs
```

---

## Effort Estimates

| Area | Tasks | Est. Days |
|------|-------|-----------|
| DMX Pipeline | 1.1-1.6 | 3-4 |
| CoreML/ML Pipeline | 2.1-2.6 | 3-4 |
| Beacon Sensors | 3.1-3.6 | 2-3 |
| Front Node | 4.1-4.6 | 2-3 |
| Calibration/Validation | 5.1-5.5 | 3-4 |
| Polish/Utilities | 6.1-6.6 | 2-3 |
| **Total** | | **15-21 days** |

---

## Dependencies to Add

| Package | Purpose | Where |
|---------|---------|-------|
| `pyserial` | RS485 DMX | `node/requirements.txt` |
| `python-sacn` or `artnet` | sACN/Art-Net sender | `node/requirements.txt` |
| `coremltools>=6.4` | CoreML conversion | `tools/requirements.txt` |
| `torchreid` | OSNet model (already in control reqs) | `control/requirements.txt` |
| `Adafruit_INA219` | Arduino lib for current sensor | Firmware `lib_deps` |
| `jsonschema` | Config validation | Shared |
| `python-json-logger` | Structured logging | Shared |
| `pytest`, `pytest-mock` | Test suite | `tests/requirements.txt` |

---

## Risk Areas

1. **DMX timing on Pi UART** - Linux not real-time; may need `pigpio` DMA or dedicated DMX HAT (e.g., DMXKing ultraDMX). Fallback: Art-Net to Ethernet-DMX gateway.
2. **CoreML conversion** - torchreid OSNet may have unsupported ops. Test early; fallback to MPS is solid.
3. **Beacon I2C bus contention** - OLED (SSD1306) + INA219 share I2C. Verify address separation (0x3C vs 0x40).
4. **Network latency in fusion** - IR (roof) + ReID (front) clocks must sync within `time_sync_tolerance` (100ms). Add NTP/chrony to nodes.

---

## Quick Wins (Do First)

- [ ] Add DMX512 frame encoder + RS485 loop (unblocks show)
- [ ] Write CoreML conversion script + generate `.mlpackage` (unblocks ANE)
- [ ] Add INA219 reading to beacon firmware (minimal code, high value)
- [ ] Create `tools/calibrate_front_camera.py` (reduces manual errors)