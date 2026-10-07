# Release Notes - Ekora v1.0.0 – Initial Stable Release

We are excited to announce the initial stable release of **Ekora (v1.0.0)**, a gesture drawing workspace that combines real-time hand tracking, freehand vector graphics, and OCR into a clean desktop application.

Ekora transforms physical hand movements from a standard webcam feed into high-fidelity vector drawings and extracts text locally.

---

## Major Features

### 1. Unified Event-Driven Architecture
- A decoupled, publish-subscribe system utilizing a central `EventBus`.
- Commands for workspace edits (add, delete, translate, modify) are fully encapsulated using the **Command Pattern** supporting infinite Undo/Redo operations.
- Modular, dynamically discovered **Plugin System** for OCR.

### 2. High-Performance Gesture Recognition
- **MediaPipe Hand Tracking** runs real-time hand landmark detection.
- **POINT Gesture (Index finger extended)** starts or continues freehand drawing.
- **FIST Gesture (Closed fist)** pauses drawing, allowing free pointer movement without creating jump lines. Disjoint stroke synchronization handles splits via `None` coordinate delimiters.
- **OPEN PALM Gesture (Hand open)** clears canvas, debounced with a 150ms hold to prevent accidental wipes.
- **PINCH Gesture (Index + Thumb touching)** translates and pans the viewport layout.
- **PEACE Gesture (Peace sign)** cycles colors.
- **One Euro Filter** stabilizes pointer coordinates using speed-adaptive dynamic smoothing coefficients.

### 3. Advanced OCR Text Overlay
- Drag selection box to crop handwriting/drawing canvas regions.
- Bounding box optimization trims empty whitespace.
- Text preview and edit dialog before placing extracted text as editable vector objects.
- Adaptive preprocessing pipelines run in background threads.

### 4. Export Standards & Persistence
- Export projects to **SVG** vector format or **PNG** raster snapshots.
- Workspace serialization persists configurations and layers to native `.ekora` format.
- Automatic crash detection prompts recovery on restart.

---

## Project Documentation
Complete manuals and deep dives are available under the `docs/` folder:
- **`architecture.md`**: Event structures, rendering pipelines, sequence diagrams.
- **`gesture_pipeline.md`**: Tracking math, One Euro equations, and hysteresis frames.
- **`ocr.md`**: DPI scaling, channel validation, and text quality scoring.
- **`plugins.md`**: Plugin system and background thread execution architecture.
- **`developer_guide.md`**: Guide to extending gestures, shapes, and plugins.

---

## Known Limitations
- Hand tracking accuracy is sensitive to extreme backlighting or low ambient lighting.
