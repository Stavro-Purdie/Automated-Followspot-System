# Tracking reliability and coordination

The runtime now treats short sensor outages as a normal operating condition.

## Beacon coordination

`control.beacon_network.discover_beacons()` sends `AFS_BEACON_DISCOVER` over UDP and then performs a bounded HTTP scan of the configured local subnet for older firmware. `BeaconCoordinator` keys the roster by the logical beacon ID reported by `/api/status`, so a DHCP address change does not create a duplicate beacon. The firmware responds on UDP port 4210 and continues serving its HTTP API on port 80.

The checked-in discovery settings live in `config/beacons_config.json`. Set `discovery.network` to a CIDR such as `192.168.1.0/24` when automatic route detection is unsuitable.

## Occlusion behavior

- `PersonTracker` keeps a track in `active` / `predicted` state for `tracking.max_occlusion_frames` missed frames.
- `DataFusion` propagates the six-dimensional constant-velocity Kalman state for up to `data_fusion.max_occlusion_time` seconds and exposes `tracking_state`, `missed_updates`, and `occlusion_duration` in `get_person_positions()`.
- Confidence decays to the configured floor during prediction. After the normal fusion memory window, the person is removed rather than followed indefinitely.

The focused tests demonstrate three missed tracker frames remain usable and the fourth is marked lost. The default fusion time budget is 0.75 seconds; this is an operational budget, not a claim about physical accuracy.

## Performance measurement

The Kalman update uses a linear solve instead of explicitly forming a matrix inverse, and reusable measurement matrices are initialized once. The tracker exposes `avg_processing_time_ms` and `max_processing_time_ms`; fusion emits per-update timing at debug level. Production reports should capture both before and after changing model/device settings on the target Mac or node hardware. No hardware-specific speedup is claimed until that benchmark is recorded.

## Operator fallback and manual control

Automated tracking does not remove the lighting designer's control of the wider
show. The live dashboard opens **Tracking Fallback & Manual Control** after a
sustained loss of tracking, camera feed, or a lighting-system fault. It is also
available at any time from **Tools**, the control-panel button, or the `F`
keyboard shortcut.

The window provides three recovery choices:

- **Hold the last reliable position** while the operator diagnoses the fault.
- **Safe state** to stop automated movement and send zero brightness to the
  configured lighting bridge.
- **Restore manual control** with pan, tilt, and brightness controls.

**Resume automated tracking** returns to normal operation without restarting the
application. The fallback procedure should be rehearsed before a show so the
operator knows which response best fits the venue and lighting design.
