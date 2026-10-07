# 🎨 Ekora

<p align="center">
  <h3 align="center">Gesture Drawing Workspace</h3>
  <p align="center">
    A gesture-controlled digital drawing workspace built with Python, OpenCV and MediaPipe.
  </p>
</p>

---

## 📌 Project Overview

Ekora is a 2nd-year B.Tech Computer Engineering project focused on exploring natural Human-Computer Interaction (HCI) using computer vision.

The application allows users to interact with a digital canvas using hand gestures captured through a webcam. Users can draw, erase, change colours, pause drawing, undo/redo their work, and extract text using OCR.

The project focuses on practical implementation of:

- Computer Vision
- Hand Tracking
- Gesture Recognition
- Digital Drawing
- Optical Character Recognition
- Basic software architecture

The current version intentionally focuses on a small set of reliable features rather than a large number of experimental features.

---

## ✨ Core Features

### 🖐️ Hand Tracking & Gesture Control

Ekora uses MediaPipe to track hand landmarks in real time.

| Gesture | Action |
|---|---|
| ☝️ Index Finger | Draw |
| 🤏 Pinch | Interact / Move |
| ✊ Fist | Pause Drawing |
| ✌️ Peace Sign | Change Colour |
| 🖐️ Open Palm | Erase |

The application also provides keyboard shortcuts for commonly used operations.

---

### 🎨 Digital Drawing Canvas

- Real-time freehand drawing
- Multiple colours
- Adjustable brush settings
- Eraser
- Clear canvas
- Pause and resume drawing
- Smooth gesture-based interaction

---

### ↩️ Undo & Redo

Ekora maintains drawing history to allow users to modify their work.

- Undo previous drawing actions
- Redo previously undone actions
- Clear individual drawing actions where supported

---

### 🔤 Optical Character Recognition (OCR)

Ekora integrates Tesseract OCR to extract text from selected areas of the canvas.

Basic workflow:

```text
Canvas
   ↓
Select Region
   ↓
Image Processing
   ↓
Tesseract OCR
   ↓
Extracted Text