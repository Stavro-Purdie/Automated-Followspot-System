# Changelog

## 1.0.0 - 2026-10-21

First production release of the Automated Followspot System.

### Included

- Multi-camera IR beacon detection with ReID and Kalman fusion.
- Bounded predicted tracking during short beacon or camera occlusion.
- Automatic beacon discovery with UDP broadcast and bounded local-subnet HTTP fallback.
- Logical beacon coordination that survives DHCP address changes.
- Combined Beacon Configurator & Live Monitor with hardware controls and status cards.
- DMX512 encoder with stub, RS485, Art-Net, and sACN transports.
- Node health endpoint with camera, DMX, uptime, and system metrics.
- CoreML/MPS-aware ReID configuration for Apple Silicon and CPU/CUDA-compatible model configuration.
- Demo mode and regression coverage for fusion, DMX, coordination, and tracking resilience.
- macOS project virtual-environment setup and platform-aware requirements.

### Validation

- 22 automated tests passing.
- Launcher and beacon configurator GUI smoke tests passing on macOS.
- `pip check` clean in the release environment.

### Hardware validation still required

Before a live show, validate camera calibration, RS485 electrical output, fixture channel maps, beacon RF coverage, and thermal/current sensor readings on the installed rig. The software release does not claim those physical checks have been performed.
