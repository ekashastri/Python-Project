# Ekora User & Operations Guide

This guide covers drawing workflows, gesture controls, saving/opening files, exporting vector layouts, keyboard shortcuts, and troubleshooting instructions.

---

## 1. General Drawing Workflows

- **Mouse Control**: Click and drag to draw lines. Double-click a shape to select it for translation or resizing.
- **Color Selection**: Cycle brush color using the palette picker in the toolbar.
- **Stroke Width**: Drag the slider in the topbar to change the brush/eraser thickness.

---

## 2. Gesture Control Guide

To control Ekora using hand tracking, position your hand within the webcam preview frame:

| Gesture Name | Hand Pose Description | Map Action |
| :--- | :--- | :--- |
| **POINT** | Extend index finger only | Continuous freehand drawing |
| **FIST** | Curl all 5 fingers | Pause active stroke (retains drawing segment) |
| **OPEN PALM** | Extend 4 or 5 fingers | Clear canvas (fires after a 150ms hold) |
| **PINCH** | Touch thumb and index tips | Drag and pan the viewport layout |
| **PEACE** | Extend index and middle | Unused (reserved for color cycling) |

---

## 3. OCR Text Extraction Workflow

1. Click the **OCR** button on the toolbar or press `O`/`o` on the keyboard.
2. The preview dims. Click and drag a bounding region over the target text.
3. The status card updates (Preparing $\to$ Enhancing $\to$ OCR $\to$ Extracting $\to$ Creating).
4. The cropped text is converted into an editable vector `text` shape, placed exactly over the screen area.

---

## 4. Saving, Opening, and Exporting Workspaces

- **Save workspace**: Saves drawing layers to JSON format (`.ekora`).
- **Open workspace**: Opens a `.ekora` file and restores undo history.
- **Export SVG**: Exports the workspace as clean, scalable vector graphics (.svg).
- **Export PNG**: Exports the workspace as a rasterized image (.png).

---

## 5. Complete Keyboard Shortcut Reference

| Key Shortcut | Action Performed |
| :--- | :--- |
| `S` or `s` | Quick Save active workspace |
| `O` or `o` | Launch OCR selection region |
| `C` or `c` | Clear active canvas layers |
| `R` or `r` | Reset color palette |
| `=` (Plus) | Zoom In |
| `-` (Minus) | Zoom Out |
| `W`, `A`, `S`, `D` | Pan Viewport Up, Left, Down, Right |
| `Ctrl + Z` | Undo last action |
| `Ctrl + Y` | Redo last undone action |
| `Backspace` or `Delete` | Delete selected shape or hovered shape |
| `ESC` | Cancel current mode or quit application |

---

## 7. Troubleshooting Common Issues

### 1. Camera Failing to Initialize
- **Error**: `[Camera Error] Cannot open camera...`
- **Solution**:
  - Close other programs using the camera (Zoom, Teams, Discord).
  - Open `config.py` and adjust `CAMERA_INDEX` (e.g. try `1` or `2` if using an external USB webcam).

### 2. High Jitter or Flickering Cursor
- **Symptom**: The cursor snaps around the screen rapidly.
- **Solution**:
  - Increase face/palm illumination.
  - Adjust One Euro filter values in `config.py` (increase `FILTER_MIN_CUTOFF`).

### 3. OCR Output is Inaccurate
- **Symptom**: Extracted text contains garbled characters.
- **Solution**:
  - Draw larger and cleaner.
  - Crop tightly around the target words to exclude adjacent lines.
