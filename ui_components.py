"""
╔══════════════════════════════════════════════════════════════╗
║                    UI Components Library                    ║
║   Header • Footer • Beat Grid • Stats • BPM Dial • Hints    ║
╚══════════════════════════════════════════════════════════════╝
"""

import pygame
import math
import time
from config import (Colors, WINDOW_WIDTH, WINDOW_HEIGHT,
                    HEADER_HEIGHT, FOOTER_HEIGHT, DRUM_PADS,
                    TUTORIAL_TIMEOUT)


def lerp_color(c1: tuple, c2: tuple, t: float) -> tuple:
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def glow_rect(surface: pygame.Surface, rect: pygame.Rect,
              color: tuple, radius: int = 8, alpha: int = 60):
    """Draw a glowing rounded rectangle."""
    glow_surf = pygame.Surface(
        (rect.width + radius*4, rect.height + radius*4),
        pygame.SRCALPHA
    )
    for i in range(radius, 0, -1):
        a = int(alpha * i / radius)
        r = (*color, a)
        pygame.draw.rect(glow_surf, r,
                         (radius*2 - i, radius*2 - i,
                          rect.width + i*2, rect.height + i*2),
                         border_radius=12)
    surface.blit(glow_surf, (rect.x - radius*2, rect.y - radius*2))


class FontManager:
    """Singleton font manager."""
    _instance = None
    fonts: dict = {}

    @classmethod
    def get(cls) -> "FontManager":
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._init()
        return cls._instance

    def _init(self):
        pygame.font.init()
        # Try to use a good font, fall back gracefully
        font_names = ["Segoe UI", "SF Pro Display", "Helvetica Neue",
                      "Arial", "DejaVu Sans", None]
        chosen = None
        for fn in font_names:
            if fn is None or fn in pygame.font.get_fonts():
                chosen = fn
                break

        self.fonts = {
            "title"  : pygame.font.SysFont(chosen, 28, bold=True),
            "heading": pygame.font.SysFont(chosen, 22, bold=True),
            "body"   : pygame.font.SysFont(chosen, 18),
            "small"  : pygame.font.SysFont(chosen, 14),
            "tiny"   : pygame.font.SysFont(chosen, 12),
            "big"    : pygame.font.SysFont(chosen, 36, bold=True),
            "pad"    : pygame.font.SysFont(chosen, 13, bold=True),
        }

    def __getitem__(self, key: str) -> pygame.font.Font:
        return self.fonts.get(key, self.fonts["body"])


