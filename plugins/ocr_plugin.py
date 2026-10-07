import cv2
import numpy as np
from typing import Optional, Tuple
from app.plugin_system import Plugin
from app.event_bus import EventBus, EventType
from app.services.interfaces import IOCRProvider


def trim_whitespace(image: np.ndarray) -> Tuple[np.ndarray, Tuple[int, int, int, int]]:
    """Trim empty background space from the edges of the image crop."""
    if image is None or image.size == 0:
        return image, (0, 0, 0, 0)
    
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image.copy()
    mean_val = np.mean(gray)
    
    # Threshold to find foreground text/drawing
    if mean_val > 127:
        # Light background
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    else:
        # Dark background
        _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
        
    coords = np.column_stack(np.where(thresh > 0))
    h, w = image.shape[:2]
    if len(coords) == 0:
        return image, (0, 0, w, h)
        
    y_min, x_min = coords.min(axis=0)
    y_max, x_max = coords.max(axis=0)
    
    # Add a small safety padding
    padding = 6
    y_min = max(0, y_min - padding)
    x_min = max(0, x_min - padding)
    y_max = min(h, y_max + padding)
    x_max = min(w, x_max + padding)
    
    trimmed = image[y_min:y_max, x_min:x_max]
    return trimmed, (int(x_min), int(y_min), int(x_max - x_min), int(y_max - y_min))


