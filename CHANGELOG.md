# Changelog

All notable changes to the Ekora project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Removed
- Smart and composite shape recognition; freehand strokes are no longer converted into shapes.

---

## [1.0.0] - 2026-07-05

### Added
- **Gesture Drawing**: Real-time camera-based drawing using normalized hand coordinates.
- **OCR Text overlay**: Crop, pre-check, clean, and overlay handwriting/drawings as editable vector text.
- **Workspace Persistence**: Automatic crash recovery cache, JSON save/load state formats.
- **SVG & PNG Exports**: Scale-independent SVG vector file formatting and PNG frame captures.
- **Plugin Architecture**: Modular plugin lifecycle handles asynchronous event publishers.

### Changed
- **Gesture Stabilization**: Refined the One Euro Filter coefficients for smoother slow drawing strokes and reduced latency during fast sweeps.
- **OCR Preprocessing Pipeline**: Reorganized filters to try simple default pathways first, run fallback pipelines dynamically, and utilize adaptive upscaling for low-contrast text.

### Fixed
- **Gesture Synchronization**: Resolved the drawing stroke continuation regression by inserting a `None` delimiter during fist-pause intervals, eliminating long coordinate jumps.
- **OCR Regression**: Fixed Tesseract failures on light and dark canvases by implementing explicit channel validation, background inversions, and text quality scoring.
- **Various UI Bugs**: Fixed settings slider callbacks, colors resets, and window coordinates offset checks.
