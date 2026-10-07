"""
Workspace Manager orchestrates the Document, Viewport, and Command history.
"""
from typing import Tuple, Optional, List
import math
import numpy as np

from app.model import Document, Stroke, Shape, Layer, Viewport
from app.commands import CommandManager, AddItemCommand, RemoveItemCommand, ModifyShapeCommand, ClearDocumentCommand
import config
from app.drawing_engine import DrawingEngine
import cv2


class WorkspaceManager:
    """Central repository for the drawing state, managing history and viewport."""
    def __init__(self):
        self.document = Document()
        self.commands = CommandManager(self.document)
        self.viewport = Viewport()
        self.engine = DrawingEngine(config.CAMERA_WIDTH, config.CAMERA_HEIGHT)
        self.is_dirty = True
        
        # Tool state
        self.brush_color = config.DEFAULT_BRUSH_COLOR
        self.brush_size = config.DEFAULT_BRUSH_SIZE
        self.eraser_size = config.ERASER_SIZE
        
        # Stroke drawing state
        self._current_stroke: Optional[Stroke] = None
        
        # Interaction state
        self.hovered_item: Optional[Shape] = None
        self.active_item: Optional[Shape] = None
        self.selected_item: Optional[Shape] = None
        self.interaction_mode: Optional[str] = None
        self.interaction_start_pt: Optional[Tuple[float, float]] = None
        self.interaction_initial_params: Optional[dict] = None
        
        # Panning state
        self._pan_prev_point: Optional[Tuple[float, float]] = None
        
    def delete_selected_item(self) -> bool:
        if self.selected_item is not None:
            self.commands.execute(RemoveItemCommand(self.selected_item, self.document.active_layer_index))
            if self.active_item == self.selected_item:
                self.active_item = None
            if self.hovered_item == self.selected_item:
                self.hovered_item = None
            self.selected_item = None
            self.is_dirty = True
            return True
        return False
        
    # ------------------------------------------------------------------
    # Strokes
    # ------------------------------------------------------------------
    def start_stroke(self, point: Tuple[int, int]) -> None:
        self.is_dirty = True
        doc_pt = self.viewport.screen_to_doc(point)
        self._current_raw_points = [doc_pt]
        self._current_stroke = Stroke([doc_pt], self.brush_color, self.brush_size, is_eraser=False)
        
    def pause_stroke(self) -> None:
        if self._current_stroke and self._current_raw_points:
            if self._current_raw_points[-1] is not None:
                self._current_raw_points.append(None)

    def continue_stroke(self, point: Tuple[int, int], eraser: bool = False) -> None:
        if not self._current_stroke:
            self.start_stroke(point)
            self._current_stroke.is_eraser = eraser
            return
            
        doc_pt = self.viewport.screen_to_doc(point)
        
        # Avoid extremely dense raw points
        last_raw = self._current_raw_points[-1]
        if last_raw is None:
            self._current_raw_points.append(doc_pt)
        else:
            dist_raw = math.hypot(doc_pt[0] - last_raw[0], doc_pt[1] - last_raw[1])
            if dist_raw < 2.0 / self.viewport.zoom:
                return
            self._current_raw_points.append(doc_pt)
            
        # Split raw into segments by None
        raw_segments = []
        curr_seg = []
        for pt in self._current_raw_points:
            if pt is None:
                if curr_seg:
                    raw_segments.append(curr_seg)
                    curr_seg = []
            else:
                curr_seg.append(pt)
        if curr_seg:
            raw_segments.append(curr_seg)
            
        interpolated_segments = []
        for raw in raw_segments:
            interpolated = []
            if len(raw) < 2:
                interpolated = list(raw)
            else:
                for i in range(len(raw) - 1):
                    p1 = raw[i]
                    p2 = raw[i+1]
                    p0 = raw[i-1] if i > 0 else p1
                    p3 = raw[i+2] if i < len(raw) - 2 else (p2[0] + (p2[0]-p1[0]), p2[1] + (p2[1]-p1[1]))
                    
                    if i == 0:
                        interpolated.append(p1)
                        
                    dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                    max_gap = getattr(config, "STROKE_MAX_GAP_PX", 6) / self.viewport.zoom
                    steps = max(2, int(dist / max_gap) + 1)
                    
                    for step in range(1, steps + 1):
                        t = step / steps
                        t2 = t * t
                        t3 = t2 * t
                        x = 0.5 * (
                            (2 * p1[0]) + (-p0[0] + p2[0]) * t +
                            (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                            (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
                        )
                        y = 0.5 * (
                            (2 * p1[1]) + (-p0[1] + p2[1]) * t +
                            (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                            (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
                        )
                        interpolated.append((x, y))
            interpolated_segments.append(interpolated)
            
        # Reconstruct flat points with None delimiters
        flat_interpolated = []
        for idx, seg in enumerate(interpolated_segments):
            if idx > 0:
                flat_interpolated.append(None)
            flat_interpolated.extend(seg)
            
        self._current_stroke.points = flat_interpolated
        self.is_dirty = True
        
    def end_stroke(self) -> Optional[str]:
        if not self._current_stroke:
            return None
            
        if len(self._current_stroke.points) > 1:
            self._prune_stroke_spikes()
            if len(self._current_stroke.points) > 1:
                self.commands.execute(AddItemCommand(self._current_stroke, self.document.active_layer_index))
            
        self._current_stroke = None
        self.is_dirty = True
        return None

    def _prune_stroke_spikes(self) -> None:
        """
        Prunes leading and trailing hooks/spikes from freehand strokes conservatively.
        Only filters when both the angle threshold and maximum spike length threshold are exceeded.
        """
        if not self._current_stroke or not self._current_stroke.points:
            return
            
        # Split into segments by None
        segments = []
        curr_seg = []
        for pt in self._current_stroke.points:
            if pt is None:
                if curr_seg:
                    segments.append(curr_seg)
                    curr_seg = []
            else:
                curr_seg.append(pt)
        if curr_seg:
            segments.append(curr_seg)
            
        if not segments:
            return
            
        min_pts = getattr(config, "STROKE_SPIKE_MIN_LENGTH", 5)
        max_len = getattr(config, "STROKE_SPIKE_MAX_LENGTH", 15.0)
        max_angle_deg = getattr(config, "STROKE_SPIKE_MAX_ANGLE", 80.0)
        cos_thresh = math.cos(math.radians(max_angle_deg))
        
        # Prune trailing hook from the last segment
        last_seg = segments[-1]
        if len(last_seg) >= min_pts:
            p0 = np.array(last_seg[-3])
            p1 = np.array(last_seg[-2])
            p2 = np.array(last_seg[-1])
            
            v1 = p1 - p0
            v2 = p2 - p1
            len1 = np.linalg.norm(v1)
            len2 = np.linalg.norm(v2)
            
            if len1 > 1e-5 and len2 > 1e-5:
                seg2_pixel_len = len2 * self.viewport.zoom
                if seg2_pixel_len <= max_len:
                    cos_val = np.dot(v1, v2) / (len1 * len2)
                    if cos_val < cos_thresh:
                        segments[-1] = last_seg[:-1]
                        
        # Prune leading hook from the first segment
        first_seg = segments[0]
        if len(first_seg) >= min_pts:
            p0 = np.array(first_seg[0])
            p1 = np.array(first_seg[1])
            p2 = np.array(first_seg[2])
            
            v1 = p1 - p0
            v2 = p2 - p1
            len1 = np.linalg.norm(v1)
            len2 = np.linalg.norm(v2)
            
            if len1 > 1e-5 and len2 > 1e-5:
                seg1_pixel_len = len1 * self.viewport.zoom
                if seg1_pixel_len <= max_len:
                    cos_val = np.dot(v1, v2) / (len1 * len2)
                    if cos_val < cos_thresh:
                        segments[0] = first_seg[1:]
                        
        # Reconstruct flat points with None delimiters
        flat_pts = []
        for idx, seg in enumerate(segments):
            if idx > 0:
                flat_pts.append(None)
            flat_pts.extend(seg)
            
        self._current_stroke.points = flat_pts

    def _convert_params_to_doc(self, shape_type: str, params: dict) -> None:
        if shape_type in ("circle", "ellipse"):
            cx, cy = self.viewport.screen_to_doc((params["cx"], params["cy"]))
            params["cx"], params["cy"] = cx, cy
            params["radius"] = params.get("radius", 0) / self.viewport.zoom
            params["axes_a"] = params.get("axes_a", 0) / self.viewport.zoom
            params["axes_b"] = params.get("axes_b", 0) / self.viewport.zoom
        elif shape_type in ("rectangle", "square"):
            x, y = self.viewport.screen_to_doc((params["x"], params["y"]))
            params["x"], params["y"] = x, y
            params["w"] = params.get("w", 0) / self.viewport.zoom
            params["h"] = params.get("h", 0) / self.viewport.zoom
            params["side"] = params.get("side", 0) / self.viewport.zoom
        elif shape_type in ("triangle", "diamond", "pentagon", "hexagon", "star"):
            params["pts"] = [self.viewport.screen_to_doc(pt) for pt in params["pts"]]
        elif shape_type in ("line", "arrow"):
            params["p0"] = self.viewport.screen_to_doc(params["p0"])
            params["p1"] = self.viewport.screen_to_doc(params["p1"])
        elif shape_type == "text":
            x, y = self.viewport.screen_to_doc((params["x"], params["y"]))
            params["x"], params["y"] = x, y
            params["scale"] = params.get("scale", 1.0) / self.viewport.zoom

    # ------------------------------------------------------------------
    # Panning
    # ------------------------------------------------------------------
    def start_pan(self, point: Tuple[int, int]) -> None:
        self._pan_prev_point = point
        
    def continue_pan(self, point: Tuple[int, int]) -> None:
        if not self._pan_prev_point:
            self._pan_prev_point = point
            return
        dx = point[0] - self._pan_prev_point[0]
        dy = point[1] - self._pan_prev_point[1]
        self.viewport.pan_x += dx
        self.viewport.pan_y += dy
        self._pan_prev_point = point
        self.is_dirty = True
        
    def end_pan(self) -> None:
        self._pan_prev_point = None

    # ------------------------------------------------------------------
    # Object Interaction
    # ------------------------------------------------------------------
    def hit_test(self, point: Tuple[int, int]) -> Tuple[Optional[Shape], Optional[str]]:
        doc_pt = self.viewport.screen_to_doc(point)
        px, py = doc_pt
        hit_zone = 20 / self.viewport.zoom
        
        # Search backwards (top to bottom)
        for layer in reversed(self.document.layers):
            if not layer.visible or layer.locked: continue
            for item in reversed(layer.items):
                x1, y1, x2, y2 = 0, 0, 0, 0
                is_valid = False

                if isinstance(item, Stroke):
                    if not item.points: continue
                    pts = np.array([p for p in item.points if p is not None])
                    x1, y1 = pts[:, 0].min(), pts[:, 1].min()
                    x2, y2 = pts[:, 0].max(), pts[:, 1].max()
                    is_valid = True
                    
                elif isinstance(item, Shape):
                    shape_type = item.shape_type
                    params = item.params
                    is_valid = True
                    
                    if shape_type == "circle":
                        r = params["radius"]
                        cx, cy = params["cx"], params["cy"]
                        x1, y1, x2, y2 = cx - r, cy - r, cx + r, cy + r
                    elif shape_type == "ellipse":
                        r = max(params["axes_a"]/2, params["axes_b"]/2)
                        cx, cy = params["cx"], params["cy"]
                        x1, y1, x2, y2 = cx - r, cy - r, cx + r, cy + r
                    elif shape_type in ("rectangle", "square"):
                        x1, y1 = params["x"], params["y"]
                        w = params.get("w", params.get("side", 0))
                        h = params.get("h", params.get("side", 0))
                        x2, y2 = x1 + w, y1 + h
                    elif shape_type == "triangle":
                        pts = np.array(params["pts"])
                        x1, y1 = pts[:, 0].min(), pts[:, 1].min()
                        x2, y2 = pts[:, 0].max(), pts[:, 1].max()
                    elif shape_type in ("line", "arrow"):
                        p0, p1 = params["p0"], params["p1"]
                        x1, y1 = min(p0[0], p1[0]), min(p0[1], p1[1])
                        x2, y2 = max(p0[0], p1[0]), max(p0[1], p1[1])
                    elif shape_type == "text":
                        scale = params.get("scale", 1.0)
                        text_len = len(params.get("text", ""))
                        x1, y1 = params["x"], params["y"] - 20 * scale
                        x2, y2 = params["x"] + text_len * 15 * scale, params["y"] + 5 * scale

                if is_valid:
                    # If this is the currently selected item, hit-test its control handles first
                    if getattr(self, "selected_item", None) == item:
                        # Delete button is positioned slightly top-right of the bounding box
                        del_x, del_y = x2 + 20/self.viewport.zoom, y1 - 20/self.viewport.zoom
                        if math.hypot(px - del_x, py - del_y) <= hit_zone * 1.5:
                            return item, "delete"
                            
                        corners = [
                            (x1, y1, "resize_tl"), (x2, y1, "resize_tr"),
                            (x1, y2, "resize_bl"), (x2, y2, "resize_br")
                        ]
                        for cx, cy, c_type in corners:
                            if math.hypot(px - cx, py - cy) <= hit_zone:
                                return item, c_type

                    # Then hit-test the body for moving/selecting
                    if (x1 - hit_zone <= px <= x2 + hit_zone) and (y1 - hit_zone <= py <= y2 + hit_zone):
                        return item, "move"
                    
        return None, None

    def update_hover(self, point: Optional[Tuple[int, int]]) -> None:
        if point is None:
            if self.hovered_item is not None:
                self.hovered_item = None
                self.is_dirty = True
            return
            
        if self.active_item is not None:
            return
            
        hit_item, hit_type = self.hit_test(point)
        if hit_item != self.hovered_item:
            self.hovered_item = hit_item
            self.is_dirty = True

    def start_interaction(self, point: Tuple[int, int]) -> None:
        hit_item, hit_type = self.hit_test(point)
        if hit_item is not None:
            self.active_item = hit_item
            self.interaction_mode = hit_type
            self.interaction_start_pt = self.viewport.screen_to_doc(point)
            import copy
            if isinstance(hit_item, Shape):
                self.interaction_initial_params = copy.deepcopy(hit_item.params)
            else:
                self.interaction_initial_params = {"points": copy.deepcopy(hit_item.points)}
            
    def continue_interaction(self, point: Tuple[int, int]) -> None:
        if not self.active_item or not self.interaction_start_pt or not self.interaction_initial_params:
            return
            
        doc_pt = self.viewport.screen_to_doc(point)
        dx = doc_pt[0] - self.interaction_start_pt[0]
        dy = doc_pt[1] - self.interaction_start_pt[1]
        
        if isinstance(self.active_item, Stroke):
            orig_points = self.interaction_initial_params["points"]
            if self.interaction_mode == "move":
                self.active_item.points = [(pt[0] + dx, pt[1] + dy) if pt is not None else None for pt in orig_points]
            elif self.interaction_mode.startswith("resize"):
                scale = max(0.1, 1.0 + (dx / 100.0))
                non_none_pts = np.array([p for p in orig_points if p is not None])
                if len(non_none_pts) > 0:
                    centroid = non_none_pts.mean(axis=0)
                    scaled_points = []
                    for pt in orig_points:
                        if pt is None:
                            scaled_points.append(None)
                        else:
                            new_pt = centroid + (np.array(pt) - centroid) * scale
                            scaled_points.append((float(new_pt[0]), float(new_pt[1])))
                    self.active_item.points = scaled_points
            self.is_dirty = True
            return
            
        stype = self.active_item.shape_type
        ip = self.interaction_initial_params
        
        new_params = ip.copy()
        
        if self.interaction_mode == "move":
            if stype in ("circle", "ellipse"):
                new_params["cx"] = ip["cx"] + dx
                new_params["cy"] = ip["cy"] + dy
            elif stype in ("rectangle", "square"):
                new_params["x"] = ip["x"] + dx
                new_params["y"] = ip["y"] + dy
            elif stype == "triangle":
                new_params["pts"] = [(pt[0] + dx, pt[1] + dy) for pt in ip["pts"]]
            elif stype in ("line", "arrow"):
                new_params["p0"] = (ip["p0"][0] + dx, ip["p0"][1] + dy)
                new_params["p1"] = (ip["p1"][0] + dx, ip["p1"][1] + dy)
            elif stype == "text":
                new_params["x"] = ip["x"] + dx
                new_params["y"] = ip["y"] + dy
                
        elif self.interaction_mode.startswith("resize"):
            # Zoom dependent scale, here dx is in document coordinates
            # A rough scale based on interaction dx
            scale = max(0.1, 1.0 + (dx / 100.0))
            if stype == "circle":
                new_params["radius"] = max(1.0, ip["radius"] * scale)
            elif stype == "ellipse":
                new_params["axes_a"] = max(1.0, ip["axes_a"] * scale)
                new_params["axes_b"] = max(1.0, ip["axes_b"] * scale)
            elif stype == "square":
                new_params["side"] = max(1.0, ip["side"] * scale)
            elif stype == "rectangle":
                new_params["w"] = max(1.0, ip["w"] * scale)
                new_params["h"] = max(1.0, ip["h"] * scale)
            elif stype == "triangle":
                pts = np.array(ip["pts"])
                centroid = pts.mean(axis=0)
                new_pts = centroid + (pts - centroid) * scale
                new_params["pts"] = [(pt[0], pt[1]) for pt in new_pts]
            elif stype in ("line", "arrow"):
                p0 = np.array(ip["p0"])
                p1 = np.array(ip["p1"])
                p1 = p0 + (p1 - p0) * scale
                new_params["p1"] = (p1[0], p1[1])
            elif stype == "text":
                new_params["scale"] = max(0.5, ip.get("scale", 1.0) * scale)
                
        self.active_item.params = new_params
        self.is_dirty = True
        
    def end_interaction(self) -> None:
        if self.active_item and self.interaction_initial_params:
            if isinstance(self.active_item, Stroke):
                from app.commands import ModifyStrokeCommand
                final_points = self.active_item.points.copy()
                self.active_item.points = self.interaction_initial_params["points"]
                cmd = ModifyStrokeCommand(self.active_item, self.interaction_initial_params["points"], final_points)
                self.commands.execute(cmd)
            else:
                # Revert the temporary change and push formal command
                final_params = self.active_item.params.copy()
                self.active_item.params = self.interaction_initial_params
                cmd = ModifyShapeCommand(self.active_item, self.interaction_initial_params, final_params)
                self.commands.execute(cmd)
            
        self.active_item = None
        self.interaction_mode = None
        self.interaction_start_pt = None
        self.interaction_initial_params = None
        self.is_dirty = True

    def delete_hovered_shape(self) -> bool:
        if self.hovered_item is not None:
            self.remove_item(self.hovered_item)
            self.hovered_item = None
            return True
        return False
        
    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def remove_item(self, item) -> None:
        layer_idx = 0
        for i, layer in enumerate(self.document.layers):
            if item in layer.items:
                layer_idx = i
                break
        cmd = RemoveItemCommand(item, layer_idx)
        self.commands.execute(cmd)
        self.is_dirty = True
        
    def clear(self) -> None:
        cmd = ClearDocumentCommand()
        self.commands.execute(cmd)
        self.is_dirty = True
        
    def undo(self) -> None:
        if self.commands.undo():
            self.is_dirty = True
            
    def redo(self) -> None:
        if self.commands.redo():
            self.is_dirty = True
            
    def cycle_color(self) -> None:
        try:
            idx = config.COLOR_PALETTE.index(self.brush_color)
            idx = (idx + 1) % len(config.COLOR_PALETTE)
        except ValueError:
            idx = 0
        self.brush_color = config.COLOR_PALETTE[idx]

    def set_color(self, color: Tuple[int, int, int]) -> None:
        self.brush_color = color

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def to_json(self) -> str:
        import json
        
        layers_data = []
        for layer in self.document.layers:
            items_data = []
            for item in layer.items:
                if isinstance(item, Stroke):
                    items_data.append({
                        "type": "stroke",
                        "points": item.points,
                        "color": item.color,
                        "thickness": item.thickness,
                        "is_eraser": item.is_eraser
                    })
                elif isinstance(item, Shape):
                    items_data.append({
                        "type": "shape",
                        "shape_type": item.shape_type,
                        "params": item.params,
                        "color": item.color,
                        "thickness": item.thickness
                    })
            layers_data.append({
                "name": layer.name,
                "visible": layer.visible,
                "locked": layer.locked,
                "items": items_data
            })
            
        data = {
            "version": 3,
            "layers": layers_data,
            "active_layer_index": self.document.active_layer_index,
            "viewport": {
                "pan_x": self.viewport.pan_x,
                "pan_y": self.viewport.pan_y,
                "zoom": self.viewport.zoom
            },
            "brush_color": self.brush_color,
            "brush_size": self.brush_size
        }
        return json.dumps(data)

    def import_workspace(self, json_str: str) -> None:
        from app.commands import ImportWorkspaceCommand
        old_json = self.to_json()
        cmd = ImportWorkspaceCommand(self, old_json, json_str)
        self.commands.execute(cmd)

    def from_json(self, json_str: str, clear_history: bool = True) -> None:
        import json
        try:
            data = json.loads(json_str)
            self.document.layers = []
            if clear_history:
                self.commands.clear_history()
            
            for layer_data in data.get("layers", []):
                layer = Layer(layer_data.get("name", "Layer"))
                layer.visible = layer_data.get("visible", True)
                layer.locked = layer_data.get("locked", False)
                for item_data in layer_data.get("items", []):
                    if item_data.get("type") == "stroke":
                        pts = [(float(p[0]), float(p[1])) if p is not None else None for p in item_data["points"]]
                        color = tuple(item_data["color"])
                        layer.items.append(Stroke(pts, color, item_data["thickness"], item_data.get("is_eraser", False)))
                    elif item_data.get("type") == "shape":
                        color = tuple(item_data["color"])
                        layer.items.append(Shape(item_data["shape_type"], item_data["params"], color, item_data["thickness"]))
                self.document.layers.append(layer)
                
            if not self.document.layers:
                self.document.layers.append(Layer("Layer 1"))
                
            self.document.active_layer_index = data.get("active_layer_index", 0)
            
            vp = data.get("viewport", {})
            self.viewport.pan_x = vp.get("pan_x", 0.0)
            self.viewport.pan_y = vp.get("pan_y", 0.0)
            self.viewport.zoom = vp.get("zoom", 1.0)
            
            if "brush_color" in data:
                self.brush_color = tuple(data["brush_color"])
            if "brush_size" in data:
                self.brush_size = data["brush_size"]
            
            self.is_dirty = True
        except Exception as e:
            print(f"Error loading Workspace JSON: {e}")
            self.clear()

    def get_canvas(self) -> np.ndarray:
        self.is_dirty = False
        return self.engine.render(self.document, self.viewport, active_stroke=self._current_stroke, selected_item=self.selected_item)

    def export_canvas(self, bg_color=(255, 255, 255)) -> np.ndarray:
        """Render the artwork cleanly for export (no UI, no selection)."""
        canvas = self.engine.render(self.document, self.viewport, active_stroke=None, selected_item=None)
        # The engine renders on black (0,0,0) by default. If we want a white background:
        if bg_color != (0, 0, 0):
            mask = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(mask, 1, 255, cv2.THRESH_BINARY)
            mask_inv = cv2.bitwise_not(mask)
            bg = np.full(canvas.shape, bg_color, dtype=np.uint8)
            bg_masked = cv2.bitwise_and(bg, bg, mask=mask_inv)
            canvas = cv2.add(bg_masked, canvas)
        return canvas

    def to_svg(self) -> str:
        """Export the current document as an SVG string."""
        w, h = config.CAMERA_WIDTH, config.CAMERA_HEIGHT
        svg = [f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">']
        # Background
        svg.append(f'  <rect width="100%" height="100%" fill="white"/>')
        
        for layer in self.document.layers:
            if not layer.visible: continue
            for item in layer.items:
                if isinstance(item, Stroke):
                    if not item.points: continue
                    color = f"rgb({item.color[2]},{item.color[1]},{item.color[0]})"
                    pts = [self.viewport.doc_to_screen(pt) if pt is not None else None for pt in item.points]
                    segments = []
                    curr_seg = []
                    for pt in pts:
                        if pt is None:
                            if curr_seg:
                                segments.append(curr_seg)
                                curr_seg = []
                        else:
                            curr_seg.append(pt)
                    if curr_seg:
                        segments.append(curr_seg)
                        
                    path_parts = []
                    for seg in segments:
                        if seg:
                            path_parts.append(f"M {seg[0][0]},{seg[0][1]} " + " ".join([f"L {p[0]},{p[1]}" for p in seg[1:]]))
                    path_d = " ".join(path_parts)
                    svg.append(f'  <path d="{path_d}" fill="none" stroke="{color}" stroke-width="{item.thickness}" stroke-linecap="round" stroke-linejoin="round"/>')
                elif isinstance(item, Shape):
                    color = f"rgb({item.color[2]},{item.color[1]},{item.color[0]})"
                    stype = item.shape_type
                    params = item.params.copy()
                    
                    if stype in ("circle", "ellipse"):
                        c = self.viewport.doc_to_screen((params["cx"], params["cy"]))
                        rx = int(params.get("radius", params.get("axes_a", 0)) * self.viewport.zoom)
                        ry = int(params.get("radius", params.get("axes_b", 0)) * self.viewport.zoom)
                        svg.append(f'  <ellipse cx="{c[0]}" cy="{c[1]}" rx="{rx}" ry="{ry}" fill="none" stroke="{color}" stroke-width="{item.thickness}"/>')
                    elif stype in ("rectangle", "square"):
                        p = self.viewport.doc_to_screen((params["x"], params["y"]))
                        width_val = int(params.get("w", params.get("side", 0)) * self.viewport.zoom)
                        height_val = int(params.get("h", params.get("side", 0)) * self.viewport.zoom)
                        svg.append(f'  <rect x="{p[0]}" y="{p[1]}" width="{width_val}" height="{height_val}" fill="none" stroke="{color}" stroke-width="{item.thickness}"/>')
                    elif stype == "line":
                        p0 = self.viewport.doc_to_screen(params["p0"])
                        p1 = self.viewport.doc_to_screen(params["p1"])
                        svg.append(f'  <line x1="{p0[0]}" y1="{p0[1]}" x2="{p1[0]}" y2="{p1[1]}" stroke="{color}" stroke-width="{item.thickness}"/>')
                    elif stype == "arrow":
                        p0 = self.viewport.doc_to_screen(params["p0"])
                        p1 = self.viewport.doc_to_screen(params["p1"])
                        dx = p1[0] - p0[0]
                        dy = p1[1] - p0[1]
                        angle = math.atan2(dy, dx)
                        arrow_len = 15.0
                        tip1 = (
                            p1[0] - arrow_len * math.cos(angle - math.pi / 6),
                            p1[1] - arrow_len * math.sin(angle - math.pi / 6)
                        )
                        tip2 = (
                            p1[0] - arrow_len * math.cos(angle + math.pi / 6),
                            p1[1] - arrow_len * math.sin(angle + math.pi / 6)
                        )
                        path_d = f"M {p0[0]},{p0[1]} L {p1[0]},{p1[1]} M {p1[0]},{p1[1]} L {tip1[0]},{tip1[1]} M {p1[0]},{p1[1]} L {tip2[0]},{tip2[1]}"
                        svg.append(f'  <path d="{path_d}" fill="none" stroke="{color}" stroke-width="{item.thickness}" stroke-linecap="round" stroke-linejoin="round"/>')
                    elif stype in ("triangle", "diamond", "pentagon", "hexagon", "star"):
                        pts = [self.viewport.doc_to_screen(pt) for pt in params["pts"]]
                        points_str = " ".join([f"{p[0]},{p[1]}" for p in pts])
                        svg.append(f'  <polygon points="{points_str}" fill="none" stroke="{color}" stroke-width="{item.thickness}"/>')
                    elif stype == "text":
                        p = self.viewport.doc_to_screen((params["x"], params["y"]))
                        scale = params.get("scale", 1.0) * self.viewport.zoom
                        font_size = int(20 * scale)
                        text_content = params.get("text", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        svg.append(f'  <text x="{p[0]}" y="{p[1]}" font-family="sans-serif" font-size="{font_size}" fill="{color}">{text_content}</text>')
                    
        svg.append("</svg>")
        return "\n".join(svg)

    def load_canvas(self, image: np.ndarray) -> None:
        # A purely vector-based engine cannot "load" a raster image as strokes.
        # But to prevent crashing, we ignore or import as a BackgroundImage layer in the future.
        pass

    def composite(self, display_frame: np.ndarray) -> np.ndarray:
        overlay = self.get_canvas()
        mask = cv2.cvtColor(overlay, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(mask, 1, 255, cv2.THRESH_BINARY)
        mask_inv = cv2.bitwise_not(mask)
        
        # In case dimensions differ, resize overlay
        if overlay.shape[:2] != display_frame.shape[:2]:
            overlay = cv2.resize(overlay, (display_frame.shape[1], display_frame.shape[0]))
            mask = cv2.resize(mask, (display_frame.shape[1], display_frame.shape[0]))
            mask_inv = cv2.resize(mask_inv, (display_frame.shape[1], display_frame.shape[0]))
            
        bg = cv2.bitwise_and(display_frame, display_frame, mask=mask_inv)
        fg = cv2.bitwise_and(overlay, overlay, mask=mask)
        return cv2.add(bg, fg)
