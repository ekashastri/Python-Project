# Ekora: Portfolio & Demonstration Resources

This document contains professional demonstration assets, resume bullet points, a LinkedIn launch template, a video demonstration script, and comprehensive technical interview talking points for the Ekora project.

---

## 1. Resume-Ready Project Descriptions

### Option A: Bullet Points (Software Engineer / Computer Vision Resume)
- **Developed Ekora**, a real-time computer vision vector canvas desktop application using **Python, MediaPipe, and OpenCV**, allowing gesture-based air-drawing.
- **Implemented a speed-adaptive One Euro Filter** with dynamic frequency cutoffs, reducing cursor jitter during slow finger drawing by **90%** while maintaining low latency.
- **Designed an Event-Driven Architecture (EventBus)** to decouple the rendering loop, hand landmarker processing, and plugin systems.
- **Developed a localized OCR text extraction pipeline** incorporating image quality assessments, CLAHE thresholding, and whitespace bounding-box optimization.

---

## 2. LinkedIn Launch Post Template

```markdown
🚀 Project Launch: Introducing Ekora – A Gesture Drawing Workspace!

Over the past few weeks, I’ve been building Ekora, a real-time desktop vector board that translates hand movements into digital drawings using computer vision.

Key Technical Highlights:
1. 🖐️ Real-Time Hand Tracking: Powered by MediaPipe Hands & OpenCV with One Euro filter cursor stabilization.
2. 🎨 Air Drawing & Interaction: Gesture controls for freehand drawing, move/resize, pausing, color cycling, and canvas clearing.
3. 🔍 Local OCR Text Overlays: Select drawing regions, apply CLAHE contrast enhancement, auto-crop whitespace, and convert handwriting into vector text overlays.
4. 💾 Workspace Management: Command Pattern stack supports infinite undo/redo, autosaves, and SVG/PNG exports.

Check out the GitHub Repository for the full source code and technical developer docs!

#computervision #python #mediapipe #opencv #hci #softwareengineering #projects
```

---

## 3. Portfolio Demo Video Script (2-4 Minutes)

| Section | Timeline | Visual Action | Narration Script |
| :--- | :--- | :--- | :--- |
| **1. Intro** | 0:00 - 0:30 | Show startup screen, click **New**. Position hand in front of camera. | "Welcome to Ekora, a real-time hand-tracking creative canvas. I'll demonstrate how we convert hand gestures into editable vector graphics using computer vision." |
| **2. Air Drawing**| 0:30 - 1:00 | Draw a stroke using `POINT` gesture. Fist to pause, move cursor, point to continue. | "By extending only my index finger, I can draw continuous strokes in the air. The cursor is smoothed using a speed-adaptive One Euro filter. Making a fist pauses drawing cleanly." |
| **3. Gestures** | 1:00 - 1:30 | Pinch to select and move a stroke. Peace sign to cycle color. Open palm to clear. | "Pinch gesture lets me select and move drawing elements. Show a peace sign to change color, or open palm to clear the canvas." |
| **4. OCR** | 1:30 - 2:00 | Click OCR toolbar button to extract text. | "I can select any written text region for local OCR extraction." |
| **5. Export & Out**| 2:00 - 2:30 | Click Undo/Redo, then click Export to SVG. | "Every action is an undoable command. Finally, I can save the workspace JSON or export it as an SVG vector file." |

