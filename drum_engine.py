"""
╔══════════════════════════════════════════════════════════════╗
║                     Core Drum Engine                        ║
║   Hit detection • Pad management • Trigger routing          ║
╚══════════════════════════════════════════════════════════════╝
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional, Callable
import time
from config import (DRUM_PADS, FINGER_LANDMARKS, HIT_VELOCITY_THRESH, COOLDOWN_FRAMES,
                    WINDOW_WIDTH, WINDOW_HEIGHT, HEADER_HEIGHT,
                    FOOTER_HEIGHT, Colors)
from hand_tracker import HandState, FingerTip


@dataclass
class DrumPad:
    """Extended with finger assignment."""
    name       : str
    cx         : int
    cy         : int
    rx         : int
    ry         : int
    color      : tuple
    sound_key  : str
    finger_zone: str = "any"

    # State
    hit_intensity : float = 0.0    # 0–1, decays each frame
    cooldown_left : int   = 0
    total_hits    : int   = 0
    last_hit_time : float = 0.0
    last_hit_by   : str    = ""

    @property
    def is_cooling(self) -> bool:
        return self.cooldown_left > 0

    def can_be_hit_by(self, finger_id: str) -> bool:
        """Check if this finger can trigger this pad."""
        if self.finger_zone == "any":
            return True
        finger_suffix = self.finger_zone.split('_')[-1]
        return finger_id == self.finger_zone or (
            finger_suffix in FINGER_LANDMARKS and finger_id.endswith(finger_suffix)
        )

    def contains(self, x: float, y: float) -> bool:
        """Elliptical hit detection."""
        dx = (x - self.cx) / self.rx
        dy = (y - self.cy) / self.ry
        return (dx * dx + dy * dy) <= 1.0

    def distance_normalized(self, x: float, y: float) -> float:
        """0.0 = center, 1.0 = edge."""
        dx = (x - self.cx) / self.rx
        dy = (y - self.cy) / self.ry
        return min(1.0, np.hypot(dx, dy))


@dataclass
class HitEvent:
    """A confirmed drum hit."""
    pad          : DrumPad
    x            : float
    y            : float
    velocity     : float     # normalized 0–1
    raw_speed    : float     # pixel/frame
    hand_id      : int
    handedness   : str
    timestamp    : float


class DrumEngine:
    """
    Manages drum pads, processes hand states,
    fires hit events with velocity.
    """

    def __init__(self):
        self.pads    : list[DrumPad] = []
        self._cooldowns: dict[str, int] = {}
        self._callbacks: list[Callable] = []
        self._build_pads()
        self.hit_count = 0

    def _build_pads(self):
        """Create pads from config with finger zones."""
        usable_h = WINDOW_HEIGHT - HEADER_HEIGHT - FOOTER_HEIGHT
        for cfg in DRUM_PADS:
            if len(cfg) == 7:
                name, cx_n, cy_n, rx, ry, color, skey = cfg
                finger = "any"
            else:
                name, cx_n, cy_n, rx, ry, color, skey, finger = cfg

            cx = int(cx_n * WINDOW_WIDTH)
            cy = int(HEADER_HEIGHT + cy_n * usable_h)
            self.pads.append(DrumPad(
                name=name, cx=cx, cy=cy,
                rx=rx, ry=ry,
                color=color, sound_key=skey,
                finger_zone=finger,
            ))
        print(f"🥁 {len(self.pads)} drum pads initialized")

    def register_callback(self, fn: Callable):
        """Register a function to call on every hit: fn(HitEvent)."""
        self._callbacks.append(fn)

    def update(self, hand_states: list[HandState]) -> list[HitEvent]:
        """
        Process all hand states, detect hits, fire callbacks.
        Returns list of HitEvents this frame.
        """
        hits = []

        # Decay
        for pad in self.pads:
            pad.hit_intensity = max(0.0, pad.hit_intensity - 0.08)
            if pad.cooldown_left > 0:
                pad.cooldown_left -= 1

        for state in hand_states:
            sp = state.strike_point
            speed = sp.speed
            vy = sp.vy   # downward velocity is positive

            # Only trigger on downward + fast movement
            if speed < HIT_VELOCITY_THRESH or vy < 0:
                continue

            for pad in self.pads:
                if pad.is_cooling:
                    continue

                if pad.contains(sp.x, sp.y):
                    # Velocity = speed normalized (capped at 2× threshold)
                    vel = min(1.0, (speed - HIT_VELOCITY_THRESH) /
                                    (HIT_VELOCITY_THRESH * 1.5))
                    vel = max(0.2, vel)

                    # Distance factor (center = loudest)
                    dist = pad.distance_normalized(sp.x, sp.y)
                    vel *= (1.0 - dist * 0.3)

                    # Update pad state
                    pad.hit_intensity  = 1.0
                    pad.cooldown_left  = COOLDOWN_FRAMES
                    pad.total_hits    += 1
                    pad.last_hit_time  = time.time()

                    event = HitEvent(
                        pad=pad,
                        x=sp.x,
                        y=sp.y,
                        velocity=vel,
                        raw_speed=speed,
                        hand_id=state.hand_id,
                        handedness=state.handedness,
                        timestamp=time.time(),
                    )
                    hits.append(event)
                    self.hit_count += 1

                    for cb in self._callbacks:
                        try:
                            cb(event)
                        except Exception as e:
                            print(f"Callback error: {e}")

                    break   # One pad per hand per frame

        return hits

    def get_pad_by_name(self, name: str) -> Optional[DrumPad]:
        for p in self.pads:
            if p.name == name:
                return p
        return None

    def get_pad_by_sound(self, key: str) -> Optional[DrumPad]:
        for p in self.pads:
            if p.sound_key == key:
                return p
        return None

    def reset_stats(self):
        for p in self.pads:
            p.total_hits = 0
