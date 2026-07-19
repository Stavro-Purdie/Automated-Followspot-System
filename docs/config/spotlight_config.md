# Spotlight Configuration

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| dmx | object | ✅ |  |
  | Property | Type | Required | Description |
  |----------|------|----------|-------------|
  | baud_rate | integer | ✅ | Allowed values: 115200, 250000, 500000, 1000000 |
  | brightness_pct | number (min: 0, max: 100) | ❌ | Range: min: 0, max: 100 |
  | endpoint_url | string (uri) | ✅ | Format: uri |
  | pan_address | integer (min: 1, max: 511) | ✅ | Range: min: 1, max: 511 |
  | pan_scale | number (min: 0.1, max: 10.0) | ✅ | Range: min: 0.1, max: 10.0 |
  | serial_port | string | ✅ |  |
  | tilt_address | integer (min: 1, max: 511) | ✅ | Range: min: 1, max: 511 |
  | tilt_scale | number (min: 0.1, max: 10.0) | ✅ | Range: min: 0.1, max: 10.0 |
  | transport | enum[stub, http_bridge, rs485_serial, artnet, sacn] | ✅ | Allowed values: stub, http_bridge, rs485_serial, artnet, sacn |
  | universe | integer (min: 1, max: 128) | ✅ | Range: min: 1, max: 128 |
| rig | object | ✅ |  |
  | Property | Type | Required | Description |
  |----------|------|----------|-------------|
  | fixture_position_m | array[number] | ✅ |  |
  | pan_limits_deg | array[number (min: -180, max: 180)] | ✅ |  |
  | pan_zero_angle_deg | number (min: -180, max: 180) | ✅ | Range: min: -180, max: 180 |
  | smoothing | object | ✅ |  |
    | Property | Type | Required | Description |
    |----------|------|----------|-------------|
    | pan_alpha | number (min: 0, max: 1) | ✅ | Range: min: 0, max: 1 |
    | tilt_alpha | number (min: 0, max: 1) | ✅ | Range: min: 0, max: 1 |
  | stage_origin_m | array[number] | ✅ |  |
  | tilt_limits_deg | array[number (min: -180, max: 180)] | ✅ |  |
  | tilt_zero_angle_deg | number (min: -180, max: 180) | ✅ | Range: min: -180, max: 180 |

## Required Fields

- **dmx**
- **rig**
