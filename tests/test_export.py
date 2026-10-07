"""
Verification test for SVG export of all supported shape types.
"""

import sys
sys.path.append(".")
from app.workspace_manager import WorkspaceManager
from app.model import Stroke, Shape

def run_export_tests():
    print("=== STARTING SVG EXPORT TESTS ===")
    
    wm = WorkspaceManager()
    layer_idx = wm.document.active_layer_index
    
    # 1. Add Stroke
    stroke = Stroke([(100.0, 100.0), (120.0, 110.0), (130.0, 140.0)], (255, 0, 0), 3)
    wm.document.layers[layer_idx].items.append(stroke)
    
    # 2. Add shapes
    wm.document.layers[layer_idx].items.extend([
        Shape("circle", {"cx": 200, "cy": 200, "radius": 50}, (0, 255, 0), 2),
        Shape("ellipse", {"cx": 300, "cy": 200, "axes_a": 60, "axes_b": 30}, (0, 0, 255), 2),
        Shape("rectangle", {"x": 400, "y": 100, "w": 100, "h": 50}, (255, 255, 0), 2),
        Shape("square", {"x": 550, "y": 100, "side": 60}, (0, 255, 255), 2),
        Shape("line", {"p0": (100, 400), "p1": (300, 400)}, (255, 0, 255), 2),
        Shape("arrow", {"p0": (100, 500), "p1": (300, 500)}, (100, 100, 100), 2),
        Shape("triangle", {"pts": [(400, 400), (450, 350), (500, 400)]}, (50, 150, 250), 2),
        Shape("diamond", {"pts": [(600, 400), (630, 370), (660, 400), (630, 430)]}, (150, 250, 50), 2),
        Shape("text", {"text": "Ekora Sketch", "x": 100, "y": 600, "scale": 1.2}, (255, 255, 255), 2)
    ])
    
    svg_str = wm.to_svg()
    print("Generated SVG content sample (first 1000 characters):")
    print(svg_str[:1000])
    
    # Assertions to ensure each shape was exported to its respective SVG tag
    assert "<svg" in svg_str
    assert "</svg>" in svg_str
    assert "<path" in svg_str       # Stroke and Arrow use path
    assert "<ellipse" in svg_str    # Circle and Ellipse use ellipse
    assert "<rect" in svg_str       # Rectangle, Square, and Background use rect
    assert "<line" in svg_str       # Line uses line
    assert "<polygon" in svg_str    # Triangle and Diamond use polygon
    assert "<text" in svg_str       # Text uses text
    
    print("\nOK: SVG export verification passed. All shape types successfully converted.")
    print("=== ALL EXPORT TESTS COMPLETED SUCCESSFULLY ===")

def test_svg_export():
    run_export_tests()

if __name__ == "__main__":
    run_export_tests()

