This document catalogs the configurable thresholds, ratios, and default options stored in `config.py`.

---

## 1. Camera Configurations

- `CAMERA_INDEX`: Index of the target camera device (default `0`).
- `CAMERA_WIDTH`: Desired capture width in pixels (default `1280`).
- `CAMERA_HEIGHT`: Desired capture height in pixels (default `720`).
- `CAMERA_FPS_TARGET`: Target frame rate for video capture (default `60`).

---

## 2. Gesture Pipeline Constants

- `GESTURE_DEBOUNCE_FRAMES`: Consecutively matching frames required to confirm a transition (default `3`).
- `PALM_HOLD_DURATION`: Stable hold duration in seconds required to trigger clear canvas (default `0.15`).
- `PALM_OPEN_FINGER_COUNT`: Extended finger count limit to classify the palm (default `4`).
- `TRACKING_TIMEOUT`: Seconds to preserve coordinates after hand tracking is lost (default `1.5`).
- `TRACKING_RECOVERY_ALPHA`: Blending parameter when re-establishing tracking (default `0.25`).

### Pinch Hysteresis Thresholds:
- `PINCH_START_THRESHOLD`: Normalized thumb-to-index distance below which a pinch is registered (default `0.15`).
- `PINCH_RELEASE_THRESHOLD`: Normalized distance above which the pinch is released (default `0.30`).
- `PINCH_ENTER_FRAMES`: Stable frames required to enter a pinch state (default `2`).
- `PINCH_EXIT_FRAMES`: Stable frames required to exit a pinch state (default `3`).

---

## 3. One Euro Filter Parameters

- `FILTER_MIN_CUTOFF`: Minimum cutoff frequency in Hz. Lower values reduce jitter during slow movements (default `1.0`).
- `FILTER_BETA`: Speed-adaptive coefficient. Larger values reduce latency during fast movements (default `0.05`).
- `FILTER_D_CUTOFF`: Cutoff frequency for derivative velocity smoothing (default `1.0`).

---

## 4. Stroke Processing Constants

- `STROKE_SPIKE_MAX_ANGLE`: Turn angle threshold in degrees to flag a spike corner (default `120.0`).
- `STROKE_SPIKE_MAX_LENGTH`: Maximum length of segment in pixels allowed to prune a spike (default `25.0`).
- `HOOK_ANGLE_THRESHOLD`: Hook turn angle threshold in degrees (default `80.0`).
- `HOOK_MAX_LEN`: Maximum hook stroke length in pixels (default `15.0`).

---

## 5. OCR & Persistence Defaults

- `OCR_WHITELIST`: Allowed characters for OCR single line matching.
- `AUTO_SAVE_INTERVAL`: Interval in seconds for saving the workspace backup (default `300`).
