# Roof Array Camera Configuration

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| cameras | array[object] | ✅ |  |
  *Array items:*
    | Property | Type | Required | Description |
    |----------|------|----------|-------------|
    | auto_crop | boolean | ✅ |  |
    | camera_id | string | ✅ |  |
    | crop_rect | array[integer (min: 0)] | ✅ |  |
    | enabled | boolean | ✅ |  |
    | overlap_threshold | number (min: 0, max: 1) | ✅ | Range: min: 0, max: 1 |
    | position | array[integer (min: 0)] | ✅ |  |
    | server_url | string (uri) | ✅ | Format: uri |
| grid_config | object | ✅ |  |
  | Property | Type | Required | Description |
  |----------|------|----------|-------------|
  | auto_arrange | boolean | ✅ |  |
  | cameras_per_row | integer (min: 1, max: 16) | ✅ | Range: min: 1, max: 16 |
  | cell_height | integer (min: 48, max: 1080) | ✅ | Range: min: 48, max: 1080 |
  | cell_width | integer (min: 64, max: 1920) | ✅ | Range: min: 64, max: 1920 |
  | total_cameras | integer (min: 1, max: 64) | ✅ | Range: min: 1, max: 64 |

## Required Fields

- **cameras**
- **grid_config**
