# Developer Guide & Extension Manual

This guide explains how to extend Ekora, run tests, and adhere to coding standards.

---

## 1. How to Add a New Gesture

Gestures are defined in `app/gesture_detector.py`. To add a new gesture:

1. **Register the enum value**:
   Add your gesture name to the `Gesture` enum in `app/gesture_detector.py`:
   ```python
   class Gesture(Enum):
       ...
       NEW_GESTURE = auto()
   ```
2. **Add a HUD label**:
   Map your gesture in `GESTURE_LABELS`:
   ```python
   GESTURE_LABELS = {
       ...
       Gesture.NEW_GESTURE: "New Action Running",
   }
   ```
3. **Write the classification criteria**:
   Implement a helper checking finger states in `_raw_gesture(self, norm)`:
   ```python
   # Example: Checking if middle and ring fingers are up
   if middle_up and ring_up and not index_up:
       return "NEW_RAW", finger_states
   ```
4. **Map raw outputs to your Enum**:
   Update `_map_raw_to_gesture(self, raw)` to map `"NEW_RAW"` to `Gesture.NEW_GESTURE`.
5. **Handle Action Triggers**:
   Update the main application event loop in `main.py` under `_handle_gesture` to perform your action.

---

## 2. How to Add a Vector Shape Render Type

Vector shape rendering is managed in `app/drawing_engine.py`.

1. **Update the clean rendering function**:
   Add your shape type to `_draw_clean_shape` in `app/drawing_engine.py` using OpenCV primitives:
   ```python
   elif stype == "hexagon":
       pts = np.array(params["pts"], dtype=np.int32)
       cv2.polylines(canvas, [pts], isClosed=True, color=color, thickness=thickness)
   ```
2. **Configure Viewport Scaling**:
   Update `_render_shape` and `_render_selection_overlay` in `app/drawing_engine.py` to scale your shape coordinates from document to screen space.
3. **Update Export Schemas**:
   Add translation logic to `to_svg()` in `app/workspace_manager.py` to render your shape using SVG primitives (e.g., `<polygon>`).

---

## 3. How to Add a New Plugin

Plugins implement the lifecycle hook model in `app/plugin_system.py`.

1. **Subclass Plugin**:
   Create a new plugin file in `plugins/` subclassing `Plugin`:
   ```python
   from app.plugin_system import Plugin
   
   class CustomPlugin(Plugin):
       def initialize(self, event_bus) -> None:
           self.event_bus = event_bus
           self.event_bus.subscribe(EventType.TARGET_EVENT, self.handle_action)
   ```
2. **Register event in event_bus.py**:
   If needed, add your event to `EventType` in `app/event_bus.py`.
3. **Expose register_plugin**:
   Provide a `register_plugin()` function in your plugin module so `PluginManager` discovers it automatically.

---

## 4. How to Add a New Export Format

Export formats are dispatched in `main.py` inside `handle_export`.

1. **Extend Export UI Dialog**:
   Update the hover buttons in `show_export_prompt` in `app/ui.py` to let the user select the new format.
2. **Implement format serialization**:
   Create a serializer in `app/workspace_manager.py` (e.g., `to_pdf()`).
3. **Add file write dispatch**:
   Implement the write block in `handle_export` in `main.py`.

---

## 5. Coding Conventions

- **Type Hints**: All public method signatures must include parameters and return type annotations.
- **Color Format**: BGR tuple representation throughout the rendering engine (matching OpenCV's native structure).
- **Coordinate Spaces**: Keep screen coordinates and document coordinates clearly separated. Document coordinates are zoom-independent; screen coordinates are transformed by the viewport before rendering.
- **Defensive guards**: Always verify that file handles, camera objects, and landmarks are not `None` before referencing properties.
