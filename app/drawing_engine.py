"""
Stateless Drawing Engine for rendering the Document to a NumPy canvas.
"""
import math
from typing import Tuple, List, Optional
import cv2
import numpy as np

from app.model import Document, Stroke, Shape, Layer, Viewport


class DrawingEngine:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height

    def render(
        self,
        document: Document,
        viewport: Viewport,
        active_stroke: Optional[Stroke] = None,
        selected_item=None
    ) -> np.ndarray:
        """Render the entire document onto a new canvas array."""
        canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        for layer in document.layers:
            if not layer.visible:
                continue
            for item in layer.items:
                if isinstance(item, Stroke):
                    self._render_stroke(canvas, item, viewport)
                elif isinstance(item, Shape):
                    self._render_shape(canvas, item, viewport)

                if item == selected_item:
                    self._render_selection_overlay(canvas, item, viewport)

        # Render the transient active stroke currently being drawn
        if active_stroke is not None:
            self._render_stroke(canvas, active_stroke, viewport)

        return canvas

    def _render_stroke(self, canvas: np.ndarray, stroke: Stroke, viewport: Viewport) -> None:
        # Split stroke.points by None into segments
        segments = []
        curr_segment = []
        for pt in stroke.points:
            if pt is None:
                if curr_segment:
                    segments.append(curr_segment)
                    curr_segment = []
            else:
                curr_segment.append(pt)
        if curr_segment:
            segments.append(curr_segment)

        color = (0, 0, 0) if stroke.is_eraser else stroke.color

        cv_pts = []
        for seg in segments:
            pts = [viewport.doc_to_screen(pt) for pt in seg]
            int_pts = [(int(p[0]), int(p[1])) for p in pts]
            if len(int_pts) >= 2:
                cv_pts.append(np.array(int_pts))
            elif len(int_pts) == 1:
                cv2.circle(canvas, int_pts[0], stroke.thickness // 2, color, -1)

        if cv_pts:
            cv2.polylines(canvas, cv_pts, isClosed=False, color=color, thickness=stroke.thickness, lineType=cv2.LINE_AA)
            for seg in cv_pts:
                cv2.circle(canvas, tuple(seg[0]), stroke.thickness // 2, color, -1)
                cv2.circle(canvas, tuple(seg[-1]), stroke.thickness // 2, color, -1)

    def _render_shape(self, canvas: np.ndarray, shape: Shape, viewport: Viewport) -> None:
        params = shape.params.copy()
        stype = shape.shape_type

        if stype in ("circle", "ellipse"):
            c = viewport.doc_to_screen((params["cx"], params["cy"]))
            params["cx"], params["cy"] = int(c[0]), int(c[1])
            params["radius"] = int(params.get("radius", 0) * viewport.zoom)
            params["axes_a"] = int(params.get("axes_a", 0) * viewport.zoom)
            params["axes_b"] = int(params.get("axes_b", 0) * viewport.zoom)

        elif stype in ("rectangle", "square"):
            p = viewport.doc_to_screen((params["x"], params["y"]))
            params["x"], params["y"] = int(p[0]), int(p[1])
            params["w"] = int(params.get("w", 0) * viewport.zoom)
            params["h"] = int(params.get("h", 0) * viewport.zoom)
            params["side"] = int(params.get("side", 0) * viewport.zoom)

        elif stype in ("triangle", "diamond", "pentagon", "hexagon", "star"):
            pts = [viewport.doc_to_screen(pt) for pt in params["pts"]]
            params["pts"] = [(int(p[0]), int(p[1])) for p in pts]

        elif stype in ("line", "arrow"):
            p0 = viewport.doc_to_screen(params["p0"])
            p1 = viewport.doc_to_screen(params["p1"])
            params["p0"] = (int(p0[0]), int(p0[1]))
            params["p1"] = (int(p1[0]), int(p1[1]))

        elif stype == "text":
            p = viewport.doc_to_screen((params.get("x", 100), params.get("y", 100)))
            params["x"], params["y"] = int(p[0]), int(p[1])
            params["scale"] = params.get("scale", 1.0) * viewport.zoom

        self._draw_clean_shape(canvas, stype, params, shape.color, shape.thickness)

    def _draw_clean_shape(
        self,
        canvas: np.ndarray,
        stype: str,
        params: dict,
        color: Tuple[int, int, int],
        thickness: int
    ) -> None:
        """Helper to render vector shapes directly using OpenCV primitives."""
        if stype == "circle":
            cx, cy = int(params["cx"]), int(params["cy"])
            r = max(1, int(params.get("radius", 10)))
            cv2.circle(canvas, (cx, cy), r, color, thickness, cv2.LINE_AA)

        elif stype == "ellipse":
            cx, cy = int(params["cx"]), int(params["cy"])
            a = max(1, int(params.get("axes_a", 10)))
            b = max(1, int(params.get("axes_b", 10)))
            angle = int(params.get("angle", 0))
            cv2.ellipse(canvas, (cx, cy), (a, b), angle, 0, 360, color, thickness, cv2.LINE_AA)

        elif stype in ("rectangle", "square"):
            x, y = int(params["x"]), int(params["y"])
            w = max(1, int(params.get("w", params.get("side", 10))))
            h = max(1, int(params.get("h", params.get("side", 10))))
            cv2.rectangle(canvas, (x, y), (x + w, y + h), color, thickness, cv2.LINE_AA)

        elif stype in ("triangle", "diamond", "pentagon", "hexagon", "star"):
            pts = params.get("pts", [])
            if pts:
                int_pts = np.array([(int(p[0]), int(p[1])) for p in pts], dtype=np.int32)
                cv2.polylines(canvas, [int_pts], isClosed=True, color=color, thickness=thickness, lineType=cv2.LINE_AA)

        elif stype == "line":
            p0 = (int(params["p0"][0]), int(params["p0"][1]))
            p1 = (int(params["p1"][0]), int(params["p1"][1]))
            cv2.line(canvas, p0, p1, color, thickness, cv2.LINE_AA)

        elif stype == "arrow":
            p0 = (int(params["p0"][0]), int(params["p0"][1]))
            p1 = (int(params["p1"][0]), int(params["p1"][1]))
            cv2.line(canvas, p0, p1, color, thickness, cv2.LINE_AA)
            dx = p1[0] - p0[0]
            dy = p1[1] - p0[1]
            angle = math.atan2(dy, dx)
            arrow_len = 15.0
            tip1 = (
                int(p1[0] - arrow_len * math.cos(angle - math.pi / 6)),
                int(p1[1] - arrow_len * math.sin(angle - math.pi / 6))
            )
            tip2 = (
                int(p1[0] - arrow_len * math.cos(angle + math.pi / 6)),
                int(p1[1] - arrow_len * math.sin(angle + math.pi / 6))
            )
            cv2.line(canvas, p1, tip1, color, thickness, cv2.LINE_AA)
            cv2.line(canvas, p1, tip2, color, thickness, cv2.LINE_AA)

        elif stype == "text":
            x, y = int(params.get("x", 100)), int(params.get("y", 100))
            text = params.get("text", "")
            scale = max(0.2, float(params.get("scale", 1.0)))
            cv2.putText(canvas, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, max(1, thickness), cv2.LINE_AA)

    def _render_selection_overlay(self, canvas: np.ndarray, item, viewport: Viewport) -> None:
        x1, y1, x2, y2 = 0, 0, 0, 0

        if isinstance(item, Stroke):
            if not item.points:
                return
            pts = [viewport.doc_to_screen(pt) for pt in item.points if pt is not None]
            pts_arr = np.array(pts)
            x1, y1 = int(pts_arr[:, 0].min()), int(pts_arr[:, 1].min())
            x2, y2 = int(pts_arr[:, 0].max()), int(pts_arr[:, 1].max())

        elif isinstance(item, Shape):
            stype = item.shape_type
            params = item.params
            if stype == "circle":
                c = viewport.doc_to_screen((params["cx"], params["cy"]))
                r = int(params.get("radius", 0) * viewport.zoom)
                x1, y1, x2, y2 = int(c[0]) - r, int(c[1]) - r, int(c[0]) + r, int(c[1]) + r
            elif stype == "ellipse":
                c = viewport.doc_to_screen((params["cx"], params["cy"]))
                rx = int(params.get("axes_a", 0) * viewport.zoom)
                ry = int(params.get("axes_b", 0) * viewport.zoom)
                r = max(rx, ry)
                x1, y1, x2, y2 = int(c[0]) - r, int(c[1]) - r, int(c[0]) + r, int(c[1]) + r
            elif stype in ("rectangle", "square"):
                p = viewport.doc_to_screen((params["x"], params["y"]))
                w = int(params.get("w", params.get("side", 0)) * viewport.zoom)
                h = int(params.get("h", params.get("side", 0)) * viewport.zoom)
                x1, y1, x2, y2 = int(p[0]), int(p[1]), int(p[0]) + w, int(p[1]) + h
            elif stype in ("triangle", "diamond", "pentagon", "hexagon", "star"):
                pts = [viewport.doc_to_screen(pt) for pt in params["pts"]]
                pts_arr = np.array(pts)
                x1, y1 = int(pts_arr[:, 0].min()), int(pts_arr[:, 1].min())
                x2, y2 = int(pts_arr[:, 0].max()), int(pts_arr[:, 1].max())
            elif stype in ("line", "arrow"):
                p0 = viewport.doc_to_screen(params["p0"])
                p1 = viewport.doc_to_screen(params["p1"])
                x1, y1 = int(min(p0[0], p1[0])), int(min(p0[1], p1[1]))
                x2, y2 = int(max(p0[0], p1[0])), int(max(p0[1], p1[1]))
            elif stype == "text":
                p = viewport.doc_to_screen((params["x"], params["y"]))
                scale = params.get("scale", 1.0) * viewport.zoom
                text_len = len(params.get("text", ""))
                x1, y1 = int(p[0]), int(p[1] - 20 * scale)
                x2, y2 = int(p[0] + text_len * 15 * scale), int(p[1] + 5 * scale)

        # Draw bounding box
        color = (180, 230, 20)  # Brand accent
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 1, cv2.LINE_AA)

        # Draw resize handles
        handles = [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]
        for hx, hy in handles:
            cv2.circle(canvas, (hx, hy), 4, color, -1, cv2.LINE_AA)
            cv2.circle(canvas, (hx, hy), 4, (0, 0, 0), 1, cv2.LINE_AA)

        # Draw delete button
        del_x, del_y = x2 + 20, y1 - 20
        cv2.circle(canvas, (del_x, del_y), 10, (50, 50, 220), -1, cv2.LINE_AA)
        cv2.circle(canvas, (del_x, del_y), 10, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.line(canvas, (del_x - 4, del_y - 4), (del_x + 4, del_y + 4), (255, 255, 255), 2, cv2.LINE_AA)
        cv2.line(canvas, (del_x - 4, del_y + 4), (del_x + 4, del_y - 4), (255, 255, 255), 2, cv2.LINE_AA)
