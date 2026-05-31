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
from config import (PADS, FINGER_LANDMARKS, HIT_VELOCITY_THRESH, COOLDOWN_FRAMES,
                    WINDOW_WIDTH, WINDOW_HEIGHT)
from hand_tracker import HandState, FingerTip


@dataclass
class DrumPad:
    """Extended with finger assignment."""
    name       : str
    label      : str
    cx         : int
    cy         : int
    rx         : int
    ry         : int
    shape      : str
    color      : tuple
    sample     : str
    sound_key  : str
    key        : str | None = None
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
        """Create pads from normalized canvas coordinates."""
        for cfg in PADS:
            cx = int(cfg.x * WINDOW_WIDTH)
            cy = int(cfg.y * WINDOW_HEIGHT)
            rx = max(10, int(cfg.w * WINDOW_WIDTH * 0.5))
            ry = max(10, int(cfg.h * WINDOW_HEIGHT * 0.5))
            self.pads.append(DrumPad(
                name=cfg.id,
                label=cfg.label,
                cx=cx, cy=cy,
                rx=rx, ry=ry,
                shape=cfg.shape,
                color=tuple(int(cfg.color[i:i+2], 16) for i in (1, 3, 5)),
                sample=cfg.sample,
                sound_key=cfg.id,
                key=cfg.key,
            ))
        print(f"🥁 {len(self.pads)} drum pads initialized")

    def register_callback(self, fn: Callable):
        """Register a function to call on every hit: fn(HitEvent)."""
        self._callbacks.append(fn)

    def update(self, hand_states: list[HandState], enabled: bool = True) -> list[HitEvent]:
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

        if not enabled:
            return hits

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

    def trigger_pad_by_key(self, key: str, velocity: float = 1.0, enabled: bool = True) -> HitEvent | None:
        """Programmatically trigger a pad by its configured keyboard key.

        Returns the generated HitEvent or None if no pad matched or pad is cooling.
        """
        if not key or not enabled:
            return None
        k = key.upper()
        for pad in self.pads:
            if pad.key and pad.key.upper() == k:
                if pad.is_cooling:
                    return None

                # Apply basic velocity bounds
                vel = max(0.2, min(1.0, float(velocity)))

                # Update pad state
                pad.hit_intensity = 1.0
                pad.cooldown_left = COOLDOWN_FRAMES
                pad.total_hits += 1
                pad.last_hit_time = time.time()

                event = HitEvent(
                    pad=pad,
                    x=float(pad.cx),
                    y=float(pad.cy),
                    velocity=vel,
                    raw_speed=0.0,
                    hand_id=-1,
                    handedness="Keyboard",
                    timestamp=time.time(),
                )

                # Fire callbacks
                for cb in self._callbacks:
                    try:
                        cb(event)
                    except Exception as e:
                        print(f"Callback error: {e}")

                self.hit_count += 1
                return event
        return None
