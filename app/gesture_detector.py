"""
Gesture detector module - interprets hand landmarks as user intents.
v2.0 - Simplified Production Gesture System

This version replaces the previous multi-gesture, multi-state mapping
with a small, predictable set of four gestures, each tied to exactly
one user-facing action:

  POINT      (one index finger)        -> Draw continuously
  FIST       (closed fist)             -> Pause drawing (freeze stroke)
  OPEN_PALM  (five fingers, held)      -> Clear canvas (once per pose)
  PINCH      (thumb + index touching)  -> Move / drag the entire drawing

Design goals
------------
* Index-finger drawing starts the instant the pose is seen (zero
  confirmation delay) and stops the instant the pose changes.
* A closed fist freezes the stroke in place (no new points are added)
  but cursor tracking keeps running; returning to the index-finger
  pose resumes the SAME stroke immediately, with no gap or restart.
* The open-palm "clear" gesture requires a short, stable hold
  (PALM_HOLD_DURATION, ~200-300ms) before it fires, and fires only
  once per pose - the user must lower the palm before it can clear
  again. This prevents accidental wipes from a single noisy frame.
* Pinch (thumb + index) drags the whole drawing. It never creates new
  strokes, and only does anything once the canvas is non-empty.
* All non-instant transitions (palm, pinch) use consecutive-frame
  confirmation (GESTURE_DEBOUNCE_FRAMES, 3-5 frames) so one noisy
  frame can't flip the active gesture. If tracking is briefly lost
  (a "ghost" frame) the previously confirmed gesture is held steady
  rather than dropping to NONE.
"""

from __future__ import annotations

import math
import time
from enum import Enum, auto
from typing import List, Optional, Tuple

import config
from app.hand_tracker import (
    HandLandmarks,
    INDEX_DIP,
    INDEX_PIP,
    INDEX_TIP,
    MIDDLE_DIP,
    MIDDLE_PIP,
    MIDDLE_TIP,
    PINKY_DIP,
    PINKY_PIP,
    PINKY_TIP,
    RING_DIP,
    RING_PIP,
    RING_TIP,
    THUMB_IP,
    THUMB_TIP,
    WRIST,
)


class Gesture(Enum):
    """
    Recognised hand gestures mapped to application actions.

    NOTE: enum members are kept compatible with the rest of the app
    (app/ui.py, main.py) which import Gesture by name. PEACE and
    PALM_DETECTED are retained only so existing imports/dict lookups
    elsewhere don't break; this detector never emits them.
    """
    NONE  = auto()
    PINCH = auto()       # Move / drag the whole drawing
    POINT = auto()       # Draw
    OPEN_PALM = auto()   # Clear canvas (after brief stable hold)
    FIST  = auto()       # Pause drawing
    PEACE = auto()       # Unused in v2 (kept for compatibility)
    PALM_DETECTED = auto()  # Unused in v2 (kept for compatibility)


# Human-readable labels for the HUD
GESTURE_LABELS = {
    Gesture.NONE:      "Idle",
    Gesture.PINCH:     "Moving Drawing",
    Gesture.POINT:     "Drawing",
    Gesture.OPEN_PALM: "Clearing...",
    Gesture.FIST:      "Paused",
    Gesture.PEACE:     "Palette",
    Gesture.PALM_DETECTED: "Clearing...",
}


