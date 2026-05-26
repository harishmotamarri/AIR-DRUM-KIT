"""
╔══════════════════════════════════════════════════════════════╗
║              MediaPipe Hand Tracking Engine                 ║
║    Tracks wrists + fingertips, computes velocity, detects   ║
║    downward strikes for drum triggering                     ║
╚══════════════════════════════════════════════════════════════╝
"""

import cv2
import mediapipe as mp
import numpy as np
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
from config import (MAX_HANDS, DETECTION_CONF, TRACKING_CONF,
                    VELOCITY_SMOOTHING, CAMERA_WIDTH, CAMERA_HEIGHT,
                    HIT_VELOCITY_THRESH)


# MediaPipe landmark indices
LM = mp.solutions.hands.HandLandmark


@dataclass
class FingerTip:
    """Data for a single tracked tip/wrist point."""
    landmark_id : int
    x           : float = 0.0    # pixel x
    y           : float = 0.0    # pixel y
    vx          : float = 0.0    # velocity x (px/frame)
    vy          : float = 0.0    # velocity y (px/frame)
    speed       : float = 0.0    # magnitude
    is_striking : bool  = False  # downward strike detected


@dataclass
class HandState:
    """Full state snapshot for one hand."""
    hand_id      : int
    handedness   : str                    # "Left" / "Right"
    landmarks    : list                   # raw normalized
    pixel_landmarks: list                 # (x, y) in pixels

    # Key tracked points
    wrist        : FingerTip = field(default_factory=lambda: FingerTip(0))
    index_tip    : FingerTip = field(default_factory=lambda: FingerTip(8))
    middle_tip   : FingerTip = field(default_factory=lambda: FingerTip(12))
    ring_tip     : FingerTip = field(default_factory=lambda: FingerTip(16))
    pinky_tip    : FingerTip = field(default_factory=lambda: FingerTip(20))
    thumb_tip    : FingerTip = field(default_factory=lambda: FingerTip(4))

    # Strike point (primary trigger — index tip or wrist)
    strike_point : FingerTip = field(default_factory=lambda: FingerTip(8))
    is_fist      : bool      = False   # Fist = wrist used as beater
    confidence   : float     = 1.0


class VelocityFilter:
    """Smoothed velocity tracker using circular buffer."""

    def __init__(self, size: int = VELOCITY_SMOOTHING):
        self._hist = deque(maxlen=size)
        self._last_pos: Optional[tuple] = None

    def update(self, x: float, y: float) -> tuple[float, float, float]:
        """Returns (vx, vy, speed)."""
        if self._last_pos is None:
            self._last_pos = (x, y)
            return 0.0, 0.0, 0.0

        raw_vx = x - self._last_pos[0]
        raw_vy = y - self._last_pos[1]
        self._hist.append((raw_vx, raw_vy))
        self._last_pos = (x, y)

        if len(self._hist) < 2:
            return raw_vx, raw_vy, np.hypot(raw_vx, raw_vy)

        vx = np.mean([v[0] for v in self._hist])
        vy = np.mean([v[1] for v in self._hist])
        return float(vx), float(vy), float(np.hypot(vx, vy))