class OCRPlugin(Plugin):
    @property
    def name(self) -> str:
        return "OCR Plugin"

    @property
    def description(self) -> str:
        return "Provides Optical Character Recognition capabilities."

    def __init__(self, provider: IOCRProvider):
        self.provider = provider
        self.event_bus = None

    def initialize(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.event_bus.subscribe(EventType.PLUGIN_OCR_REQUESTED, self.handle_ocr_request)

    def shutdown(self) -> None:
        self.event_bus.unsubscribe(EventType.PLUGIN_OCR_REQUESTED, self.handle_ocr_request)
        
    def handle_ocr_request(self, *args, **kwargs) -> None:
        import threading
        
        app = kwargs.get("app", None)
        session_id = kwargs.get("session_id", 0)
        
        if app:
            app.ocr_cancelled = False
            app.ocr_processing = True
        
        def worker():
            image = kwargs.get("image", None)
            rect = kwargs.get("rect", None)
            ui = getattr(app, "ui", None)
            
            # Trim whitespace to focus processing and compute precise text alignment
            x_offset, y_offset, w_offset, h_offset = 0, 0, 0, 0
            if image is not None and image.size > 0:
                image, offset_box = trim_whitespace(image)
                x_offset, y_offset, w_offset, h_offset = offset_box
                
            if rect:
                rect = (rect[0] + x_offset, rect[1] + y_offset, w_offset, h_offset)
                
            def status_callback(stage: str):
                if ui:
                    for s in ["Preparing image...", "Enhancing image...", "Running OCR...", "Extracting text...", "Creating editable objects...", "🤖 Processing OCR..."]:
                        ui.remove_flash_message(s)
                    ui.flash_message(f"🤖 {stage}", duration_sec=float('inf'))
                    
            if ui:
                ui.remove_flash_message("Processing OCR")
                status_callback("Preparing image...")
                
            def check_cancelled() -> bool:
                return app is not None and (
                    getattr(app, "ocr_cancelled", False) or 
                    getattr(app, "ocr_session_id", 0) != session_id
                )
                
            try:
                # Check for cancellation before executing OCR
                if check_cancelled():
                    print("[OCR Plugin] OCR task cancelled before execution.")
                    return
                    
                text, confidence = self.provider.extract_text(image, cancel_check=check_cancelled, status_callback=status_callback)
                
                # Check for cancellation after executing OCR
                if check_cancelled():
                    print("[OCR Plugin] OCR task cancelled after execution.")
                    return

                print(f"[OCR Plugin] Background OCR completed. Extracted: {text} (Conf: {confidence:.1f}%)")
                
                # Clear original selection rectangle in main app
                if app:
                    app.ocr_selected_rect = None
                    
                if ui:
                    for s in ["Preparing image...", "Enhancing image...", "Running OCR...", "Extracting text...", "Creating editable objects...", "🤖 Processing OCR..."]:
                        ui.remove_flash_message(s)
                    
                if text == "Cancelled":
                    if ui:
                        ui.flash_message("OCR Cancelled", duration_sec=2.0)
                    return
                    
                if text and not text.startswith("Pytesseract is not installed") and "Error" not in text and "OCR Error" not in text:
                    if ui:
                        ui.flash_message("✓ OCR Complete", duration_sec=3.0)
                        ui.flash_message(f"Confidence: {int(confidence)}%", duration_sec=3.0)

                    if status_callback:
                        status_callback("Creating editable objects...")

                    # Allow editing the extracted text before inserting it
                    edited_text = self.show_preview_dialog(text)
                    
                    if ui:
                        ui.remove_flash_message("Creating editable objects...")
                    
                    # Check for cancellation after dialog returns
                    if check_cancelled():
                        print("[OCR Plugin] OCR task cancelled after dialog.")
                        return

                    if not edited_text:
                        if ui:
                            ui.flash_message("OCR Cancelled", duration_sec=2.0)
                        return
                        
                    lines = [line.strip() for line in edited_text.split('\n')]
                    start_x = rect[0] if rect else 100
                    start_y = rect[1] + 25 if rect else 100
                    scale = 1.0
                    
                    # Insert each line as an editable text object
                    for i, line in enumerate(lines):
                        if line:
                            params = {"text": line, "x": start_x, "y": start_y + (i * 25 * scale), "scale": scale}
                            self.event_bus.publish(EventType.PLUGIN_ADD_SHAPE, shape_type="text", params=params, color=(255, 255, 255), size=2)
                else:
                    error_msg = text if text else "No text found in selected region"
                    if ui:
                        ui.flash_message("OCR Failed", duration_sec=5.0)
                    self.event_bus.publish(EventType.SHOW_ERROR_DIALOG, "OCR Failed", [error_msg])
            except Exception as e:
                import traceback
                traceback.print_exc()
                error_msg = f"OCR Error: {e}"
                if ui:
                    for s in ["Preparing image...", "Enhancing image...", "Running OCR...", "Extracting text...", "Creating editable objects...", "🤖 Processing OCR..."]:
                        ui.remove_flash_message(s)
                    ui.flash_message("OCR Failed", duration_sec=5.0)
                self.event_bus.publish(EventType.SHOW_ERROR_DIALOG, "OCR Error", [error_msg])
            finally:
                if app:
                    app.ocr_processing = False
                    # Only clear selected rect if this is still the active session
                    if getattr(app, "ocr_session_id", 0) == session_id:
                        app.ocr_selected_rect = None
                
        threading.Thread(target=worker, daemon=True).start()

    def show_preview_dialog(self, initial_text: str) -> Optional[str]:
        import tkinter as tk
        from tkinter import scrolledtext
        
        result = [None]
        root = tk.Tk()
        root.title("OCR Text Preview")
        root.geometry("600x500")
        root.attributes("-topmost", True)
        
        # Style
        root.configure(bg="#2d221e")
        
        lbl = tk.Label(root, text="OCR Extracted Text Preview:", font=("Arial", 11, "bold"), bg="#2d221e", fg="#f0eae8")
        lbl.pack(pady=12)
        
        # Start in Disabled (Read-only) mode
        txt = scrolledtext.ScrolledText(root, width=65, height=18, bg="#1e1412", fg="#f0eae8", insertbackground="white", font=("Courier", 10))
        txt.insert(tk.END, initial_text)
        txt.configure(state=tk.DISABLED)
        txt.pack(padx=15, pady=5)
        
        status_lbl = tk.Label(root, text="Mode: Preview (Click Edit to modify)", font=("Arial", 9, "italic"), bg="#2d221e", fg="#c8b0a0")
        status_lbl.pack(pady=2)
        
        def on_insert():
            state_val = txt.cget("state")
            if state_val == tk.DISABLED:
                txt.configure(state=tk.NORMAL)
            result[0] = txt.get("1.0", tk.END).strip()
            root.destroy()
            
        def on_edit():
            txt.configure(state=tk.NORMAL)
            txt.focus_set()
            status_lbl.configure(text="Mode: Editing", fg="#96c800")
            btn_edit.configure(state=tk.DISABLED, bg="#3e2f28")
            
        def on_cancel():
            root.destroy()
            
        btn_frame = tk.Frame(root, bg="#2d221e")
        btn_frame.pack(pady=15)
        
        btn_ins = tk.Button(btn_frame, text="Insert", command=on_insert, width=12, bg="#96c800", fg="black", font=("Arial", 10, "bold"))
        btn_ins.pack(side=tk.LEFT, padx=10)
        
        btn_edit = tk.Button(btn_frame, text="Edit", command=on_edit, width=12, bg="#5c453c", fg="#f0eae8", font=("Arial", 10, "bold"))
        btn_edit.pack(side=tk.LEFT, padx=10)
        
        btn_can = tk.Button(btn_frame, text="Cancel", command=on_cancel, width=12, bg="#3e2f28", fg="#f0eae8", font=("Arial", 10))
        btn_can.pack(side=tk.LEFT, padx=10)
        
        # Center dialog
        root.update_idletasks()
        w = root.winfo_screenwidth()
        h = root.winfo_screenheight()
        size = tuple(int(_) for _ in root.geometry().split('+')[0].split('x'))
        x = w/2 - size[0]/2
        y = h/2 - size[1]/2
        root.geometry("%dx%d+%d+%d" % (size[0], size[1], x, y))
        
        root.mainloop()
        return result[0]


def register_plugin() -> Plugin:
    from app.services.providers import TesseractOCRProvider
    return OCRPlugin(TesseractOCRProvider())