class GestureDetector:
    """
    Stateful gesture classifier for the simplified v2 interaction model.

    Four gestures only:
        POINT (draw) / FIST (pause) / OPEN_PALM (clear) / PINCH (move)

    Draw and Pause are instantaneous (no confirmation delay) so
    handwriting feels natural and pausing/resuming is immediate.
    Clear and Move are gated by short consecutive-frame confirmation
    to avoid accidental triggers from single noisy frames.
    """

    def __init__(self) -> None:
        self._gesture: Gesture = Gesture.NONE

        # --- Debounce: candidate raw gesture must be stable for N frames ---
        self._candidate_raw: Optional[str] = None
        self._candidate_frames: int = 0

        # --- Open-palm hold tracking ---
        self._palm_hold_start: Optional[float] = None
        self._palm_armed: bool = True   # re-armed once the pose is left
        self._is_pinching = False
        self.last_pinch_distance = 0.0
        self._pinch_counter = 0

        # --- Active stroke flag (set by main.py via property) ---
        self._stroke_active: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def stroke_active(self) -> bool:
        return self._stroke_active

    @stroke_active.setter
    def stroke_active(self, value: bool) -> None:
        self._stroke_active = value

    def detect(
        self,
        hand: HandLandmarks,
        frame_shape: Tuple[int, int],
    ) -> Tuple[Gesture, float, dict]:
        """
        Classify the current hand pose.

        Parameters
        ----------
        hand        : detected hand landmarks (may be a ghost frame)
        frame_shape : (height, width) of the frame for normalisation

        Returns
        -------
        Tuple containing:
        - Gesture enum value reflecting the current confirmed gesture.
        - Confidence float (0.0 to 1.0)
        - Finger states dict
        """
        lm = hand.landmarks
        h, w = frame_shape

        # Normalise landmarks to 0-1
        norm: List[Tuple[float, float]] = [(x / w, y / h) for x, y in lm]

        raw, finger_states = self._raw_gesture(norm)
        confidence = self._update_gesture(raw)
        return self._gesture, confidence, finger_states

    # ------------------------------------------------------------------
    # Raw (single-frame, un-debounced) gesture classification
    # ------------------------------------------------------------------

    def _raw_gesture(self, norm: List[Tuple[float, float]]) -> Tuple[str, dict]:
        """Return a raw gesture name and finger states from normalised landmarks."""
        thumb_up  = self._thumb_extended(norm)
        index_up  = self._finger_extended(norm, INDEX_TIP,  INDEX_PIP,  INDEX_DIP,  WRIST)
        middle_up = self._finger_extended(norm, MIDDLE_TIP, MIDDLE_PIP, MIDDLE_DIP, WRIST)
        ring_up   = self._finger_extended(norm, RING_TIP,   RING_PIP,   RING_DIP,   WRIST)
        pinky_up  = self._finger_extended(norm, PINKY_TIP,  PINKY_PIP,  PINKY_DIP,  WRIST)
        
        finger_states = {
            "Thumb": thumb_up,
            "Index": index_up,
            "Middle": middle_up,
            "Ring": ring_up,
            "Pinky": pinky_up
        }
        
        # Pinch (thumb + index touching) takes priority -> Move gesture
        # Normalise pinch distance to rotation-invariant hand size
        # Hand size is width from INDEX_MCP to PINKY_MCP and height from WRIST to MIDDLE_MCP
        hand_scale = (self._distance(norm[5], norm[17]) + self._distance(norm[0], norm[9])) / 2.0
        pinch_dist_raw = self._distance(norm[THUMB_TIP], norm[INDEX_TIP])
        self.last_pinch_distance = pinch_dist_raw / (hand_scale + 1e-6)

        PINCH_START_THRESH = getattr(config, "PINCH_START_THRESHOLD", 0.15)
        PINCH_RELEASE_THRESH = getattr(config, "PINCH_RELEASE_THRESHOLD", 0.30)

        # Scale-dependent offset for camera distance (fixed pixel resolution allowance)
        pixel_error_allowance = 0.005 / (hand_scale + 0.01)
        pinch_start_limit = PINCH_START_THRESH + pixel_error_allowance
        pinch_release_limit = PINCH_RELEASE_THRESH + pixel_error_allowance

        # Pinch frame-based stable entry and exit hysteresis
        if self._is_pinching:
            if self.last_pinch_distance > pinch_release_limit:
                self._pinch_counter += 1
                if self._pinch_counter >= getattr(config, "PINCH_EXIT_FRAMES", 3):
                    self._is_pinching = False
                    self._pinch_counter = 0
            else:
                self._pinch_counter = 0
        else:
            if self.last_pinch_distance < pinch_start_limit:
                self._pinch_counter += 1
                if self._pinch_counter >= getattr(config, "PINCH_ENTER_FRAMES", 2):
                    self._is_pinching = True
                    self._pinch_counter = 0
            else:
                self._pinch_counter = 0

        if self._is_pinching:
            return "PINCH", finger_states

        # Open Palm (sum of extended fingers >= threshold) -> Clear
        extended_count = sum([thumb_up, index_up, middle_up, ring_up, pinky_up])
        palm_open_finger_count = getattr(config, "PALM_OPEN_FINGER_COUNT", 4)
        if extended_count >= palm_open_finger_count:
            return "PALM", finger_states

        # Gesture Locking: If currently drawing, ignore transitional noise
        if self._stroke_active and index_up:
            return "POINT", finger_states

        # Fist (no fingers extended) -> Pause
        if not index_up and not middle_up and not ring_up and not pinky_up:
            return "FIST", finger_states

        # Peace (index + middle extended, ring + pinky curled) -> Palette
        if index_up and middle_up and not ring_up and not pinky_up:
            return "PEACE", finger_states

        # Point: only the index finger extended -> Draw
        if index_up and not middle_up and not ring_up and not pinky_up:
            return "POINT", finger_states

        return "NONE", finger_states

    # ------------------------------------------------------------------
    # Gesture confirmation / transition logic
    # ------------------------------------------------------------------

    def _map_raw_to_gesture(self, raw: str) -> Gesture:
        if raw == "POINT":
            return Gesture.POINT
        elif raw == "FIST":
            return Gesture.FIST
        elif raw == "PINCH":
            return Gesture.PINCH
        elif raw == "PALM":
            return Gesture.OPEN_PALM
        elif raw == "PEACE":
            return Gesture.PEACE
        else:
            return Gesture.NONE

    def _update_gesture(self, raw: str) -> float:
        """Advance the confirmed gesture given the latest raw reading and return confidence."""
        debounce_n = getattr(config, "GESTURE_DEBOUNCE_FRAMES", 3)

        # --- Debounce bookkeeping: consecutive frames of the same raw value ---
        if raw == self._candidate_raw:
            self._candidate_frames += 1
        else:
            self._candidate_raw = raw
            self._candidate_frames = 1

        confirmed_n_frames = self._candidate_frames >= debounce_n
        confidence = min(1.0, self._candidate_frames / max(1, debounce_n))

        raw_gesture_enum = self._map_raw_to_gesture(raw)

        # -----------------------------------------------------------------
        # Re-arm the palm/clear trigger as soon as the palm pose is left
        # -----------------------------------------------------------------
        if raw != "PALM":
            self._palm_armed = True
            self._palm_hold_start = None

        # -----------------------------------------------------------------
        # OPEN_PALM -> Clear. Requires a short stable hold before firing.
        # -----------------------------------------------------------------
        if raw == "PALM":
            now = time.monotonic()
            if self._palm_hold_start is None:
                self._palm_hold_start = now

            hold_duration = getattr(config, "PALM_HOLD_DURATION", 0.15)
            elapsed = now - self._palm_hold_start
            
            confidence = min(1.0, elapsed / hold_duration)

            if elapsed >= hold_duration and self._palm_armed:
                self._gesture = Gesture.OPEN_PALM
                self._palm_armed = False  # don't fire again until pose is left
            elif not self._palm_armed:
                self._gesture = Gesture.OPEN_PALM
            return confidence

        # Apply state transition logic
        if confirmed_n_frames:
            self._gesture = raw_gesture_enum
        else:
            # Instant start transitions from NONE (Idle) for pointing, pausing, or cycling colors
            if self._gesture == Gesture.NONE and raw in ("POINT", "FIST", "PEACE"):
                self._gesture = raw_gesture_enum

        return confidence

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
        """Euclidean distance between two normalised points."""
        return math.hypot(a[0] - b[0], a[1] - b[1])

    @staticmethod
    def _finger_extended(
        norm: List[Tuple[float, float]],
        tip_idx: int,
        pip_idx: int,
        dip_idx: int,
        wrist_idx: int,
    ) -> bool:
        """
        A finger is "extended" when its tip is farther from the wrist than
        the PIP joint, and farther from the MCP joint than the PIP joint.
        This provides orientation invariance and robustly filters curled fingers.
        """
        tip = norm[tip_idx]
        pip = norm[pip_idx]
        mcp = norm[tip_idx - 3]
        wrist = norm[wrist_idx]

        dist_tip_wrist = math.hypot(tip[0] - wrist[0], tip[1] - wrist[1])
        dist_pip_wrist = math.hypot(pip[0] - wrist[0], pip[1] - wrist[1])

        dist_tip_mcp = math.hypot(tip[0] - mcp[0], tip[1] - mcp[1])
        dist_pip_mcp = math.hypot(pip[0] - mcp[0], pip[1] - mcp[1])

        return (dist_tip_wrist > dist_pip_wrist * 1.1) and (dist_tip_mcp > dist_pip_mcp * 1.05)

    @staticmethod
    def _thumb_extended(norm: List[Tuple[float, float]]) -> bool:
        """
        Thumb extension is check compared to its distance from the wrist.
        """
        tip = norm[THUMB_TIP]
        ip  = norm[THUMB_IP]
        wrist = norm[WRIST]
        
        dist_tip = math.hypot(tip[0] - wrist[0], tip[1] - wrist[1])
        dist_ip  = math.hypot(ip[0] - wrist[0], ip[1] - wrist[1])
        return dist_tip > dist_ip
