"""
Concrete implementations of OCR providers.
"""
from app.services.interfaces import IOCRProvider
import numpy as np
from typing import Optional
import cv2

try:
    import pytesseract
    HAS_TESSERACT = True
except Exception:
    HAS_TESSERACT = False



def deskew(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    gray = cv2.bitwise_not(gray)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    
    # Extract coordinates as (x, y) with int32 type for OpenCV minAreaRect compatibility
    y_idx, x_idx = np.where(thresh > 0)
    if len(x_idx) < 10:
        return image
        
    coords = np.column_stack((x_idx, y_idx)).astype(np.int32)
    angle = cv2.minAreaRect(coords)[-1]
    
    # Normalize rotation angle boundaries
    if angle < -45:
        angle = -(90 + angle)
    elif angle > 45:
        angle = 90 - angle
    else:
        angle = -angle
        
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return rotated

def analyze_image_quality(gray: np.ndarray) -> dict:
    """Analyze image metrics: contrast, noise level, and mean brightness."""
    std_dev = float(np.std(gray))
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    noise_var = float(np.var(laplacian))
    mean_val = float(np.mean(gray))
    return {
        "contrast": std_dev,
        "noise_var": noise_var,
        "mean": mean_val
    }

def preprocess_image_advanced(
    image: np.ndarray,
    enhance_contrast: bool = False,
    denoise: str = "none",
    morphology: str = "none",
    sharpen: bool = False,
    binarize: str = "none"
) -> np.ndarray:
    """Adaptive preprocessing pipeline applying selected operators based on quality analysis."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image.copy()
    
    # 1. Contrast Enhancement
    if enhance_contrast:
        import config
        min_contrast = getattr(config, "OCR_MIN_CONTRAST_THRESHOLD", 45.0)
        std_dev = np.std(gray)
        if std_dev < min_contrast:
            # Low contrast: apply stronger CLAHE
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
        else:
            clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
            
    # 2. Denoising
    if denoise == "gaussian":
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
    elif denoise == "median":
        gray = cv2.medianBlur(gray, 3)
    elif denoise == "bilateral":
        gray = cv2.bilateralFilter(gray, 9, 50, 50)
        
    # 3. Sharpening
    if sharpen:
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        gray = cv2.filter2D(gray, -1, kernel)
        
    # 4. Morphology
    if morphology == "opening":
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        gray = cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel)
    elif morphology == "closing":
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        gray = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
        
    # 5. Binarization
    if binarize == "otsu":
        _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    elif binarize == "adaptive":
        gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    elif binarize == "simple":
        _, gray = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
        
    return gray

def evaluate_text_quality(text: str, confidence: float) -> float:
    if not text or not text.strip():
        return -999.0
    
    # Calculate alphanumeric character count
    clean_chars = [c for c in text if c.isalnum()]
    clean_len = len(clean_chars)
    if clean_len == 0:
        return -500.0
        
    total_len = len(text)
    alnum_ratio = clean_len / total_len
    
    # Check for noisy/suspicious characters commonly generated on margins/background noise
    suspicious_chars = ["|", "~", "^", "\\", "°", "®", "©", "¢", "£", "¤", "¥"]
    suspicious_count = sum(1 for c in text if c in suspicious_chars)
    suspicious_ratio = suspicious_count / total_len
    
    # Combined quality score: starts with OCR confidence
    score = confidence
    score += alnum_ratio * 20.0
    score -= suspicious_ratio * 50.0
    score += min(clean_len, 30) * 1.5
    return score

class TesseractOCRProvider(IOCRProvider):
    _last_successful_pipeline: str = "Baseline"

    def extract_text(self, image: np.ndarray, cancel_check=None, status_callback=None) -> tuple[str, float]:
        if not HAS_TESSERACT:
            return "Pytesseract is not installed (Mock: Extracted Text)", 0.0
            
        import config

        # 1. Explicit Image Format & Channel Validation
        if not isinstance(image, np.ndarray):
            return "Invalid image format (not numpy array)", 0.0
        if len(image.shape) == 2:
            format_str = "Grayscale"
            channels = 1
            bgr_image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        elif len(image.shape) == 3:
            channels = image.shape[2]
            if channels == 3:
                format_str = "BGR"
                bgr_image = image.copy()
            elif channels == 4:
                format_str = "BGRA"
                bgr_image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
            else:
                return f"Unsupported number of channels: {channels}", 0.0
        else:
            return "Invalid image shape", 0.0

        # 2. Input Image Check (Verify it contains drawings/text and is not blank/incorrectly cropped)
        h_orig, w_orig = bgr_image.shape[:2]
        if w_orig < 4 or h_orig < 4:
            return "Selected region is too small", 0.0
            
        gray_orig = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
        std_dev_orig = np.std(gray_orig)
        mean_orig = np.mean(gray_orig)
        
        # Verify contrast
        if std_dev_orig < 2.0:
            return "Selected region has no text or contrast", 0.0
            
        # Verify non-background pixels count
        if mean_orig > 127:
            _, thresh_orig = cv2.threshold(gray_orig, 200, 255, cv2.THRESH_BINARY_INV)
        else:
            _, thresh_orig = cv2.threshold(gray_orig, 30, 255, cv2.THRESH_BINARY)
            
        fg_pixels_orig = np.sum(thresh_orig > 0)
        if fg_pixels_orig < 5:
            return "Selected region is empty", 0.0

        # 3. Dynamic Proper DPI Scaling (Upscale small text crops)
        scale_factor = 1.0
        bgr_scaled = bgr_image.copy()
        if h_orig < 100 or w_orig < 150:
            scale_factor = max(2.0, 150.0 / w_orig, 100.0 / h_orig)
            new_w = int(w_orig * scale_factor)
            new_h = int(h_orig * scale_factor)
            bgr_scaled = cv2.resize(bgr_image, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
            
        h_up, w_up = bgr_scaled.shape[:2]

        try:
            if cancel_check and cancel_check():
                return "Cancelled", 0.0

            if status_callback:
                status_callback("Preparing image...")

            # 4. Check for Skew Correction
            apply_deskew = False
            deskewed_img = None
            if getattr(config, "OCR_ENABLE_DESKEW", True):
                gray_scaled = cv2.cvtColor(bgr_scaled, cv2.COLOR_BGR2GRAY)
                mean_scaled = np.mean(gray_scaled)
                gray_inv = cv2.bitwise_not(gray_scaled) if mean_scaled > 127 else gray_scaled.copy()
                _, skew_thresh = cv2.threshold(gray_inv, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
                y_idx, x_idx = np.where(skew_thresh > 0)
                if len(x_idx) >= 10:
                    coords = np.column_stack((x_idx, y_idx)).astype(np.int32)
                    angle = cv2.minAreaRect(coords)[-1]
                    if angle < -45:
                        angle = -(90 + angle)
                    elif angle > 45:
                        angle = 90 - angle
                    else:
                        angle = -angle
                        
                    if 1.5 < abs(angle) < 43.5:
                        apply_deskew = True
                        center = (w_up // 2, h_up // 2)
                        M = cv2.getRotationMatrix2D(center, angle, 1.0)
                        deskewed_img = cv2.warpAffine(bgr_scaled, M, (w_up, h_up), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

            if cancel_check and cancel_check():
                return "Cancelled", 0.0

            if status_callback:
                status_callback("Enhancing image...")

            # 5. Preprocessing Pipelines Cache/Generator
            generated_images = {}

            def get_preprocessed_image(name: str) -> Optional[np.ndarray]:
                if name in generated_images:
                    return generated_images[name]
                    
                enable_grayscale = getattr(config, "OCR_ENABLE_GRAYSCALE", True)
                enable_otsu = getattr(config, "OCR_ENABLE_OTSU", True)
                enable_adaptive = getattr(config, "OCR_ENABLE_ADAPTIVE", True)
                enable_clahe = getattr(config, "OCR_ENABLE_CLAHE", True)
                enable_deskew = getattr(config, "OCR_ENABLE_DESKEW", True)

                # Determine raw source image (deskewed or normal)
                src = deskewed_img if (name.startswith("Deskewed") and enable_deskew and deskewed_img is not None) else bgr_scaled
                
                # Check base name
                base_name = name.replace("Deskewed ", "")
                
                if base_name == "Baseline":
                    res = cv2.cvtColor(src, cv2.COLOR_BGR2RGB)
                else:
                    g_img = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
                    m_val = np.mean(g_img)
                    g_for_t = cv2.bitwise_not(g_img) if m_val < 127 else g_img.copy()
                    
                    if base_name == "Grayscale" and enable_grayscale:
                        res = g_img
                    elif base_name == "Otsu" and enable_otsu:
                        _, res = cv2.threshold(g_for_t, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
                    elif base_name == "Adaptive" and enable_adaptive:
                        res = cv2.adaptiveThreshold(g_for_t, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
                    elif base_name == "CLAHE" and enable_clahe:
                        clahe_obj = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                        clahe_gray = clahe_obj.apply(g_for_t)
                        _, res = cv2.threshold(clahe_gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
                    else:
                        res = None
                
                if res is not None:
                    generated_images[name] = res
                return res

            # Determine PSMs (Page Segmentation Modes)
            aspect = w_up / max(1, h_up)
            if h_up < 55 or aspect > 4.5:
                psm_candidates = [7]  # Single line
            else:
                psm_candidates = [3]  # Fully automatic page segmentation

            # Build ordered list of preprocessing pipelines to evaluate
            default_list = ["Baseline", "Grayscale", "Otsu"]
            fallback_list = ["CLAHE", "Adaptive"]
            if apply_deskew:
                fallback_list.extend(["Deskewed Baseline", "Deskewed Grayscale", "Deskewed Otsu"])
                
            pipelines_to_run = []
            
            # Baseline is always the absolute priority
            if getattr(config, "OCR_ENABLE_BASELINE", True):
                pipelines_to_run.append("Baseline")
                
            # Cached success pipeline next (prioritize last successful)
            cached = TesseractOCRProvider._last_successful_pipeline
            if cached and cached not in pipelines_to_run:
                # Make sure the cached pipeline is still enabled
                if cached in default_list or cached in fallback_list:
                    pipelines_to_run.append(cached)
                    
            # Add remaining default pipelines
            for p in default_list:
                if p not in pipelines_to_run:
                    pipelines_to_run.append(p)
                    
            # Add fallbacks
            for p in fallback_list:
                if p not in pipelines_to_run:
                    pipelines_to_run.append(p)

            # 6. Diagnostic Logging
            debug_enabled = getattr(config, "OCR_DEBUG", False)
            conf_threshold = getattr(config, "OCR_CONFIDENCE_THRESHOLD", 60.0)

            if debug_enabled:
                print("=" * 60)
                print("[OCR Diagnostic Log]")
                print(f"  Selected region size: {w_orig}x{h_orig}")
                print(f"  Image format: {format_str} | Channels: {channels}")
                print(f"  Image statistics - StdDev (contrast): {std_dev_orig:.2f} | Mean brightness: {mean_orig:.2f}")
                print(f"  DPI Scale factor: {scale_factor:.2f} (Upscaled size: {w_up}x{h_up})")
                print(f"  Foreground pixels: {fg_pixels_orig}")
                print(f"  Cached last successful pipeline: {TesseractOCRProvider._last_successful_pipeline}")
                print(f"  Pipelines scheduled: {pipelines_to_run}")
                print(f"  PSM candidates: {psm_candidates}")
                print("-" * 60)

            best_text = ""
            best_conf = 0.0
            best_score = -999.0
            best_pipe = "None"
            best_psm = -1

            if status_callback:
                status_callback("Running OCR...")

            # Run preprocessors and evaluate text quality
            for pipe_name in pipelines_to_run:
                # Early exit if we have found a result that satisfies our confidence threshold
                if best_score >= conf_threshold:
                    if debug_enabled:
                        print(f"[OCR Debug] Early exit triggered. Best score {best_score:.2f} >= threshold {conf_threshold:.2f}")
                    break
                    
                # Skip fallback pipelines if we already have a decent candidate (confidence >= 50)
                is_fallback = (pipe_name in fallback_list and "Deskewed" not in pipe_name) or "Deskewed" in pipe_name
                if is_fallback and best_score >= 50.0:
                    if debug_enabled:
                        print(f"[OCR Debug] Skipping fallback {pipe_name} since current score {best_score:.2f} is acceptable.")
                    continue

                proc = get_preprocessed_image(pipe_name)
                if proc is None:
                    continue

                for psm in psm_candidates:
                    if cancel_check and cancel_check():
                        return "Cancelled", 0.0
                        
                    config_str = f"-l eng --oem 3 --psm {psm} --dpi 300"
                    
                    try:
                        data = pytesseract.image_to_data(proc, config=config_str, output_type=pytesseract.Output.DICT)
                        confidences = [int(c) for c in data['conf'] if str(c).strip() != '-1']
                        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
                        
                        text = pytesseract.image_to_string(proc, config=config_str).strip()
                        score = evaluate_text_quality(text, avg_conf)
                        
                        if debug_enabled:
                            print(f"[OCR Debug] Run - Pipeline: {pipe_name} | PSM: {psm} | AvgConf: {avg_conf:.1f}% | Score: {score:.2f} | Output: {repr(text)}")
                            
                        if score > best_score:
                            best_score = score
                            best_text = text
                            best_conf = avg_conf
                            best_pipe = pipe_name
                            best_psm = psm
                            
                    except Exception as loop_e:
                        if debug_enabled:
                            print(f"[OCR Debug] Exception on {pipe_name} (PSM {psm}): {loop_e}")
                        continue

            if status_callback:
                status_callback("Extracting text...")

            # Cache the successful pipeline if it meets the confidence threshold
            if best_score >= conf_threshold and best_pipe != "None":
                TesseractOCRProvider._last_successful_pipeline = best_pipe
                if debug_enabled:
                    print(f"[OCR Debug] Updating last successful pipeline cache to: {best_pipe}")

            if debug_enabled:
                print("-" * 60)
                print("[OCR Result Summary]")
                print(f"  Best Pipeline: {best_pipe} | PSM: {best_psm}")
                print(f"  Avg Confidence: {best_conf:.1f}% | Quality Score: {best_score:.2f}")
                print(f"  Extracted Text: {repr(best_text)}")
                print("=" * 60)

            if best_score == -999.0:
                best_text = ""
                best_conf = 0.0

            return best_text, float(best_conf)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"OCR Error: {e}", 0.0





