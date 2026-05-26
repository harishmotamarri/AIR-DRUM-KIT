"""
╔══════════════════════════════════════════════════════════════╗
║              Visual Effects Engine                          ║
║   Ripples • Particles • Glows • Flash • Beat Visualizer     ║
╚══════════════════════════════════════════════════════════════╝
"""

import cv2
import numpy as np
import pygame
from dataclasses import dataclass, field
from typing import Optional
import math
from config import (Colors, RIPPLE_DURATION, RIPPLE_MAX_RADIUS,
                    PARTICLE_COUNT, PARTICLE_LIFETIME, FLASH_DURATION,
                    GLOW_LAYERS)


# ── Data Classes ─────────────────────────────────────────────

@dataclass
class RippleEffect:
    x: float
    y: float
    color: tuple
    frame: int = 0
    max_frames: int = RIPPLE_DURATION
    max_radius: int = RIPPLE_MAX_RADIUS
    pad_rx: int = 70   # ellipse x radius
    pad_ry: int = 35   # ellipse y radius

    @property
    def alive(self) -> bool:
        return self.frame < self.max_frames

    @property
    def progress(self) -> float:
        return self.frame / self.max_frames


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    color: tuple
    life: int = 0
    max_life: int = PARTICLE_LIFETIME
    size: float = 4.0
    gravity: float = 0.4

    @property
    def alive(self) -> bool:
        return self.life < self.max_life

    @property
    def alpha(self) -> float:
        return 1.0 - (self.life / self.max_life)


@dataclass
class FlashEffect:
    x: float
    y: float
    color: tuple
    frame: int = 0
    max_frames: int = FLASH_DURATION
    intensity: float = 1.0

    @property
    def alive(self) -> bool:
        return self.frame < self.max_frames


@dataclass
class TextPopup:
    text: str
    x: float
    y: float
    color: tuple
    frame: int = 0
    max_frames: int = 45
    scale: float = 1.0

    @property
    def alive(self) -> bool:
        return self.frame < self.max_frames


# ── OpenCV Overlay Helpers ────────────────────────────────────

def draw_circle_alpha(img: np.ndarray, center, radius: int,
                      color: tuple, alpha: float, thickness: int = 2):
    """Draw a circle with alpha blending onto BGR image."""
    if radius < 1:
        return
    overlay = img.copy()
    cv2.circle(overlay, center, radius, color, thickness, cv2.LINE_AA)
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)


def draw_ellipse_alpha(img: np.ndarray, center, axes,
                       color: tuple, alpha: float, thickness: int = 2):
    """Draw an ellipse with alpha blending."""
    if axes[0] < 1 or axes[1] < 1:
        return
    overlay = img.copy()
    cv2.ellipse(overlay, center, axes, 0, 0, 360,
                color, thickness, cv2.LINE_AA)
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)


def draw_glow_circle(img: np.ndarray, center, radius: int,
                     color: tuple, intensity: float = 1.0, layers: int = 4):
    """Multi-layer glow effect."""
    for i in range(layers, 0, -1):
        r_off = i * 8
        a = intensity * (0.15 / i)
        c = tuple(min(255, int(ch * (1 + i * 0.15))) for ch in color)
        draw_circle_alpha(img, center, radius + r_off, c, a, thickness=-1)

    # Core
    draw_circle_alpha(img, center, radius, color, intensity * 0.9, thickness=-1)


# ── Main Effects Manager ──────────────────────────────────────

