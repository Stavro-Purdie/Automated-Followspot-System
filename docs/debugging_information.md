# Debugging Information

The Automated Followspot System includes a simulated telemetry dashboard for quick debugging without hardware.

## Debug Telemetry Dashboard

Launch it from the GUI launcher through `Tools -> Debug Telemetry Dashboard`, or run it directly:

```bash
python3 control/debug_telemetry_dashboard.py
```

What it shows:

- Simulated node IDs, IP addresses, and MAC addresses
- Raw hex payload output for packet-level inspection
- Battery, current draw, and temperature readings
- A copy-to-clipboard snapshot for sharing debug state

This dashboard is intentionally synthetic. It is meant for UI validation, operator training, and debugging workflow checks when live telemetry is unavailable.
