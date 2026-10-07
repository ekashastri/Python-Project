"""
Performance validation script for gesture recognition, cursor tracking, and stabilization.
"""

import time
import math
import tracemalloc
import sys
from typing import List, Tuple

sys.path.append(".")
from app.hand_tracker import HandLandmarks
from app.cursor_tracker import CursorTracker
from app.virtual_pen import VirtualPen
from app.gesture_detector import GestureDetector, Gesture

def generate_mock_landmarks(state: str, frame_idx: int) -> HandLandmarks:
    # 21 landmarks
    lms = []
    # Wrist
    lms.append((640, 360))
    
    # Generate points based on state
    if state == "POINT":
        # Index extended, others curled
        # Thumb
        lms.extend([(600, 340), (590, 330), (580, 320), (570, 310)])
        # Index (extended, moving in a circle)
        angle = frame_idx * 0.05
        cx = 640 + 200 * math.cos(angle)
        cy = 360 + 200 * math.sin(angle)
        lms.extend([(cx, cy - 60), (cx, cy - 40), (cx, cy - 20), (cx, cy)])
        # Middle (curled)
        lms.extend([(630, 380), (620, 390), (610, 400), (600, 410)])
        # Ring (curled)
        lms.extend([(650, 380), (650, 395), (650, 410), (650, 420)])
        # Pinky (curled)
        lms.extend([(670, 380), (670, 390), (670, 400), (670, 410)])
        
    elif state == "FIST":
        # All fingers curled
        lms.extend([(600, 340), (590, 330), (580, 320), (570, 310)]) # thumb
        lms.extend([(620, 380), (620, 390), (620, 400), (620, 410)]) # index
        lms.extend([(630, 380), (630, 390), (630, 400), (630, 410)]) # middle
        lms.extend([(640, 380), (640, 390), (640, 400), (640, 410)]) # ring
        lms.extend([(650, 380), (650, 390), (650, 400), (650, 410)]) # pinky
        
    elif state == "PINCH":
        # Thumb and index tips touching
        lms.extend([(600, 340), (590, 330), (580, 320), (570, 310)]) # thumb tip at 570, 310
        lms.extend([(620, 340), (610, 330), (590, 320), (570, 310)]) # index tip touching thumb tip
        lms.extend([(630, 380), (620, 390), (610, 400), (600, 410)])
        lms.extend([(650, 380), (650, 395), (650, 410), (650, 420)])
        lms.extend([(670, 380), (670, 390), (670, 400), (670, 410)])
        
    elif state == "PALM":
        # All fingers extended
        lms.extend([(580, 300), (560, 270), (540, 240), (520, 210)]) # thumb
        lms.extend([(610, 290), (600, 250), (590, 210), (580, 170)]) # index
        lms.extend([(640, 280), (640, 230), (640, 180), (640, 130)]) # middle
        lms.extend([(670, 290), (680, 250), (690, 210), (700, 170)]) # ring
        lms.extend([(700, 300), (720, 270), (740, 240), (760, 210)]) # pinky
        
    else: # NONE
        lms.extend([(640, 360)] * 20)
        
    return HandLandmarks(lms, "Right")

def run_performance_test():
    print("=== STARTING GESTURE & TRACKING PERFORMANCE VALIDATION ===")
    
    tracemalloc.start()
    initial_memory = tracemalloc.get_traced_memory()[0]
    
    cursor_tracker = CursorTracker()
    pen = VirtualPen()
    detector = GestureDetector()
    
    total_frames = 1000
    latencies = []
    
    # 1. Warm-up
    for i in range(50):
        hand = generate_mock_landmarks("POINT", i)
        raw_pos, tracker_pos, vel = cursor_tracker.update(hand)
        if raw_pos:
            pen.process(raw_pos)
        detector.detect(hand, (720, 1280))
        
    # 2. Main Simulation loop (1000 frames)
    # Simulate states: DRAW -> LOST -> RECOVERY -> PINCH -> FIST -> PALM -> IDLE
    simulation_states = (
        ["POINT"] * 250 +
        ["NONE"] * 100 +      # Lost tracking
        ["POINT"] * 150 +     # Recover tracking
        ["PINCH"] * 150 +     # Pinch/drag
        ["FIST"] * 150 +      # Pause
        ["PALM"] * 100 +      # Palm clear
        ["NONE"] * 100        # Idle/lost
    )
    
    start_time = time.perf_counter()
    
    for idx, state in enumerate(simulation_states):
        hand = generate_mock_landmarks(state, idx) if state != "NONE" else None
        
        # Measure step processing time
        step_start = time.perf_counter()
        
        # Cursor tracking
        raw_pos, tracker_pos, velocity = cursor_tracker.update(hand)
        
        # Pen stabilization
        if raw_pos is not None:
            pen_pos = pen.process(raw_pos)
        else:
            pen.reset()
            pen_pos = tracker_pos
            
        # Gesture detection
        if hand is not None:
            gesture, conf, f_states = detector.detect(hand, (720, 1280))
        else:
            gesture = Gesture.NONE
            
        step_end = time.perf_counter()
        latencies.append((step_end - step_start) * 1000.0) # in ms
        
    end_time = time.perf_counter()
    total_elapsed = end_time - start_time
    
    final_memory = tracemalloc.get_traced_memory()[0]
    peak_memory = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    
    avg_latency_ms = sum(latencies) / len(latencies)
    max_latency_ms = max(latencies)
    throughput_fps = len(latencies) / total_elapsed
    
    print("\n--- Performance Results ---")
    print(f"Total simulated frames : {total_frames}")
    print(f"Total execution time   : {total_elapsed:.4f} seconds")
    print(f"Average frame latency  : {avg_latency_ms:.4f} ms")
    print(f"Max single-frame time  : {max_latency_ms:.4f} ms")
    print(f"Throughput (Max FPS)   : {throughput_fps:.1f} frames/sec")
    print(f"Initial Memory usage   : {initial_memory / 1024.0:.2f} KB")
    print(f"Final Memory usage     : {final_memory / 1024.0:.2f} KB")
    print(f"Peak Memory usage      : {peak_memory / 1024.0:.2f} KB")
    print(f"Memory Leak check      : Passed (Delta: {(final_memory - initial_memory)/1024.0:.2f} KB)")
    
    # Assertions for validation
    assert avg_latency_ms < 2.0, f"Average latency is too high: {avg_latency_ms:.2f} ms"
    assert throughput_fps >= 300, f"Throughput is too low: {throughput_fps:.1f} FPS"
    assert (final_memory - initial_memory) < 50 * 1024, "Potential memory leak detected (> 50 KB delta)"
    
    print("\n=== PERFORMANCE VALIDATION PASSED SUCCESSFULLY ===")

def test_gesture_performance():
    run_performance_test()

if __name__ == "__main__":
    run_performance_test()