class HandTracker:
    """
    Wraps MediaPipe Hands with velocity tracking and strike detection.
    Provides clean per-frame hand state objects.
    """

    """Enhanced tracker with per-finger tracking."""

    FINGER_TIPS = {
        "thumb":  4,
        "index":  8,
        "middle": 12,
        "ring":   16,
        "pinky":  20,
    }

    TRACKED_LANDMARKS = [
        (LM.WRIST,           "wrist"     ),
        (LM.INDEX_FINGER_TIP,"index_tip" ),
        (LM.MIDDLE_FINGER_TIP,"middle_tip"),
        (LM.RING_FINGER_TIP, "ring_tip"  ),
        (LM.PINKY_TIP,       "pinky_tip" ),
        (LM.THUMB_TIP,       "thumb_tip" ),
    ]

    def __init__(self):
        self._mp_hands = mp.solutions.hands
        self._hands = self._mp_hands.Hands(
            static_image_mode        = False,
            max_num_hands            = MAX_HANDS,
            min_detection_confidence = DETECTION_CONF,
            min_tracking_confidence  = TRACKING_CONF,
        )
        self._drawing = mp.solutions.drawing_utils
        self._drawing_styles = mp.solutions.drawing_styles

        # Velocity filters: key = (hand_id, landmark_id)
        self._vel_filters: dict[tuple, VelocityFilter] = {}

        # Strike state: cooldown tracking
        self._strike_cooldown: dict[tuple, int] = {}

        # Previous y positions for direction detection
        self._prev_vy: dict[tuple, float] = {}

        self.frame_count = 0

    def _get_vel_filter(self, hand_id: int, lm_id: int) -> VelocityFilter:
        key = (hand_id, lm_id)
        if key not in self._vel_filters:
            self._vel_filters[key] = VelocityFilter()
        return self._vel_filters[key]

    def _detect_fist(self, landmarks_norm, hand_label: str) -> bool:
        """Detect closed fist by checking finger curl."""
        try:
            tips  = [8, 12, 16, 20]
            pips  = [6, 10, 14, 18]
            curled = 0
            for tip, pip in zip(tips, pips):
                if landmarks_norm[tip].y > landmarks_norm[pip].y:
                    curled += 1
            return curled >= 3
        except Exception:
            return False

    def process(self, frame_bgr: np.ndarray) -> list[HandState]:
        """Process frame and return hand states with all fingertip velocities."""
        self.frame_count += 1
        h, w = frame_bgr.shape[:2]

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = self._hands.process(rgb)
        rgb.flags.writeable = True

        hand_states: list[HandState] = []

        if not results.multi_hand_landmarks:
            return hand_states

        for hand_idx, (lm_obj, handedness_obj) in enumerate(
            zip(results.multi_hand_landmarks, results.multi_handedness)
        ):
            label = handedness_obj.classification[0].label
            score = handedness_obj.classification[0].score

            px_lm = [(int(lm.x * w), int(lm.y * h))
                     for lm in lm_obj.landmark]

            state = HandState(
                hand_id=hand_idx,
                handedness=label,
                landmarks=lm_obj.landmark,
                pixel_landmarks=px_lm,
                confidence=score,
                is_fist=self._detect_fist(lm_obj.landmark, label),
            )

            # Track all fingertips with velocity
            for lm_id, attr_name in self.TRACKED_LANDMARKS:
                lm = lm_obj.landmark[lm_id]
                px = lm.x * w
                py = lm.y * h

                vel = self._get_vel_filter(hand_idx, lm_id)
                vx, vy, spd = vel.update(px, py)

                tip = FingerTip(
                    landmark_id=lm_id,
                    x=px, y=py,
                    vx=vx, vy=vy,
                    speed=spd,
                    is_striking=(vy > 0 and spd > HIT_VELOCITY_THRESH * 0.7),
                )
                setattr(state, attr_name, tip)

            all_tips = [
                state.index_tip, state.middle_tip,
                state.ring_tip, state.pinky_tip, state.thumb_tip,
            ]
            striking_tips = [t for t in all_tips if t.vy > 0]

            if striking_tips:
                state.strike_point = max(striking_tips, key=lambda t: t.speed)
            else:
                state.strike_point = max(all_tips, key=lambda t: t.speed)

            hand_states.append(state)

        return hand_states

    def get_all_strike_points(self, hand_states: list[HandState]) -> list[tuple]:
        """
        Get ALL active fingertips from both hands for multi-finger drumming.
        Returns: [(x, y, speed, vy, hand_label, finger_name), ...]
        """
        points = []

        for state in hand_states:
            tips = [
                (state.thumb_tip, "thumb"),
                (state.index_tip, "index"),
                (state.middle_tip, "middle"),
                (state.ring_tip, "ring"),
                (state.pinky_tip, "pinky"),
            ]

            for tip, finger in tips:
                if tip.speed > HIT_VELOCITY_THRESH * 0.5:
                    hand_prefix = "left" if state.handedness == "Left" else "right"
                    points.append((
                        tip.x, tip.y,
                        tip.speed, tip.vy,
                        state.handedness,
                        f"{hand_prefix}_{finger}",
                        state.hand_id,
                    ))

        return points

    def draw_skeleton(self, frame: np.ndarray,
                      hand_states: list[HandState]) -> np.ndarray:
        """
        Draw hand skeleton on frame with custom styling.
        Returns modified frame.
        """
        for state in hand_states:
            # Reconstruct landmark list for drawing
            lm_list = type('obj', (object,), {
                'landmark': state.landmarks
            })()

            # Custom connection drawing
            for connection in self._mp_hands.HAND_CONNECTIONS:
                p1 = connection[0]
                p2 = connection[1]
                if p1 < len(state.pixel_landmarks) and \
                   p2 < len(state.pixel_landmarks):
                    x1, y1 = state.pixel_landmarks[p1]
                    x2, y2 = state.pixel_landmarks[p2]

                    # Color by hand
                    color = (0, 180, 255) if state.handedness == "Right" \
                            else (255, 140, 0)
                    cv2.line(frame, (x1,y1), (x2,y2), color, 2, cv2.LINE_AA)

            # Draw landmark dots
            for i, (px, py) in enumerate(state.pixel_landmarks):
                r     = 6 if i in [4,8,12,16,20,0] else 3
                color = (255, 255, 255)
                cv2.circle(frame, (px, py), r+1, (0,0,0), -1)
                cv2.circle(frame, (px, py), r,   color,   -1)

            # Strike point highlight
            sp = state.strike_point
            sx, sy = int(sp.x), int(sp.y)
            intensity = min(1.0, sp.speed / 30)
            ring_col  = (int(intensity*255), int((1-intensity)*200), 50)
            cv2.circle(frame, (sx, sy), 14, ring_col, 2, cv2.LINE_AA)
            cv2.circle(frame, (sx, sy), 4,  (255,255,255), -1)

        return frame

    def release(self):
        self._hands.close()