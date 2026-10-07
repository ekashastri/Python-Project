import math
import time
from typing import Optional, Tuple

import config
from app.hand_tracker import HandLandmarks, INDEX_TIP


class LandmarkProcessor:
    """
    Applies exponential smoothing, velocity filtering, maximum movement clamp,
    and outlier rejection to raw hand coordinates.
    """
    def __init__(self) -> None:
        self.alpha_min = getattr(config, "LANDMARK_SMOOTH_ALPHA_MIN", 0.08)
        self.alpha_max = getattr(config, "LANDMARK_SMOOTH_ALPHA_MAX", 0.90)
        self.velocity_scale = getattr(config, "LANDMARK_SMOOTH_VELOCITY_SCALE", 80.0)
        self.max_movement = getattr(config, "LANDMARK_MAX_MOVEMENT", 150)
        
        self.last_pos: Optional[Tuple[float, float]] = None

    def process(self, raw_x: float, raw_y: float) -> Tuple[int, int]:
        if self.last_pos is None:
            self.last_pos = (raw_x, raw_y)
            return (int(raw_x), int(raw_y))
            
        dx = raw_x - self.last_pos[0]
        dy = raw_y - self.last_pos[1]
        dist = math.hypot(dx, dy)
        
        # Outlier rejection
        if dist > self.max_movement:
            # Completely reject impossible movements
            return (int(self.last_pos[0]), int(self.last_pos[1]))
            
        # Velocity filtering for dynamic alpha
        alpha = self.alpha_min + (self.alpha_max - self.alpha_min) * min(1.0, dist / self.velocity_scale)
        
        smoothed_x = self.last_pos[0] + alpha * dx
        smoothed_y = self.last_pos[1] + alpha * dy
        
        self.last_pos = (smoothed_x, smoothed_y)
        return (int(smoothed_x), int(smoothed_y))

    def reset(self) -> None:
        self.last_pos = None


class CursorTracker:
    """
    Maintains the global cursor position based on the index fingertip.
    """
    def __init__(self) -> None:
        self.processor = LandmarkProcessor()
        self.current_pos: Optional[Tuple[int, int]] = None
        
        # State for interpolation
        self.last_update_time: float = 0.0
        self.velocity: Tuple[float, float] = (0.0, 0.0)
        self.persistence_timeout: float = getattr(config, "STROKE_PERSISTENCE_TIMEOUT", 0.20)
        self.is_recovering = False

    def update(self, hand: Optional[HandLandmarks]) -> Tuple[Optional[Tuple[int, int]], Optional[Tuple[int, int]], Tuple[float, float]]:
        now = time.time()
        
        if hand is not None:
            raw_x, raw_y = hand.landmarks[INDEX_TIP]
            
            if self.is_recovering and self.current_pos is not None:
                recovery_alpha = getattr(config, "TRACKING_RECOVERY_ALPHA", 0.25)
                smoothed_x = self.current_pos[0] + recovery_alpha * (raw_x - self.current_pos[0])
                smoothed_y = self.current_pos[1] + recovery_alpha * (raw_y - self.current_pos[1])
                smoothed = (int(smoothed_x), int(smoothed_y))
                self.processor.last_pos = (smoothed_x, smoothed_y)
                self.is_recovering = False
            else:
                smoothed = self.processor.process(float(raw_x), float(raw_y))
            
            if self.current_pos is not None:
                dt = max(0.001, now - self.last_update_time)
                vx = (smoothed[0] - self.current_pos[0]) / dt
                vy = (smoothed[1] - self.current_pos[1]) / dt
                
                # Smooth velocity to prevent erratic updates
                self.velocity = (
                    self.velocity[0] * 0.8 + vx * 0.2,
                    self.velocity[1] * 0.8 + vy * 0.2
                )
            else:
                self.velocity = (0.0, 0.0)
                
            self.current_pos = smoothed
            self.last_update_time = now
            return ((int(raw_x), int(raw_y)), self.current_pos, self.velocity)
            
        else:
            # Frame skipped / tracking momentarily lost:
            # Freeze cursor for persistence_timeout
            if self.current_pos is not None and (now - self.last_update_time < self.persistence_timeout):
                # We intentionally do not update last_update_time so the timeout eventually expires
                # We also do not update the processor's last_pos so when the hand returns, it anchors correctly.
                self.is_recovering = True
                return (None, self.current_pos, self.velocity)
            else:
                self.current_pos = None
                self.processor.reset()
                self.velocity = (0.0, 0.0)
                self.is_recovering = False
                return (None, None, self.velocity)