class Header:
    """Top status bar."""

    def __init__(self):
        self.fm = FontManager.get()
        self._pulse = 0.0
        self._start = time.time()

    def render(self, surface: pygame.Surface, fps: float,
               state: str, bpm: float, hit_count: int,
               beat_pulse: float):
        h    = HEADER_HEIGHT
        w    = WINDOW_WIDTH

        # Background
        bg_rect = pygame.Rect(0, 0, w, h)
        pygame.draw.rect(surface, Colors.BG_DARK, bg_rect)
        # Bottom line
        pygame.draw.line(surface, Colors.GRAY_DARK,
                         (0, h-1), (w, h-1), 1)

        # ── Logo / Title ──────────────────────────────────────
        t = time.time() - self._start
        pulse_col = lerp_color(Colors.ACCENT_BLUE, Colors.ACCENT_PURPLE,
                               (math.sin(t * 1.5) + 1) / 2)
        title = self.fm["title"].render("🥁  AIR DRUM KIT", True, pulse_col)
        surface.blit(title, (20, (h - title.get_height()) // 2))

        # ── State Badge ───────────────────────────────────────
        state_cfg = {
            "idle"      : ("READY",     Colors.GRAY_MID),
            "recording" : ("⏺ REC",     Colors.RED_HOT),
            "playing"   : ("▶ LOOP",    Colors.GREEN_NEON),
        }
        s_text, s_col = state_cfg.get(state, ("?", Colors.WHITE))

        badge_surf = self.fm["heading"].render(s_text, True, s_col)
        bx = 280
        by = (h - badge_surf.get_height()) // 2

        # Badge bg
        badge_rect = pygame.Rect(bx - 8, by - 4,
                                 badge_surf.get_width() + 16, 
                                 badge_surf.get_height() + 8)
        if state == "recording":
            # Blinking background
            alpha = int(128 + 127 * math.sin(t * 8))
            bg    = pygame.Surface(badge_rect.size, pygame.SRCALPHA)
            bg.fill((*Colors.RED_HOT, alpha // 3))
            surface.blit(bg, badge_rect.topleft)
        pygame.draw.rect(surface, s_col, badge_rect,
                         1, border_radius=6)
        surface.blit(badge_surf, (bx, by))

        # ── BPM ───────────────────────────────────────────────
        bpm_text = self.fm["heading"].render(f"♩ {bpm:.0f} BPM",
                                             True, Colors.ACCENT_CYAN)
        surface.blit(bpm_text, (420, (h - bpm_text.get_height()) // 2))

        # ── Hit Counter ───────────────────────────────────────
        hit_text = self.fm["body"].render(f"HITS  {hit_count:04d}",
                                          True, Colors.GRAY_LIGHT)
        surface.blit(hit_text, (580, (h - hit_text.get_height()) // 2))

        # ── Beat Pulse Indicator ──────────────────────────────
        pulse_x = w - 200
        for i in range(8):
            bx2 = pulse_x + i * 18
            by2 = h // 2 - 6
            intensity = max(0.0, beat_pulse - i * 0.12)
            col = lerp_color(Colors.GRAY_DARK, Colors.ACCENT_CYAN, intensity)
            pygame.draw.rect(surface, col,
                             (bx2, by2, 12, 12), border_radius=3)

        # ── FPS ───────────────────────────────────────────────
        fps_text = self.fm["tiny"].render(f"FPS {fps:.0f}",
                                          True, Colors.GRAY_MID)
        surface.blit(fps_text, (w - 65, h - fps_text.get_height() - 4))


class Footer:
    """Bottom control hints bar."""

    HINTS = [
        ("SPACE",  "Record/Stop"),
        ("P",      "Play/Stop Loop"),
        ("↑↓",     "BPM +/-"),
        ("S",      "Save Beat"),
        ("R",      "Reset Stats"),
        ("ESC",    "Quit"),
    ]

    def __init__(self):
        self.fm = FontManager.get()

    def render(self, surface: pygame.Surface):
        y   = WINDOW_HEIGHT - FOOTER_HEIGHT
        w   = WINDOW_WIDTH
        h   = FOOTER_HEIGHT

        # Background
        pygame.draw.rect(surface, Colors.BG_DARK,
                         (0, y, w, h))
        pygame.draw.line(surface, Colors.GRAY_DARK,
                         (0, y), (w, y), 1)

        # Hints
        x_off = 20
        for key, desc in self.HINTS:
            # Key badge
            key_surf = self.fm["small"].render(key, True, Colors.BG_DARK)
            key_rect = pygame.Rect(x_off - 4,
                                   y + (h - key_surf.get_height()) // 2 - 2,
                                   key_surf.get_width() + 8,
                                   key_surf.get_height() + 4)
            pygame.draw.rect(surface, Colors.ACCENT_CYAN,
                             key_rect, border_radius=4)
            surface.blit(key_surf, (x_off,
                                    y + (h - key_surf.get_height()) // 2))
            x_off += key_rect.width + 4

            # Description
            desc_surf = self.fm["small"].render(desc, True, Colors.GRAY_MID)
            surface.blit(desc_surf,
                         (x_off,
                          y + (h - desc_surf.get_height()) // 2))
            x_off += desc_surf.get_width() + 24

            if x_off > w - 100:
                break


class BeatGridUI:
    """
    Compact sequencer grid showing recorded pattern.
    Shows 16 steps × N drum tracks.
    """

    TRACK_KEYS = ["kick", "snare", "hihat", "openhat",
                  "crash", "ride", "tom1", "tom2", "clap"]
    TRACK_NAMES = ["KICK", "SNARE", "HI-HAT", "OPEN HAT",
                   "CRASH", "RIDE", "TOM 1", "TOM 2", "CLAP"]
    TRACK_COLORS = [
        Colors.RED_HOT, Colors.ACCENT_CYAN, Colors.YELLOW_NEON,
        Colors.ORANGE,  Colors.ACCENT_PURPLE, Colors.GREEN_NEON,
        (255, 120, 60), (255, 80, 140), Colors.GREEN_NEON,
    ]

    def __init__(self):
        self.fm = FontManager.get()
        self.x  = 20
        self.y  = HEADER_HEIGHT + 10
        self.step_w = 18
        self.step_h = 11
        self.track_h = 14
        self.label_w = 60
        self.steps  = 16

    def render(self, surface: pygame.Surface, grid_data: dict,
               is_recording: bool, is_playing: bool):
        if not grid_data:
            return

        filled  = grid_data.get("filled", {})
        cur_step = grid_data.get("current_step", -1)
        steps   = grid_data.get("steps", 16)
        use_steps = min(steps, self.steps)

        # Background panel
        panel_w = self.label_w + use_steps * self.step_w + 20
        panel_h = len(self.TRACK_KEYS) * self.track_h + 20
        panel   = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((8, 10, 20, 200))
        pygame.draw.rect(panel, Colors.GRAY_DARK,
                         (0, 0, panel_w, panel_h), 1, border_radius=6)
        surface.blit(panel, (self.x, self.y))

        for ti, (tk, tn, tc) in enumerate(zip(
                self.TRACK_KEYS, self.TRACK_NAMES, self.TRACK_COLORS)):

            ty = self.y + 10 + ti * self.track_h

            # Track label
            label = self.fm["tiny"].render(tn[:6], True, Colors.GRAY_MID)
            surface.blit(label, (self.x + 4,
                                  ty + (self.track_h - label.get_height()) // 2))

            track_filled = filled.get(tk, set())

            for si in range(use_steps):
                sx = self.x + self.label_w + si * self.step_w

                is_cur  = (si == cur_step % use_steps) and \
                          (is_playing or is_recording)
                is_hit  = si in track_filled

                # Cell background
                if is_cur:
                    cell_col = lerp_color(Colors.BG_MID,
                                          Colors.ACCENT_CYAN, 0.5)
                elif si % 4 == 0:
                    cell_col = (20, 22, 35)
                else:
                    cell_col = Colors.BG_DARK

                cell_r = pygame.Rect(sx + 1, ty + 1,
                                     self.step_w - 2, self.track_h - 2)
                pygame.draw.rect(surface, cell_col, cell_r, border_radius=2)

                # Hit indicator
                if is_hit:
                    hit_col = lerp_color(tc, Colors.WHITE,
                                          0.3 if is_cur else 0.0)
                    inner = pygame.Rect(sx + 2, ty + 2,
                                        self.step_w - 4, self.track_h - 4)
                    pygame.draw.rect(surface, hit_col, inner,
                                     border_radius=2)


class PadOverlay:
    """Beautiful, responsive drum pad visualization."""

    def __init__(self, pads):
        self.pads = pads
        self.fm = FontManager.get()
        self._pulse_phase = 0

        # Pre-render static elements
        self._pad_surfaces = {}
        self._create_pad_surfaces()

    def _create_pad_surfaces(self):
        """Pre-render pad base surfaces for performance."""
        for pad in self.pads:
            size = (pad.rx * 2 + 80, pad.ry * 2 + 80)
            self._pad_surfaces[pad.name] = pygame.Surface(size, pygame.SRCALPHA)

    def render(self, surface: pygame.Surface, hand_states: list = None):
        """Render all pads with dynamic effects."""
        self._pulse_phase += 0.08

        # Get active finger positions for proximity effects
        finger_positions = []
        if hand_states:
            for state in hand_states:
                for tip in [state.index_tip, state.middle_tip,
                           state.ring_tip, state.pinky_tip, state.thumb_tip]:
                    finger_positions.append((tip.x, tip.y, tip.speed))

        for pad in self.pads:
            self._render_pad(surface, pad, finger_positions)

    def _render_pad(self, surface: pygame.Surface, pad, fingers: list):
        """Render single pad with all effects."""
        intensity = pad.hit_intensity

        # Check finger proximity for hover effect
        hover_intensity = 0.0
        for (fx, fy, fspeed) in fingers:
            dist = pad.distance_normalized(fx, fy)
            if dist < 1.5:
                hover_intensity = max(hover_intensity, (1.5 - dist) / 1.5)

        pad_surf = pygame.Surface(
            (pad.rx * 2 + 80, pad.ry * 2 + 80), pygame.SRCALPHA
        )

        center = (pad.rx + 40, pad.ry + 40)

        # Layer 1: Outer glow rings
        glow_intensity = intensity * 0.6 + hover_intensity * 0.3
        if glow_intensity > 0.05:
            for i in range(5, 0, -1):
                ring_r_x = pad.rx + i * 12
                ring_r_y = pad.ry + i * 6
                alpha = int(glow_intensity * 60 * (6 - i) / 5)
                glow_col = (*pad.color, alpha)
                pygame.draw.ellipse(
                    pad_surf, glow_col,
                    (center[0] - ring_r_x, center[1] - ring_r_y,
                     ring_r_x * 2, ring_r_y * 2)
                )

        # Layer 2: Base fill
        base_alpha = 45 + int(intensity * 120) + int(hover_intensity * 40)
        fill_col = tuple(min(255, int(c * (0.6 + intensity * 0.4)))
                        for c in pad.color)
        pygame.draw.ellipse(
            pad_surf, (*fill_col, base_alpha),
            (center[0] - pad.rx, center[1] - pad.ry,
             pad.rx * 2, pad.ry * 2)
        )

        # Layer 3: Inner gradient
        if intensity > 0.1:
            inner_rx = int(pad.rx * 0.6)
            inner_ry = int(pad.ry * 0.6)
            inner_alpha = int(intensity * 180)
            bright_col = tuple(min(255, c + 60) for c in pad.color)
            pygame.draw.ellipse(
                pad_surf, (*bright_col, inner_alpha),
                (center[0] - inner_rx, center[1] - inner_ry,
                 inner_rx * 2, inner_ry * 2)
            )

        # Layer 4: Border
        border_alpha = 140 + int(intensity * 115)
        border_width = 2 + int(intensity * 2)
        border_col = tuple(min(255, c + int(intensity * 50)) for c in pad.color)
        pygame.draw.ellipse(
            pad_surf, (*border_col, border_alpha),
            (center[0] - pad.rx, center[1] - pad.ry,
             pad.rx * 2, pad.ry * 2),
            border_width
        )

        # Layer 5: Hit flash
        if intensity > 0.7:
            flash_alpha = int((intensity - 0.7) / 0.3 * 200)
            pygame.draw.ellipse(
                pad_surf, (255, 255, 255, flash_alpha),
                (center[0] - pad.rx + 5, center[1] - pad.ry + 3,
                 pad.rx * 2 - 10, pad.ry * 2 - 6)
            )

        # Blit pad surface
        surface.blit(pad_surf, (pad.cx - pad.rx - 40, pad.cy - pad.ry - 40))

        # Label
        label_alpha = 160 + int(intensity * 95)
        label_col = lerp_color(Colors.GRAY_MID, Colors.WHITE, intensity)

        # Clean name (remove L-/R- prefix for display)
        display_name = pad.name.replace("L-", "").replace("R-", "").replace("-C", "")

        # Shadow
        shadow = self.fm["pad"].render(display_name, True, (0, 0, 0))
        shadow.set_alpha(label_alpha)
        surface.blit(shadow,
                    (pad.cx - shadow.get_width() // 2 + 1,
                     pad.cy - shadow.get_height() // 2 + 1))

        # Label
        label = self.fm["pad"].render(display_name, True, label_col)
        label.set_alpha(label_alpha)
        surface.blit(label,
                    (pad.cx - label.get_width() // 2,
                     pad.cy - label.get_height() // 2))

        # Hit counter (small)
        if pad.total_hits > 0:
            count_text = self.fm["tiny"].render(str(pad.total_hits), True, pad.color)
            count_text.set_alpha(180)
            surface.blit(count_text,
                        (pad.cx + pad.rx - 8, pad.cy - pad.ry - 2))


# ═══════════════════════════════════════════════════════════════
#   TUTORIAL SYSTEM
# ═══════════════════════════════════════════════════════════════

class TutorialOverlay:
    """Interactive first-time tutorial."""

    STEPS = [
        {
            "title": "👋 Welcome to Air Drums!",
            "text": "Wave your hands to begin",
            "condition": "detect_hands",
            "highlight": None,
        },
        {
            "title": "✋ Show Both Hands",
            "text": "Raise both hands in front of the camera",
            "condition": "both_hands",
            "highlight": None,
        },
        {
            "title": "👇 Strike Downward!",
            "text": "Move your hand DOWN fast to hit a drum",
            "condition": "first_hit",
            "highlight": "center",
        },
        {
            "title": "🥁 Hit the SNARE!",
            "text": "Aim for the blue pad in the center",
            "condition": "hit_snare",
            "highlight": "SNARE-C",
        },
        {
            "title": "🦶 Now the KICK!",
            "text": "Hit the red pad at the bottom",
            "condition": "hit_kick",
            "highlight": "KICK-C",
        },
        {
            "title": "🎉 You're Ready!",
            "text": "Press SPACE to record, P to playback!",
            "condition": "complete",
            "highlight": None,
        },
    ]

    def __init__(self):
        self.fm = FontManager.get()
        self.current_step = 0
        self.step_timer = 0
        self.completed = False
        self.hit_counts = {}
        self.hands_detected = 0
        self.first_hit_done = False
        self._pulse = 0

    def update(self, hand_states: list, hits: list):
        """Update tutorial state based on user actions."""
        if self.completed:
            return

        self._pulse += 0.15
        self.step_timer += 1

        step = self.STEPS[self.current_step]
        condition = step["condition"]

        self.hands_detected = len(hand_states)

        for hit in hits:
            self.hit_counts[hit.pad.sound_key] = \
                self.hit_counts.get(hit.pad.sound_key, 0) + 1
            self.first_hit_done = True

        advance = False

        if condition == "detect_hands":
            advance = self.hands_detected >= 1
        elif condition == "both_hands":
            advance = self.hands_detected >= 2
        elif condition == "first_hit":
            advance = self.first_hit_done
        elif condition == "hit_snare":
            advance = self.hit_counts.get("snare", 0) >= 2
        elif condition == "hit_kick":
            advance = self.hit_counts.get("kick", 0) >= 2
        elif condition == "complete":
            if self.step_timer > 180:
                self.completed = True

        if advance and condition != "complete":
            self.current_step += 1
            self.step_timer = 0

        if self.step_timer > TUTORIAL_TIMEOUT and condition != "complete":
            self.current_step = min(self.current_step + 1, len(self.STEPS) - 1)
            self.step_timer = 0

    def render(self, surface: pygame.Surface, pads: list):
        """Render tutorial overlay."""
        if self.completed:
            return

        step = self.STEPS[self.current_step]

        dark = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        dark.fill((0, 0, 0, 140))
        surface.blit(dark, (0, 0))

        if step["highlight"] and step["highlight"] != "center":
            for pad in pads:
                if pad.name == step["highlight"]:
                    self._draw_highlight(surface, pad)

        card_w, card_h = 500, 160
        card_x = (WINDOW_WIDTH - card_w) // 2
        card_y = 100

        pulse = (math.sin(self._pulse) + 1) / 2
        glow_col = lerp_color(Colors.ACCENT_BLUE, Colors.ACCENT_PURPLE, pulse)

        glow_rect = pygame.Rect(card_x - 4, card_y - 4, card_w + 8, card_h + 8)
        pygame.draw.rect(surface, glow_col, glow_rect, 3, border_radius=20)

        card_surf = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
        card_surf.fill((15, 18, 30, 240))
        pygame.draw.rect(card_surf, Colors.GRAY_DARK,
                        (0, 0, card_w, card_h), 1, border_radius=16)
        surface.blit(card_surf, (card_x, card_y))

        for i in range(len(self.STEPS)):
            dot_x = card_x + 20 + i * 25
            dot_y = card_y + 20
            col = Colors.ACCENT_CYAN if i <= self.current_step else Colors.GRAY_DARK
            pygame.draw.circle(surface, col, (dot_x, dot_y), 6 if i == self.current_step else 4)

        title = self.fm["heading"].render(step["title"], True, Colors.WHITE)
        surface.blit(title, (card_x + (card_w - title.get_width()) // 2, card_y + 50))

        text = self.fm["body"].render(step["text"], True, Colors.GRAY_LIGHT)
        surface.blit(text, (card_x + (card_w - text.get_width()) // 2, card_y + 90))

        if step["condition"] not in ["complete"]:
            hint = self.fm["small"].render("(or wait to skip)", True, Colors.GRAY_MID)
            surface.blit(hint, (card_x + (card_w - hint.get_width()) // 2, card_y + 130))

    def _draw_highlight(self, surface: pygame.Surface, pad):
        """Draw pulsing highlight around target pad."""
        pulse = (math.sin(self._pulse * 2) + 1) / 2

        for i in range(3):
            r_off = int(20 + i * 15 + pulse * 10)
            alpha = int(150 - i * 40)
            col = (*Colors.YELLOW_NEON, alpha)

            highlight = pygame.Surface(
                (pad.rx * 2 + r_off * 2, pad.ry * 2 + r_off * 2),
                pygame.SRCALPHA
            )
            pygame.draw.ellipse(highlight, col,
                               (0, 0, pad.rx * 2 + r_off * 2, pad.ry * 2 + r_off * 2), 3)
            surface.blit(highlight,
                        (pad.cx - pad.rx - r_off, pad.cy - pad.ry - r_off))

    def skip(self):
        """Skip tutorial entirely."""
        self.completed = True


# ═══════════════════════════════════════════════════════════════
#   PRODUCTION GRADE PAD OVERLAY
# ═══════════════════════════════════════════════════════════════


class StatsPanel:
    """Right-side panel showing hit stats per drum."""

    def __init__(self, pads):
        self.pads = pads
        self.fm   = FontManager.get()
        self.x    = WINDOW_WIDTH - 160
        self.y    = HEADER_HEIGHT + 10

    def render(self, surface: pygame.Surface):
        w, h = 145, len(self.pads) * 20 + 36

        # Panel bg
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((8, 10, 20, 185))
        pygame.draw.rect(panel, Colors.GRAY_DARK,
                         (0, 0, w, h), 1, border_radius=6)
        surface.blit(panel, (self.x, self.y))

        title = self.fm["small"].render("HIT STATS", True,
                                         Colors.ACCENT_CYAN)
        surface.blit(title, (self.x + 10, self.y + 8))

        total_hits = sum(p.total_hits for p in self.pads) or 1

        for i, pad in enumerate(self.pads):
            y  = self.y + 30 + i * 20
            # Bar
            bar_w = int(100 * pad.total_hits / total_hits)
            intensity = pad.hit_intensity
            bar_col   = lerp_color(
                tuple(int(c * 0.5) for c in pad.color),
                pad.color,
                intensity
            )
            pygame.draw.rect(surface, (20, 22, 35),
                             (self.x + 8, y + 2, 100, 10), border_radius=3)
            if bar_w > 0:
                pygame.draw.rect(surface, bar_col,
                                 (self.x + 8, y + 2, bar_w, 10),
                                 border_radius=3)

            # Label
            lbl = self.fm["tiny"].render(
                f"{pad.name[:6]:6s} {pad.total_hits:3d}",
                True, Colors.GRAY_LIGHT
            )
            surface.blit(lbl, (self.x + 8, y - 2))