class EffectsEngine:
    """
    Manages and renders all visual effects.
    Works on both OpenCV frames (camera overlay) and
    pygame surfaces (UI layer).
    """

    def __init__(self):
        self.ripples   : list[RippleEffect] = []
        self.particles : list[Particle]     = []
        self.flashes   : list[FlashEffect]  = []
        self.popups    : list[TextPopup]    = []

        # Per-pad glow intensity (fades out)
        self.pad_glow: dict[str, float] = {}

        # Beat pulse for background
        self.beat_pulse_intensity: float = 0.0

    # ── Spawning ─────────────────────────────────────────────

    def spawn_hit(self, x: float, y: float, color: tuple,
                  pad_rx: int = 70, pad_ry: int = 35,
                  velocity: float = 1.0, pad_name: str = ""):
        """Spawn all effects for a drum hit."""
        # Ripple
        self.ripples.append(RippleEffect(
            x=x, y=y, color=color,
            max_radius=int(RIPPLE_MAX_RADIUS * (0.7 + 0.3 * velocity)),
            pad_rx=pad_rx, pad_ry=pad_ry
        ))

        # Flash
        self.flashes.append(FlashEffect(
            x=x, y=y, color=color,
            intensity=velocity
        ))

        # Particles
        n = int(PARTICLE_COUNT * (0.6 + 0.4 * velocity))
        for i in range(n):
            angle  = math.radians(360 * i / n + np.random.uniform(-15, 15))
            speed  = np.random.uniform(2.5, 8.0) * velocity
            col_var = tuple(min(255, int(c + np.random.randint(-30, 30)))
                            for c in color)
            self.particles.append(Particle(
                x=x + np.random.uniform(-5, 5),
                y=y + np.random.uniform(-5, 5),
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed - 2.0,  # slight upward bias
                color=col_var,
                size=np.random.uniform(2.0, 5.5),
                max_life=int(PARTICLE_LIFETIME * np.random.uniform(0.6, 1.0)),
                gravity=np.random.uniform(0.2, 0.5),
            ))

        # Text popup
        if pad_name:
            self.popups.append(TextPopup(
                text=pad_name,
                x=x, y=y - 40,
                color=color,
                scale=0.8 + 0.4 * velocity,
            ))

        # Pad glow
        self.pad_glow[pad_name] = min(1.0, (self.pad_glow.get(pad_name, 0)
                                             + 0.8 * velocity))

        # Beat pulse
        self.beat_pulse_intensity = min(1.0, self.beat_pulse_intensity + 0.6)

    def spawn_metronome_pulse(self):
        """Visual beat indicator."""
        self.beat_pulse_intensity = min(1.0,
                                        self.beat_pulse_intensity + 0.3)

    # ── Update ────────────────────────────────────────────────

    def update(self):
        """Advance all effects by one frame."""
        # Advance
        for r in self.ripples:   r.frame += 1
        for f in self.flashes:   f.frame += 1
        for p in self.popups:    p.frame += 1
        for p in self.particles:
            p.life += 1
            p.x    += p.vx
            p.y    += p.vy
            p.vy   += p.gravity   # gravity
            p.vx   *= 0.97        # air resistance

        # Decay
        self.beat_pulse_intensity = max(0.0,
                                        self.beat_pulse_intensity - 0.06)
        for k in list(self.pad_glow.keys()):
            self.pad_glow[k] = max(0.0, self.pad_glow[k] - 0.05)

        # Cull dead effects
        self.ripples   = [r for r in self.ripples   if r.alive]
        self.flashes   = [f for f in self.flashes   if f.alive]
        self.popups    = [p for p in self.popups    if p.alive]
        self.particles = [p for p in self.particles if p.alive]

    # ── Render on OpenCV Frame ────────────────────────────────

    def render_on_frame(self, frame: np.ndarray):
        """Draw all effects on the CV2 BGR frame."""
        # Particles first (bottom layer)
        self._render_particles_cv(frame)
        # Ripples
        self._render_ripples_cv(frame)
        # Flashes
        self._render_flashes_cv(frame)

    def _render_ripples_cv(self, frame: np.ndarray):
        for r in self.ripples:
            prog   = r.progress
            ease   = 1.0 - (1.0 - prog) ** 2   # ease-out
            radius = int(r.max_radius * ease)
            alpha  = (1.0 - prog) * 0.85

            cx, cy = int(r.x), int(r.y)

            # Multi-ring ripple
            for ring in range(3):
                ring_prog  = max(0, prog - ring * 0.15)
                ring_r     = int(radius * (1.0 - ring * 0.18))
                ring_alpha = alpha * (1.0 - ring * 0.3)
                if ring_r > 5:
                    draw_ellipse_alpha(
                        frame, (cx, cy),
                        (ring_r, max(1, int(ring_r * r.pad_ry / max(r.pad_rx, 1)))),
                        r.color, ring_alpha,
                        thickness=max(1, 3 - ring)
                    )

    def _render_particles_cv(self, frame: np.ndarray):
        h, w = frame.shape[:2]
        for p in self.particles:
            if not (0 < p.x < w and 0 < p.y < h):
                continue
            alpha  = p.alpha ** 1.5
            r      = max(1, int(p.size * p.alpha))
            center = (int(p.x), int(p.y))

            # Glow
            glow_c = tuple(min(255, int(c * 1.3)) for c in p.color)
            draw_circle_alpha(frame, center, r + 2, glow_c, alpha * 0.3, -1)
            draw_circle_alpha(frame, center, r,     p.color, alpha * 0.85, -1)

    def _render_flashes_cv(self, frame: np.ndarray):
        for f in self.flashes:
            prog   = f.frame / f.max_frames
            alpha  = (1.0 - prog) * f.intensity * 0.7
            radius = int(50 + prog * 30)
            draw_glow_circle(frame, (int(f.x), int(f.y)),
                             radius, f.color, alpha, layers=GLOW_LAYERS)

    # ── Render on Pygame Surface ──────────────────────────────

    def render_on_pygame(self, surface: pygame.Surface,
                         font_sm: pygame.font.Font):
        """Render popups and beat pulse on pygame surface."""
        self._render_popups_pygame(surface, font_sm)

    def _render_popups_pygame(self, surface: pygame.Surface,
                               font: pygame.font.Font):
        for p in self.popups:
            prog = p.frame / p.max_frames
            # Rise animation
            y_off = -prog * 50
            # Scale punch
            scale = 1.0 + 0.4 * (1.0 - prog) ** 3

            alpha = int(255 * (1.0 - prog ** 1.5))
            col   = (*p.color, alpha)

            text_surf = font.render(p.text, True, p.color)
            # Scale
            new_w = int(text_surf.get_width()  * scale)
            new_h = int(text_surf.get_height() * scale)
            if new_w > 0 and new_h > 0:
                text_surf = pygame.transform.smoothscale(
                    text_surf, (new_w, new_h))

            # Alpha
            text_surf.set_alpha(alpha)

            rect = text_surf.get_rect(
                center=(int(p.x), int(p.y + y_off))
            )
            surface.blit(text_surf, rect)