"""
Ekora v2.2 – main entry point with decoupled cursor tracking and new gesture model.
"""

from __future__ import annotations

import sys
import os

import time
import threading
from pathlib import Path
from typing import Optional


import cv2
import numpy as np

import config
from app.camera import create_camera, ThreadedCamera
from app.workspace_manager import WorkspaceManager
from app.gesture_detector import Gesture, GestureDetector
from app.hand_tracker import HandLandmarks, HandTracker, ThreadedTracker
from app.cursor_tracker import CursorTracker
from app.virtual_pen import VirtualPen
from app.ui import UIRenderer, StartupResult
from app.event_bus import EventBus, EventType
from app.plugin_system import PluginManager


class Application:
    def __init__(self) -> None:
        self.app_settings = config.load_settings()
        self.is_running = True
        self.current_workspace_path: Optional[str] = None
        self.last_frame: Optional[np.ndarray] = None
        self.app_mode: str = "Idle"
        
        self.ocr_selecting = False
        self.ocr_rect_start = None
        self.ocr_rect_end = None
        self.ocr_selected_rect = None
        self.ocr_processing = False
        self.ocr_cancelled = False
        self.ocr_session_id = 0
        
        self.main_thread_actions = []
        
        # Stroke persistence state
        self.stroke_loss_start_time: Optional[float] = None
        self.lost_frame_counter: int = 0
        
        self.event_bus = EventBus()
        self._register_events()

        print("=" * 50)
        print("  Ekora – Virtual Finger Drawing v2.2")
        print("=" * 50)
        print("\nStarting camera and hand tracker…\n")

        self.camera = ThreadedCamera(create_camera())
        self.tracker = ThreadedTracker(HandTracker())
        self.cursor_tracker = CursorTracker()
        self.virtual_pen = VirtualPen()
        self.gestures = GestureDetector()
        self.canvas = WorkspaceManager()
        self.ui = UIRenderer(self.event_bus)
        self.event_bus.subscribe(EventType.FLASH_MESSAGE, self.ui.flash_message)
        
        self.plugin_manager = PluginManager(self.event_bus)
        self.plugin_manager.discover_and_load()
        
        self.window_name = config.WINDOW_NAME
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, config.CAMERA_WIDTH, config.CAMERA_HEIGHT)

        self._recover_autosave()

        self.ui.set_camera_mode(self.app_settings.get("camera_mode", config.CAMERA_MODE_DARK_OVERLAY))

    def _register_events(self) -> None:
        self.event_bus.subscribe(EventType.WORKSPACE_NEW, self.handle_new_workspace)
        self.event_bus.subscribe(EventType.WORKSPACE_OPEN, self.handle_open_workspace)
        self.event_bus.subscribe(EventType.WORKSPACE_SAVE, self.handle_save_workspace)
        self.event_bus.subscribe(EventType.WORKSPACE_SAVE_AS, self.handle_save_as)
        self.event_bus.subscribe(EventType.WORKSPACE_SHOW_RECENT, self.handle_recent)
        self.event_bus.subscribe(EventType.WORKSPACE_EXPORT, self.handle_export)
        self.event_bus.subscribe(EventType.SETTINGS_OPEN, self.handle_settings)
        self.event_bus.subscribe(EventType.HELP_REQUESTED, self.handle_help)
        self.event_bus.subscribe(EventType.ABOUT_REQUESTED, self.handle_about)
        self.event_bus.subscribe(EventType.BRUSH_SIZE_CHANGED, self.handle_brush_size)
        self.event_bus.subscribe(EventType.PLUGIN_ADD_SHAPE, self.handle_plugin_add_shape)
        self.event_bus.subscribe(EventType.OCR_SELECTION_STARTED, self.handle_ocr_selection_started)
        self.event_bus.subscribe(EventType.SHOW_ERROR_DIALOG, self.handle_show_error_dialog)
        self.event_bus.subscribe(EventType.CANVAS_UNDO, lambda *a: self.canvas.undo())
        self.event_bus.subscribe(EventType.CANVAS_REDO, lambda *a: self.canvas.redo())

    def _recover_autosave(self) -> None:
        autosave_path = Path(__file__).parent / ".autosave.ekora"
        if autosave_path.exists():
            ok, frame = self.camera.read()
            if ok and frame is not None:
                base = cv2.resize(frame, (config.CAMERA_WIDTH, config.CAMERA_HEIGHT))
                if self.ui.show_recovery_prompt(base):
                    with open(autosave_path, "r", encoding="utf-8") as f:
                        self.canvas.from_json(f.read())
                    self.canvas.is_dirty = True
                    self.ui.flash_message("Recovered workspace!")
            autosave_path.unlink()

    def _add_recent_file(self, path: str) -> None:
        recent = self.app_settings.get("recent_files", [])
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        self.app_settings["recent_files"] = recent[:5]
        config.save_settings(self.app_settings)

    def _check_unsaved(self) -> bool:
        if self.canvas.is_dirty:
            res = self.ui.show_unsaved_prompt(self.last_frame)
            self._set_mouse_callback()
            if res == "save":
                self.handle_save_workspace()
                return True
            elif res == "discard":
                return True
            return False
        return True

    def handle_new_workspace(self, *args, **kwargs) -> None:
        if not self._check_unsaved(): return
        self.current_workspace_path = None
        self.canvas.clear()
        self.canvas.is_dirty = False
        self.ui.flash_message("New Workspace")

    def handle_open_workspace(self, path: str = None, *args, **kwargs) -> None:
        if not self._check_unsaved(): return
        
        if not path:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askopenfilename(
                title="Open Workspace",
                filetypes=[("Ekora Workspace", "*.ekora"), ("PNG Image", "*.png"), ("All files", "*.*")],
            )
            root.destroy()
            
        if path:
            try:
                if path.endswith(".ekora"):
                    with open(path, "r", encoding="utf-8") as file:
                        self.canvas.import_workspace(file.read())
                else:
                    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
                    if img is not None:
                        self.canvas.load_canvas(img)
                    else:
                        self.ui.flash_message("Could not open image")
                        return
                self.current_workspace_path = path
                self._add_recent_file(path)
                self.ui.flash_message(f"Opened: {Path(path).name}")
            except Exception as e:
                self.ui.flash_message(f"Load failed: {e}")

    def handle_save_workspace(self, *args, **kwargs) -> None:
        if self.current_workspace_path:
            if self.current_workspace_path.endswith(".ekora"):
                with open(self.current_workspace_path, "w", encoding="utf-8") as f:
                    f.write(self.canvas.to_json())
            else:
                cv2.imwrite(self.current_workspace_path, self.canvas.get_canvas())
            self.canvas.is_dirty = False
            self.ui.flash_message(f"Saved: {Path(self.current_workspace_path).name}")
        else:
            self.handle_save_as()

    def handle_save_as(self, *args, **kwargs) -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.asksaveasfilename(
                title="Save As",
                defaultextension=".ekora",
                filetypes=[("Ekora Workspace", "*.ekora"), ("PNG Image", "*.png"), ("All files", "*.*")],
            )
            root.destroy()
            if path:
                if path.endswith(".ekora"):
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(self.canvas.to_json())
                else:
                    cv2.imwrite(path, self.canvas.get_canvas())
                self.current_workspace_path = path
                self.canvas.is_dirty = False
                self._add_recent_file(path)
                self.ui.flash_message(f"Saved: {Path(path).name}")
        except Exception as e:
            self.ui.flash_message(f"Save failed: {e}")

    def handle_recent(self, *args, **kwargs) -> None:
        recent = self.app_settings.get("recent_files", [])
        valid_recent = [p for p in recent if Path(p).exists()]
        if len(valid_recent) != len(recent):
            self.app_settings["recent_files"] = valid_recent
            config.save_settings(self.app_settings)
            
        path = self.ui.show_recent_files(self.last_frame, valid_recent)
        self._set_mouse_callback()
        if path:
            self.handle_open_workspace(path)

    def handle_export(self, *args, **kwargs) -> None:
        res = self.ui.show_export_prompt(self.last_frame)
        self._set_mouse_callback()
        if not res: return
        
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        ext = res["format"]
        path = filedialog.asksaveasfilename(
            title="Export As",
            defaultextension=f".{ext}",
            filetypes=[(f"{ext.upper()} Image", f"*.{ext}")],
        )
        root.destroy()
        if path:
            if path.lower().endswith(".svg"):
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.canvas.to_svg())
            else:
                if res["bg"]:
                    sw = config.SIDEBAR_WIDTH
                    comp = self.last_frame.copy()
                    roi = comp[:, sw:]
                    canvas_roi = self.canvas.export_canvas(bg_color=(0, 0, 0))[:, sw:]
                    mask = cv2.cvtColor(canvas_roi, cv2.COLOR_BGR2GRAY)
                    _, mask = cv2.threshold(mask, 1, 255, cv2.THRESH_BINARY)
                    mask_inv = cv2.bitwise_not(mask)
                    bg = cv2.bitwise_and(roi, roi, mask=mask_inv)
                    fg = cv2.bitwise_and(canvas_roi, canvas_roi, mask=mask)
                    blended = cv2.add(bg, fg)
                    comp[:, sw:] = blended
                    cv2.imwrite(path, comp)
                else:
                    cv2.imwrite(path, self.canvas.export_canvas(bg_color=(255, 255, 255)))
            self.ui.flash_message(f"Exported: {Path(path).name}")

    def handle_settings(self, *args, **kwargs) -> None:
        settings = self.ui.show_settings_prompt(self.last_frame)
        self._set_mouse_callback()
        self.app_settings.update(settings)
        self.ui.set_camera_mode(settings.get("camera_mode", config.CAMERA_MODE_DARK_OVERLAY))
        self.ui.flash_message("Settings Updated")

    def handle_help(self, *args, **kwargs) -> None:
        shortcuts = [
            "Ctrl+N : New Workspace",
            "Ctrl+O : Open Workspace",
            "Ctrl+S : Save Workspace",
            "Ctrl+Shift+S : Save As",
            "Ctrl+Z : Undo",
            "Ctrl+Y : Redo",
            "Delete : Clear Canvas",
            "Esc    : Quit",
        ]
        self.ui.show_info_dialog(self.last_frame, "Keyboard Shortcuts", shortcuts)
        self._set_mouse_callback()

    def handle_about(self, *args, **kwargs) -> None:
        lines = [
            "Ekora",
            "Think. Sketch. Create.",
            "Version 2.2",
            "Developer: AI Assistant",
            "GitHub repository: (Local)",
            "License: MIT",
        ]
        self.ui.show_info_dialog(self.last_frame, "About", lines)
        self._set_mouse_callback()

    def handle_brush_size(self, new_size: int) -> None:
        self.canvas.brush_size = new_size
        self.canvas.eraser_size = new_size
        
    def handle_canvas_clear(self, *args, **kwargs) -> None:
        self.canvas.clear()
        self.ui.flash_message("Canvas Cleared")

    def handle_plugin_add_shape(self, shape_type: str, params: dict, color: tuple, size: int) -> None:
        from app.model import Shape, Stroke
        from app.commands import AddItemCommand
        
        # Make a copy of params to avoid in-place modification side effects
        params_copy = params.copy()
        
        if shape_type == "stroke":
            points = params_copy.get("points", [])
            # Convert screen coordinates to document coordinates using the current viewport
            doc_pts = [self.canvas.viewport.screen_to_doc((float(p[0]), float(p[1]))) for p in points]
            stroke = Stroke(doc_pts, color, size)
            self.canvas.commands.execute(AddItemCommand(stroke, self.canvas.document.active_layer_index))
        else:
            # Convert basic shape parameters from screen space to document space
            self.canvas._convert_params_to_doc(shape_type, params_copy)
            shape = Shape(shape_type, params_copy, color, size)
            self.canvas.commands.execute(AddItemCommand(shape, self.canvas.document.active_layer_index))
            
        self.canvas.is_dirty = True

    def handle_ocr_selection_started(self, *args, **kwargs) -> None:
        self.ocr_mode_active = True
        self.ocr_selecting = False
        self.ocr_rect_start = None
        self.ocr_rect_end = None
        self.ocr_selected_rect = None
        self.ocr_processing = False
        self.ocr_cancelled = False

    def _mouse_handler(self, event: int, mx: int, my: int, flags: int, param) -> None:
        if getattr(self, "ocr_mode_active", False):
            if event == cv2.EVENT_LBUTTONDOWN:
                # Check if cancel button (❌) was clicked
                if 905 <= mx <= 932 and 25 <= my <= 52:
                    self.ocr_mode_active = False
                    self.ocr_selecting = False
                    self.ocr_rect_start = None
                    self.ocr_rect_end = None
                    self.ocr_selected_rect = None
                    self.ocr_cancelled = True
                    self.ui.flash_message("OCR Mode Disabled")
                    return
                self.ocr_selecting = True
                self.ocr_rect_start = (mx, my)
                self.ocr_rect_end = (mx, my)
            elif event == cv2.EVENT_MOUSEMOVE and getattr(self, "ocr_selecting", False):
                self.ocr_rect_end = (mx, my)
            elif event == cv2.EVENT_LBUTTONUP and getattr(self, "ocr_selecting", False) and getattr(self, "ocr_rect_start", None):
                self.ocr_rect_end = (mx, my)
                self.ocr_selecting = False
                self.ocr_mode_active = False
                x1, y1 = self.ocr_rect_start
                x2, y2 = self.ocr_rect_end
                rx1, rx2 = min(x1, x2), max(x1, x2)
                ry1, ry2 = min(y1, y2), max(y1, y2)
                if rx2 - rx1 > 5 and ry2 - ry1 > 5:
                    self.ocr_selected_rect = (rx1, ry1, rx2, ry2)
                    frame = self.canvas.get_canvas()
                    crop = frame[ry1:ry2, rx1:rx2]
                    self.ocr_session_id += 1
                    self.event_bus.publish(
                        EventType.PLUGIN_OCR_REQUESTED,
                        image=crop,
                        rect=(rx1, ry1, rx2-rx1, ry2-ry1),
                        app=self,
                        session_id=self.ocr_session_id
                    )
                else:
                    self.ui.flash_message("OCR Selection too small")
            return

        # Check if an object is selected and the close/delete button (❌) was clicked
        if event == cv2.EVENT_LBUTTONDOWN and self.canvas.selected_item is not None:
            hit_item, hit_type = self.canvas.hit_test((mx, my))
            if hit_item == self.canvas.selected_item and hit_type == "delete":
                deleted_item = self.canvas.selected_item
                self.canvas.delete_selected_item()
                if getattr(self, "highlight_item", None) == deleted_item:
                    self.highlight_item = None
                self.ui.flash_message("Object Deleted")
                return

        self.ui.handle_mouse(event, mx, my, flags, self.canvas, self.canvas.brush_size)

    def _set_mouse_callback(self) -> None:
        self._mouse_callback_ref = lambda e, x, y, f, p: self._mouse_handler(e, x, y, f, p)
        cv2.setMouseCallback(self.window_name, self._mouse_callback_ref)

    def handle_show_error_dialog(self, title: str, lines: list, *args, **kwargs) -> None:
        if getattr(self, "last_frame", None) is not None:
            self.main_thread_actions.append(lambda: self.ui.show_info_dialog(self.last_frame, title, lines))

    def run(self) -> None:
        startup_result = self.ui.show_startup(config.CAMERA_WIDTH, config.CAMERA_HEIGHT)
        self._set_mouse_callback()
        if startup_result == StartupResult.QUIT:
            self.shutdown()
            return

        if startup_result == StartupResult.OPEN:
            self.handle_open_workspace()
        elif startup_result not in (StartupResult.NEW, StartupResult.QUIT):
            self.handle_open_workspace(startup_result)

        self._set_mouse_callback()

        print("Controls:")
        print("  Point (index finger)   → Draw")
        print("  Pinch (thumb + index)  → Interact/Move")
        print("  Fist                   → Pause drawing")
        print("  Peace sign             → Next colour")
        print("  Open palm              → Erase canvas")
        print("  Q / ESC                → Quit")
        print("  C                      → Clear canvas")
        print("  S                      → Quick save\n")

        prev_gesture = Gesture.NONE
        
        try:
            while self.is_running:
                # Process main thread actions
                while getattr(self, "main_thread_actions", []):
                    action = self.main_thread_actions.pop(0)
                    action()
                    
                ok, frame = self.camera.read()
                if not ok or frame is None:
                    time.sleep(0.005)
                    continue

                if frame.shape[1] != config.CAMERA_WIDTH or frame.shape[0] != config.CAMERA_HEIGHT:
                    frame = cv2.resize(frame, (config.CAMERA_WIDTH, config.CAMERA_HEIGHT))

                self.tracker.update_frame(frame)
                hand = self.tracker.get_latest_hand()
                # Update smooth cursor tracking
                raw_pos, tracker_pos, velocity = self.cursor_tracker.update(hand)
                
                if raw_pos is not None:
                    pen_pos = self.virtual_pen.process(raw_pos)
                else:
                    self.virtual_pen.reset()
                    pen_pos = tracker_pos
                
                gesture = Gesture.NONE
                confidence = 0.0
                finger_states = {}

                if hand is not None:
                    detected_gesture, confidence, finger_states = self.gestures.detect(hand, frame.shape[:2])
                else:
                    detected_gesture = Gesture.NONE
                    
                # Stroke Persistence Logic only applies to NONE (tracking loss)
                if self.gestures.stroke_active and detected_gesture == Gesture.NONE:
                    if self.stroke_loss_start_time is None:
                        self.stroke_loss_start_time = time.time()
                    self.lost_frame_counter += 1
                    
                    persistence_timeout = getattr(config, "STROKE_PERSISTENCE_TIMEOUT", 0.20)
                    if time.time() - self.stroke_loss_start_time < persistence_timeout:
                        gesture = Gesture.POINT
                    else:
                        gesture = detected_gesture
                        self.stroke_loss_start_time = None
                else:
                    gesture = detected_gesture
                    if gesture == Gesture.POINT:
                        self.stroke_loss_start_time = None
                        self.lost_frame_counter = 0

                if hand is not None or pen_pos is not None:
                    self.canvas.update_hover(pen_pos)
                    self._handle_gesture(gesture, prev_gesture, hand, pen_pos)
                    prev_gesture = gesture
                else:
                    # Complete loss of tracking
                    self._complete_stroke()
                    prev_gesture = Gesture.NONE

                display_frame = self.ui.apply_camera_mode(frame)

                if hand is not None:
                    self.tracker.draw_skeleton(display_frame, hand)

                composited = self.canvas.composite(display_frame)

                stroke_id = id(self.canvas._current_stroke) if self.canvas._current_stroke else 0
                
                output = self.ui.render(
                    composited,
                    gesture       = gesture,
                    brush_color   = self.canvas.brush_color,
                    brush_size    = self.canvas.brush_size,
                    hand_detected = hand is not None or pen_pos is not None,
                    cursor_pos    = pen_pos,
                    eraser_size   = self.canvas.eraser_size,
                    confidence    = confidence,
                    finger_states = finger_states,
                    app_mode      = self.app_mode,
                    raw_pos       = raw_pos,
                    velocity      = velocity,
                    raw_gesture   = self.gestures._candidate_raw,
                    stroke_active = self.gestures.stroke_active,
                    stroke_id     = stroke_id,
                    lost_frame_counter = self.lost_frame_counter,
                    prev_gesture_name = prev_gesture.name,
                    pinch_distance = self.gestures.last_pinch_distance,
                    selected_object = self.canvas.active_item.__class__.__name__ if getattr(self.canvas, 'active_item', None) else getattr(self.canvas, 'hovered_item', None).__class__.__name__ if getattr(self.canvas, 'hovered_item', None) else "None",
                )

                if getattr(self, "ocr_selecting", False) and getattr(self, "ocr_rect_start", None) and getattr(self, "ocr_rect_end", None):
                    x1, y1 = self.ocr_rect_start
                    x2, y2 = self.ocr_rect_end
                    rx1, rx2 = min(x1, x2), max(x1, x2)
                    ry1, ry2 = min(y1, y2), max(y1, y2)
                    if rx2 - rx1 > 2 and ry2 - ry1 > 2:
                        dimmed = (output * 0.4).astype(np.uint8)
                        dimmed[ry1:ry2, rx1:rx2] = output[ry1:ry2, rx1:rx2]
                        output = dimmed
                    cv2.rectangle(output, (x1, y1), (x2, y2), (255, 150, 0), 2)

                if getattr(self, "ocr_selected_rect", None) is not None:
                    x1, y1, x2, y2 = self.ocr_selected_rect
                    cv2.rectangle(output, (x1, y1), (x2, y2), (255, 150, 0), 2)

                # Draw OCR instructions overlay
                if getattr(self, "ocr_mode_active", False):
                    overlay = output.copy()
                    cv2.rectangle(overlay, (340, 20), (940, 115), (40, 30, 25), -1)
                    cv2.addWeighted(overlay, 0.85, output, 0.15, 0, output)
                    cv2.rectangle(output, (340, 20), (940, 115), (150, 200, 0), 2) # Accent green border
                    
                    # Draw red cancel button (❌) inside the overlay at top-right
                    cv2.rectangle(output, (905, 25), (932, 52), (50, 50, 220), -1) # BGR Red
                    cv2.rectangle(output, (905, 25), (932, 52), (100, 100, 255), 1) # Border
                    cv2.putText(output, "X", (911, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 2, cv2.LINE_AA)
                    
                    lines = [
                        "OCR Mode Enabled",
                        "Drag with the mouse to select the text region.",
                        "Release to start recognition.",
                        "Press Esc to cancel."
                    ]
                    cv2.putText(output, lines[0], (350, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (150, 200, 0), 2, cv2.LINE_AA)
                    for idx, line in enumerate(lines[1:]):
                        cv2.putText(output, line, (350, 65 + idx * 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (240, 234, 232), 1, cv2.LINE_AA)

                cv2.imshow(self.window_name, output)
                self.last_frame = output.copy()
                
                if self.app_settings.get("auto_save", True):
                    if not hasattr(self.camera, "_last_autosave"):
                        self.camera._last_autosave = time.time()
                    if time.time() - self.camera._last_autosave > self.app_settings.get("auto_save_interval", 300):
                        if self.canvas.is_dirty:
                            def do_autosave(json_data, path):
                                try:
                                    with open(path, "w", encoding="utf-8") as f:
                                        f.write(json_data)
                                except Exception:
                                    pass
                            
                            autosave_path = Path(__file__).parent / ".autosave.ekora"
                            json_data = self.canvas.to_json()
                            threading.Thread(target=do_autosave, args=(json_data, autosave_path), daemon=True).start()
                            
                            self.ui.flash_message("Autosave completed")
                        self.camera._last_autosave = time.time()

                key = cv2.waitKey(1) & 0xFF
                if key == 27: # ESC
                    if getattr(self, "ocr_mode_active", False) or getattr(self, "ocr_selecting", False) or getattr(self, "ocr_selected_rect", None) is not None:
                        self.ocr_mode_active = False
                        self.ocr_selecting = False
                        self.ocr_rect_start = None
                        self.ocr_rect_end = None
                        self.ocr_selected_rect = None
                        self.ocr_cancelled = True
                        self.ui.flash_message("OCR Mode Disabled")
                    else:
                        if self._check_unsaved():
                            self.is_running = False
                elif key == 14:
                    self.handle_new_workspace()
                elif key == 15:
                    self.handle_open_workspace()
                elif key == 19:
                    self.handle_save_workspace()
                elif key == 26:
                    self.canvas.undo()
                elif key == 25:
                    self.canvas.redo()
                elif key in (8, 127):
                    if self.canvas.selected_item is not None:
                        deleted_item = self.canvas.selected_item
                        self.canvas.delete_selected_item()
                        if getattr(self, "highlight_item", None) == deleted_item:
                            self.highlight_item = None
                        self.ui.flash_message("Object Deleted")
                    else:
                        if self.canvas.delete_hovered_shape():
                            self.ui.flash_message("Object Deleted")
                elif key in (ord("c"), ord("C")):
                    self.handle_canvas_clear()
                elif key in (ord("o"), ord("O")):
                    self.event_bus.publish(EventType.OCR_SELECTION_STARTED)
                elif key in (ord("s"), ord("S")):
                    self.handle_save_workspace()
                elif key in (ord("r"), ord("R")):
                    self.canvas.set_color(config.DEFAULT_BRUSH_COLOR)
                elif key == ord("="): # Plus key for zoom in
                    self.canvas.viewport.zoom *= 1.1
                    self.canvas.is_dirty = True
                elif key == ord("-"): # Minus key for zoom out
                    self.canvas.viewport.zoom /= 1.1
                    self.canvas.is_dirty = True
                # Arrow keys for pan (OpenCV keys vary by OS, but let's use WASD for reliability)
                elif key in (ord("w"), ord("W")):
                    self.canvas.viewport.pan_y += 50
                    self.canvas.is_dirty = True
                elif key in (ord("s"), ord("S")):
                    self.canvas.viewport.pan_y -= 50
                    self.canvas.is_dirty = True
                elif key in (ord("a"), ord("A")):
                    self.canvas.viewport.pan_x += 50
                    self.canvas.is_dirty = True
                elif key in (ord("d"), ord("D")):
                    self.canvas.viewport.pan_x -= 50
                    self.canvas.is_dirty = True

        except KeyboardInterrupt:
            print("\nInterrupted by user.")
        finally:
            self.shutdown()

    def _complete_stroke(self) -> None:
        self.canvas.end_stroke()
        self.gestures.stroke_active = False

    def _handle_gesture(
        self,
        gesture: Gesture,
        prev_gesture: Gesture,
        hand: Optional[HandLandmarks],
        cursor_pos: Optional[tuple[int, int]],
    ) -> None:
        if not cursor_pos:
            return

        # 0. Global state cleanup on transition
        if prev_gesture != gesture:
            # Exiting PINCH
            if prev_gesture == Gesture.PINCH:
                if getattr(self.canvas, 'active_item', None) is not None:
                    self.canvas.end_interaction()
                else:
                    self.canvas.end_pan()
            # Exiting POINT
            if prev_gesture == Gesture.POINT:
                # If we transition to FIST, we pause/freeze the stroke, do NOT complete it yet
                if gesture != Gesture.FIST:
                    self._complete_stroke()
            # Exiting FIST
            if prev_gesture == Gesture.FIST:
                # If we transition to anything other than POINT, finalize the paused stroke
                if gesture != Gesture.POINT:
                    self._complete_stroke()

        # 1. PINCH -> MOVE MODE (Strictly no drawing)
        if gesture == Gesture.PINCH:
            self.app_mode = "Move"
            if prev_gesture != Gesture.PINCH:
                hit_item, hit_type = self.canvas.hit_test(cursor_pos)
                if hit_item is not None:
                    # If we pinched the delete button of the selected item
                    if hit_type == "delete" and hit_item == self.canvas.selected_item:
                        self.canvas.delete_selected_item()
                    else:
                        self.canvas.selected_item = hit_item
                        self.canvas.start_interaction(cursor_pos)
                else:
                    self.canvas.selected_item = None
                    self.canvas.start_pan(cursor_pos)
            else:
                if getattr(self.canvas, 'active_item', None) is not None:
                    self.canvas.continue_interaction(cursor_pos)
                else:
                    self.canvas.continue_pan(cursor_pos)

        # 2. OPEN PALM -> CLEAR
        elif gesture == Gesture.OPEN_PALM:
            self.app_mode = "Erase"
            if prev_gesture != Gesture.OPEN_PALM:
                self.handle_canvas_clear()
                self.ui.flash_message("Canvas Cleared!")
                
        # 3. FIST -> PAUSE MODE (Strictly pause, no erase/delete)
        elif gesture == Gesture.FIST:
            self.app_mode = "Pause"

        # 4. POINT -> DRAW MODE (Strictly index finger only)
        elif gesture == Gesture.POINT:
            self.app_mode = "Brush"
            if prev_gesture != Gesture.POINT and prev_gesture != Gesture.FIST:
                self.canvas.start_stroke(cursor_pos)
                self.gestures.stroke_active = True
            else:
                if prev_gesture == Gesture.FIST:
                    self.canvas.pause_stroke()
                self.canvas.continue_stroke(cursor_pos, eraser=False)
                self.gestures.stroke_active = True
                
        # 5. PEACE (Cycle Color)
        elif gesture == Gesture.PEACE:
            self.app_mode = "Idle"
            if prev_gesture != Gesture.PEACE:
                self.canvas.cycle_color()
                self.ui.flash_message("Color Changed!")
                
        # 6. IDLE / NONE
        else:
            self.app_mode = "Idle"

    def shutdown(self) -> None:
        print("Shutting down…")
        self.plugin_manager.shutdown_all()
        self.tracker.close()
        self.camera.release()
        cv2.destroyAllWindows()
        print("Goodbye!")


def main() -> None:
    app = Application()
    app.run()


if __name__ == "__main__":
    main()
