# ReID Configuration

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| camera | object | ✅ |  |
  | Property | Type | Required | Description |
  |----------|------|----------|-------------|
  | front_camera | object | ✅ |  |
    | Property | Type | Required | Description |
    |----------|------|----------|-------------|
    | angle | number | ✅ |  |
    | calibration_matrix | array[array[number]] | ✅ |  |
    | depth | object | ✅ |  |
      | Property | Type | Required | Description |
      |----------|------|----------|-------------|
      | confidence_floor | number (min: 0, max: 1) | ✅ | Range: min: 0, max: 1 |
      | enabled | boolean | ✅ |  |
      | fallback_height | number (min: 0.1, max: 3.0) | ✅ | Range: min: 0.1, max: 3.0 |
      | smoothing_window | integer (min: 1, max: 30) | ✅ | Range: min: 1, max: 30 |
    | distortion_coeffs | array[number] | ✅ |  |
    | extrinsics | object | ✅ |  |
      | Property | Type | Required | Description |
      |----------|------|----------|-------------|
      | calibrated | boolean | ✅ |  |
      | calibration_date | string (date-time) | ❌ | Format: date-time |
      | reference_frame | string | ✅ |  |
      | rotation_matrix | array[array[number]] | ✅ |  |
      | translation_vector | array[number] | ✅ |  |
    | focal_length | number (min: 1) | ✅ | Range: min: 1 |
    | fov | number (min: 1, max: 180) | ✅ | Range: min: 1, max: 180 |
    | position | array[number] | ✅ |  |
    | resolution | array[integer (min: 1)] | ✅ |  |
| data_fusion | object | ✅ |  |
  | Property | Type | Required | Description |
  |----------|------|----------|-------------|
  | fusion_memory_time | number (min: 0.1, max: 30.0) | ✅ | Range: min: 0.1, max: 30.0 |
  | ir_weight | number (min: 0, max: 1) | ✅ | Range: min: 0, max: 1 |
  | position_match_threshold | number (min: 0.01, max: 10.0) | ✅ | Range: min: 0.01, max: 10.0 |
  | reid_weight | number (min: 0, max: 1) | ✅ | Range: min: 0, max: 1 |
  | time_sync_tolerance | number (min: 0.001, max: 1.0) | ✅ | Range: min: 0.001, max: 1.0 |
| identities | object | ✅ |  |
  | Property | Type | Required | Description |
  |----------|------|----------|-------------|
  | gallery_path | string | ✅ |  |
  | manifest_path | string | ✅ |  |
  | match_threshold | number (min: 0.1, max: 1.0) | ✅ | Range: min: 0.1, max: 1.0 |
  | reload_interval_sec | number (min: 0.1, max: 3600) | ✅ | Range: min: 0.1, max: 3600 |
| models | object | ✅ |  |
  | Property | Type | Required | Description |
  |----------|------|----------|-------------|
  | detector | object | ✅ |  |
    | Property | Type | Required | Description |
    |----------|------|----------|-------------|
    | batch_size | integer (min: 1, max: 32) | ✅ | Range: min: 1, max: 32 |
    | device | enum[auto, cpu, cuda, mps] | ✅ | Allowed values: auto, cpu, cuda, mps |
    | model_path | string | ✅ |  |
    | name | enum[yolov8n, yolov8s, yolov8m, yolov8l, yolov8x] | ✅ | Allowed values: yolov8n, yolov8s, yolov8m, yolov8l, yolov8x |
  | reid | object | ✅ |  |
    | Property | Type | Required | Description |
    |----------|------|----------|-------------|
    | device | enum[auto, cpu, cuda, mps] | ✅ | Allowed values: auto, cpu, cuda, mps |
    | feature_dim | integer | ✅ | Allowed values: 512, 1024, 2048 |
    | model_path | string | ✅ |  |
    | name | enum[osnet_x0_5, osnet_x1_0, osnet_ibn_x1_0] | ✅ | Allowed values: osnet_x0_5, osnet_x1_0, osnet_ibn_x1_0 |
| optimization | object | ✅ |  |
  | Property | Type | Required | Description |
  |----------|------|----------|-------------|
  | coreml_compute_unit | enum[ALL, CPU_AND_GPU, CPU_AND_NE, CPU_ONLY] | ✅ | Allowed values: ALL, CPU_AND_GPU, CPU_AND_NE, CPU_ONLY |
  | coreml_model_path | string | ✅ |  |
  | coreml_reid_enabled | boolean | ✅ |  |
  | coreml_skip_torch | boolean | ✅ |  |
  | detection_interval | integer (min: 1, max: 10) | ✅ | Range: min: 1, max: 10 |
  | max_tracking_age | integer (min: 1, max: 100) | ✅ | Range: min: 1, max: 100 |
  | reid_interval | integer (min: 1, max: 10) | ✅ | Range: min: 1, max: 10 |
  | tensorrt_optimization | boolean | ✅ |  |
  | use_half_precision | boolean | ✅ |  |
| performance | object | ✅ |  |
  | Property | Type | Required | Description |
  |----------|------|----------|-------------|
  | confidence_threshold | number (min: 0.1, max: 1.0) | ✅ | Range: min: 0.1, max: 1.0 |
  | detection_resolution | array[integer (min: 1)] | ✅ |  |
  | input_resolution | array[integer (min: 1)] | ✅ |  |
  | max_persons | integer (min: 1, max: 50) | ✅ | Range: min: 1, max: 50 |
  | nms_threshold | number (min: 0.1, max: 1.0) | ✅ | Range: min: 0.1, max: 1.0 |
  | target_fps | integer (min: 1, max: 60) | ✅ | Range: min: 1, max: 60 |
| stage_geometry | object | ✅ |  |
  | Property | Type | Required | Description |
  |----------|------|----------|-------------|
  | depth | number (min: 0.1, max: 100) | ✅ | Range: min: 0.1, max: 100 |
  | height | number (min: 0.1, max: 50) | ✅ | Range: min: 0.1, max: 50 |
  | origin | array[number] | ✅ |  |
  | units | enum[meters, feet] | ❌ | Allowed values: meters, feet |
  | width | number (min: 0.1, max: 100) | ✅ | Range: min: 0.1, max: 100 |
| tracking | object | ✅ |  |
  | Property | Type | Required | Description |
  |----------|------|----------|-------------|
  | depth_estimation_method | enum[simple, height_based, geometric, hybrid] | ✅ | Allowed values: simple, height_based, geometric, hybrid |
  | feature_similarity_threshold | number (min: 0.1, max: 1.0) | ✅ | Range: min: 0.1, max: 1.0 |
  | max_disappeared | integer (min: 1, max: 100) | ✅ | Range: min: 1, max: 100 |
  | max_distance | number (min: 1, max: 1000) | ✅ | Range: min: 1, max: 1000 |
  | max_tracking_distance | number (min: 0.1, max: 10.0) | ✅ | Range: min: 0.1, max: 10.0 |
  | new_track_confidence_threshold | number (min: 0.1, max: 1.0) | ✅ | Range: min: 0.1, max: 1.0 |
  | reid_threshold | number (min: 0.1, max: 1.0) | ✅ | Range: min: 0.1, max: 1.0 |
  | track_memory_frames | integer (min: 1, max: 100) | ✅ | Range: min: 1, max: 100 |

## Required Fields

- **camera**
- **data_fusion**
- **identities**
- **models**
- **optimization**
- **performance**
- **stage_geometry**
- **tracking**
