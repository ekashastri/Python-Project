"""
Verification test for Phase 5 OCR Preprocessing, Region Trimming, and OCR extraction.
"""

import sys
import numpy as np
import cv2

sys.path.append(".")
from plugins.ocr_plugin import trim_whitespace
from app.services.providers import TesseractOCRProvider, analyze_image_quality

def run_ocr_tests():
    print("=== STARTING OCR PREPROCESSING & DYNAMIC CONFIGURATION TESTS ===")
    
    # 1. Verify Trim Whitespace on dark background
    print("\n--- Test 1: Trim Whitespace (Dark Background) ---")
    img_dark = np.zeros((100, 200, 3), dtype=np.uint8)
    # Draw a white rectangle in the center (simulating a word/stroke)
    cv2.rectangle(img_dark, (40, 30), (160, 70), (255, 255, 255), -1)
    
    trimmed, (x, y, w, h) = trim_whitespace(img_dark)
    print(f"Original shape: {img_dark.shape}")
    print(f"Trimmed shape: {trimmed.shape}")
    print(f"Bounding box: x={x}, y={y}, w={w}, h={h}")
    
    # Expect bounding box to crop around the central rectangle (plus safety padding)
    # 40 - padding (6) = 34, 30 - padding (6) = 24, etc.
    assert x > 0 and y > 0
    assert w < 200 and h < 100
    print("OK: Trim Whitespace (Dark Background) passed.")

    # 2. Verify Trim Whitespace on light background
    print("\n--- Test 2: Trim Whitespace (Light Background) ---")
    img_light = np.ones((100, 200, 3), dtype=np.uint8) * 255
    # Draw a dark rectangle in the center (simulating printed text)
    cv2.rectangle(img_light, (50, 40), (150, 60), (0, 0, 0), -1)
    
    trimmed_l, (xl, yl, wl, hl) = trim_whitespace(img_light)
    print(f"Original shape: {img_light.shape}")
    print(f"Trimmed shape: {trimmed_l.shape}")
    print(f"Bounding box: x={xl}, y={yl}, w={wl}, h={hl}")
    assert xl > 0 and yl > 0
    assert wl < 200 and hl < 100
    print("OK: Trim Whitespace (Light Background) passed.")

    # 3. Quality Analysis
    print("\n--- Test 3: Quality Analysis ---")
    gray_img = cv2.cvtColor(img_dark, cv2.COLOR_BGR2GRAY)
    quality = analyze_image_quality(gray_img)
    print(f"Image quality metrics: {quality}")
    assert "contrast" in quality
    assert "noise_var" in quality
    assert "mean" in quality
    print("OK: Quality Analysis passed.")

    # 4. OCR Extraction execution
    print("\n--- Test 4: OCR Extraction Pipeline ---")
    provider = TesseractOCRProvider()
    
    stages_reported = []
    def mock_status_callback(stage):
        stages_reported.append(stage)
        print(f"  [Callback Status]: {stage}")
        
    text, confidence = provider.extract_text(img_dark, status_callback=mock_status_callback)
    print(f"Extracted: '{text}' (Confidence: {confidence:.2f}%)")
    print(f"Reported stages: {stages_reported}")
    
    # Verify stages were correctly reported
    assert len(stages_reported) > 0
    assert "Preparing image..." in stages_reported
    assert "Enhancing image..." in stages_reported
    assert "Running OCR..." in stages_reported
    assert "Extracting text..." in stages_reported
    
    print("OK: OCR Extraction Pipeline passed.")
    print("\n=== ALL OCR TESTS COMPLETED SUCCESSFULLY ===")

def test_ocr_pipeline():
    run_ocr_tests()

if __name__ == "__main__":
    run_ocr_tests()

