# Plugin System & Extensible Architecture

This document details Ekora's plugin system and modular feature extension framework.

---

## 1. Plugin Lifecycle

Ekora features an event-driven plugin architecture managed by `PluginManager` (`app/plugin_system.py`).

Plugins implement the `Plugin` protocol:
- `name`: Display name of the plugin.
- `description`: Overview of plugin functionality.
- `initialize(event_bus)`: Subscribes plugin event handlers to the central `EventBus`.
- `shutdown()`: Unsubscribes event handlers cleanly when the application exits.

All plugins reside in the `plugins/` directory and export a `register_plugin()` entrypoint.

---

## 2. Active Plugins

### Optical Character Recognition (OCR) Plugin (`plugins/ocr_plugin.py`)
- Subscribes to `OCR_SELECTION_STARTED` and `PLUGIN_OCR_REQUESTED`.
- Evaluates user crop bounding boxes using OpenCV image statistics.
- Preprocesses canvas crops via adaptive image enhancement pipelines (`Baseline`, `Grayscale`, `Otsu`, `Adaptive`, `CLAHE`).
- Leverages Tesseract OCR (`TesseractOCRProvider`) on background threads to extract text without blocking the UI.
- Emits `PLUGIN_ADD_SHAPE` to overlay editable vector `text` shapes directly on the document layer.

---

## 3. Failure Isolation & Validation

Plugins execute external or computationally heavy operations on background threads to keep the main drawing loop responsive at 60+ FPS.

1. **Thread Safety**: Long-running operations communicate with the UI renderer via thread-safe `EventBus` message events and non-blocking toast notifications.
2. **Graceful Error Handling**: Engine exceptions (e.g. missing Tesseract binary) are caught in the plugin worker thread, publishing user-friendly error dialogs rather than interrupting the core rendering loop.
