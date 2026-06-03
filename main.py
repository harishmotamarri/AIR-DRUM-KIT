"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║         🥁  AIR DRUM KIT — Production Grade v1.0            ║
║                                                              ║
║   Play a full drum kit with your hands in the air.          ║
║   MediaPipe hand tracking + procedural drum synthesis       ║
║   + visual effects + beat recorder.                         ║
║                                                              ║
║   Controls:                                                  ║
║     SPACE     → Record / Stop Recording                     ║
║     P         → Play / Stop Loop                            ║
║     UP/DOWN   → BPM +5 / -5                                 ║
║     S         → Save beat to JSON                           ║
║     R         → Reset hit statistics                        ║
║     ESC/Q     → Quit                                        ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""

import cv2
import pygame
import numpy as np
import sys
import time
import math
import os
os.environ['SDL_AUDIODRIVER'] = 'directsound'
from threading import Thread
from collections import deque

# ── Local imports ─────────────────────────────────────────────
from config import (
    WINDOW_WIDTH, WINDOW_HEIGHT, FPS_TARGET, WINDOW_TITLE,
    CAMERA_INDEX, CAMERA_WIDTH, CAMERA_HEIGHT, FLIP_HORIZONTAL,
    SAMPLE_RATE, AUDIO_CHANNELS, AUDIO_BUFFER, MAX_POLY,
    Colors, RECORDINGS_DIR, SHOW_TUTORIAL, TUTORIAL_TIMEOUT, PADS,
    HEADER_HEIGHT, FOOTER_HEIGHT,
)
from sound_generator  import SoundBank
from hand_tracker     import HandTracker
from drum_engine      import DrumEngine, HitEvent
from visual_effects   import EffectsEngine
from beat_recorder    import BeatRecorder
from ui_components    import (Header, Footer, BeatGridUI,
                               PadOverlay, StatsPanel, TutorialOverlay,
                               FullscreenButton,
                               FontManager)
from air_writer       import AirWriter

MODE_DRUMMING = "drumming"
MODE_WRITING  = "writing"

toggle_cooldown = 1.5
last_toggle_time = 0.0
OPEN_PALM_HOLD_SECONDS = 0.30
PAD_FADE_SECONDS = 0.30
TOGGLE_BANNER_SECONDS = 1.50



# ══════════════════════════════════════════════════════════════
#   Startup Banner
# ══════════════════════════════════════════════════════════════

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║     ██████╗ ██████╗ ██╗   ██╗███╗   ███╗                    ║
║     ██╔══██╗██╔══██╗██║   ██║████╗ ████║                    ║
║     ██║  ██║██████╔╝██║   ██║██╔████╔██║                    ║
║     ██║  ██║██╔══██╗██║   ██║██║╚██╔╝██║                    ║
║     ██████╔╝██║  ██║╚██████╔╝██║ ╚═╝ ██║                    ║
║     ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚═╝     ╚═╝  KIT               ║
║                                                              ║
║           Play the air. Make music. Wow everyone.            ║
╚══════════════════════════════════════════════════════════════╝
"""


# ══════════════════════════════════════════════════════════════
#   Camera Thread
# ══════════════════════════════════════════════════════════════

class CameraThread(Thread):
    """Non-blocking camera capture on a background thread."""

    def __init__(self, index: int):
        super().__init__(daemon=True)
        self.cap     = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS,          60)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)
        self.frame   : np.ndarray | None = None
        self._running = True
        self._ok      = self.cap.isOpened()

    @property
    def ok(self) -> bool:
        return self._ok

    def run(self):
        while self._running:
            ret, frame = self.cap.read()
            if ret:
                if FLIP_HORIZONTAL:
                    frame = cv2.flip(frame, 1)
                self.frame = frame
            else:
                time.sleep(0.005)

    def stop(self):
        self._running = False
        self.cap.release()


def _lerp_point(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
    t = max(0.0, min(1.0, t))
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _ease_out_quad(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) * (1.0 - t)


class StickAnimator:
    """Simple drumstick animation that chases a pad target and rebounds."""

    def __init__(self):
        self._sticks: dict[int, dict] = {}

    def _get(self, hand_id: int, anchor: tuple[float, float]) -> dict:
        stick = self._sticks.get(hand_id)
        if stick is None:
            stick = {
                "anchor": anchor,
                "pos": anchor,
                "target": anchor,
                "phase": "idle",
                "t": 0.0,
            }
            self._sticks[hand_id] = stick
        return stick

    def on_hit(self, hand_id: int, anchor: tuple[float, float], target: tuple[float, float]):
        stick = self._get(hand_id, anchor)
        stick["anchor"] = anchor
        stick["target"] = target
        stick["phase"] = "strike"
        stick["t"] = 0.0

    def update(self, dt: float, hand_states):
        anchors = {
            state.hand_id: (float(state.strike_point.x), float(state.strike_point.y))
            for state in hand_states
        }

        for hand_id, stick in list(self._sticks.items()):
            if hand_id in anchors:
                stick["anchor"] = anchors[hand_id]

            if stick["phase"] == "strike":
                stick["t"] += dt
                k = _ease_out_quad(min(1.0, stick["t"] / 0.12))
                stick["pos"] = _lerp_point(stick["pos"], stick["target"], k)
                if k >= 1.0:
                    stick["phase"] = "rebound"
                    stick["t"] = 0.0
            elif stick["phase"] == "rebound":
                stick["t"] += dt
                k = _ease_out_quad(min(1.0, stick["t"] / 0.18))
                stick["pos"] = _lerp_point(stick["pos"], stick["anchor"], k)
                if k >= 1.0:
                    stick["phase"] = "idle"
                    stick["t"] = 0.0
                    stick["pos"] = stick["anchor"]
            else:
                stick["pos"] = _lerp_point(stick["pos"], stick["anchor"], min(1.0, dt * 10.0))

    def render(self, surface: pygame.Surface):
        for stick in self._sticks.values():
            ax, ay = stick["anchor"]
            px, py = stick["pos"]
            dx = px - ax
            dy = py - ay
            dist = math.hypot(dx, dy)
            if dist < 1.0:
                continue

            ux = dx / dist
            uy = dy / dist
            base = (ax - ux * 18.0, ay - uy * 18.0)
            tip = (px + ux * 18.0, py + uy * 18.0)

            pygame.draw.line(surface, (0, 0, 0, 90), base, tip, 10)
            pygame.draw.line(surface, (244, 220, 176), base, tip, 6)
            pygame.draw.line(surface, (255, 255, 255), (base[0] + ux * 2, base[1] + uy * 2), (tip[0] - ux * 2, tip[1] - uy * 2), 2)
            pygame.draw.circle(surface, (255, 255, 255), (int(px), int(py)), 4)
            pygame.draw.circle(surface, (230, 180, 120), (int(base[0]), int(base[1])), 5)


# ══════════════════════════════════════════════════════════════
#   AirDrumApp
# ══════════════════════════════════════════════════════════════

class AirDrumApp:
    """
    Main application class.
    Orchestrates all subsystems and runs the main loop.
    """

    def __init__(self):
        print(BANNER)
        self._fullscreen = False
        self._first_gesture_consumed = False
        self._latest_hand_states = []
        self._open_palm_since = None
        self._toggle_armed = True
        self._gesture_ready = False
        
        self.mode = MODE_DRUMMING
        self._pad_visibility_alpha = 255.0
        self._pad_visibility_target = 255.0
        self._pad_visibility_speed = 255.0 / PAD_FADE_SECONDS
        self._toggle_banner = None

        self._init_audio()
        self._init_display()
        self._init_subsystems()
        self._init_ui()
        self._running = True

        # State
        self._fps_hist = deque(maxlen=30)
        self._last_t   = time.time()
        self._fps      = 0.0
        self._message  = ""
        self._msg_timer = 0

        print("\n✅  All systems initialized. Starting...")
        print("🎵  Point your camera at yourself and hit those drums!\n")

    # ── Initialization ────────────────────────────────────────

    def _init_audio(self):
        print("🔊 Initializing audio...")
        pygame.mixer.pre_init(
            frequency=SAMPLE_RATE,
            size=-16,
            channels=AUDIO_CHANNELS,
            buffer=128,
        )
        pygame.mixer.init()
        pygame.mixer.set_num_channels(MAX_POLY)
        self.sound_bank = SoundBank(PADS)

    def _init_display(self):
        print("🖥  Initializing display...")
        pygame.init()
        self._set_display_mode(fullscreen=False)
        pygame.display.set_caption(WINDOW_TITLE)

        # Try to set a nice icon
        try:
            icon = pygame.Surface((32, 32), pygame.SRCALPHA)
            pygame.draw.circle(icon, (220, 60, 60), (16, 16), 14)
            pygame.draw.circle(icon, (255, 255, 255), (16, 16), 14, 2)
            pygame.display.set_icon(icon)
        except Exception:
            pass

        self.clock  = pygame.time.Clock()
        self.fm     = FontManager.get()

        # Surfaces
        self.overlay_surf  = pygame.Surface(
            (WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        self.pad_surf      = pygame.Surface(
            (WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        self.effects_surf  = pygame.Surface(
            (WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        self.ui_surf       = pygame.Surface(
            (WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)

    def _init_subsystems(self):
        print("🤖 Initializing subsystems...")
        self.camera   = CameraThread(CAMERA_INDEX)
        self.tracker  = HandTracker()
        self.engine   = DrumEngine()
        self.effects  = EffectsEngine()
        self.recorder = BeatRecorder()
        self.air_writer = AirWriter()

        if not self.camera.ok:

            print("⚠️  Camera not found — using test pattern")
        self.camera.start()

        # Wire hit callback
        self.engine.register_callback(self._on_hit)

    def _init_ui(self):
        print("🎨 Initializing UI...")
        self.header     = Header()
        self.footer     = Footer()
        self.beat_grid  = BeatGridUI()
        self.pad_overlay= PadOverlay(self.engine.pads)
        self.stats_panel= StatsPanel(self.engine.pads)
        self.tutorial   = TutorialOverlay()
        self.fullscreen_button = FullscreenButton()
        self.sticks = StickAnimator()

    def _set_display_mode(self, fullscreen: bool):
        self._fullscreen = fullscreen
        flags = pygame.DOUBLEBUF | pygame.SCALED
        flags |= pygame.FULLSCREEN if fullscreen else pygame.RESIZABLE
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), flags)

    def _toggle_fullscreen(self):
        self._set_display_mode(not self._fullscreen)

    def _consume_first_gesture(self):
        if not self._first_gesture_consumed:
            self._first_gesture_consumed = True
            if not self._fullscreen:
                self._set_display_mode(True)

    def _set_mode(self, mode: str):
        self.mode = mode
        if mode == MODE_DRUMMING:
            self._pad_visibility_target = 255.0
            self._start_toggle_banner("DRUM MODE")
            self._play_toggle_sound(True)
        else:
            self._pad_visibility_target = 0.0
            self._start_toggle_banner("AIR WRITING MODE")
            self._play_toggle_sound(False)

    def _start_toggle_banner(self, text: str):
        self._toggle_banner = {
            "text": text,
            "activated": (text == "DRUM MODE"),
            "start": time.time(),
            "duration": TOGGLE_BANNER_SECONDS,
        }

    def _play_toggle_sound(self, activated: bool):
        sound_key = "ui_activate" if activated else "ui_deactivate"
        try:
            self.sound_bank.play(sound_key, 1.0)
        except Exception:
            pass

    def _toggle_mode(self, now: float):
        global last_toggle_time

        last_toggle_time = now
        self._toggle_armed = False
        new_mode = MODE_WRITING if self.mode == MODE_DRUMMING else MODE_DRUMMING
        self._set_mode(new_mode)

    def _update_gesture_toggle(self, hand_states, now: float):
        global last_toggle_time

        open_palm_detected = any(state.is_open_palm for state in hand_states)

        if not open_palm_detected:
            self._gesture_ready = True
            self._open_palm_since = None
            self._toggle_armed = True
            return

        if not self._gesture_ready:
            self._open_palm_since = None
            self._toggle_armed = False
            return

        if self._open_palm_since is None:
            self._open_palm_since = now

        if not self._toggle_armed:
            return

        cooldown_remaining = toggle_cooldown - (now - last_toggle_time)
        if cooldown_remaining > 0.0:
            self._toggle_armed = False
            return

        hold_time = now - self._open_palm_since
        if hold_time >= OPEN_PALM_HOLD_SECONDS:
            self._toggle_mode(now)

    def _process_writing_gestures(self, hand_states, now: float):
        if self.mode != MODE_WRITING:
            return
            
        for state in hand_states:
            idx_up = state.finger_open_states.get("index", False)
            mid_up = state.finger_open_states.get("middle", False)
            rng_up = state.finger_open_states.get("ring", False)
            pnk_up = state.finger_open_states.get("pinky", False)
            
            if idx_up and mid_up and not rng_up and state.open_finger_count == 2:
                # Clear canvas (Peace sign)
                if now - self.air_writer.last_clear_time > 1.5:
                    self.air_writer.clear_canvas()
                    self.air_writer.last_clear_time = now
                    self._show_message("CANVAS CLEARED", 60)
            elif idx_up and mid_up and rng_up and not pnk_up and state.open_finger_count == 3:
                # Undo last stroke (Three fingers)
                if now - self.air_writer.last_undo_time > 0.5:
                    self.air_writer.undo_last_stroke()
                    self.air_writer.last_undo_time = now
                    self._show_message("UNDO", 60)
            elif idx_up and mid_up and rng_up and pnk_up and state.open_finger_count == 4:
                # Change Color (Four fingers)
                if now - self.air_writer.last_color_time > 1.0:
                    self.air_writer.cycle_color()
                    self.air_writer.last_color_time = now
                    cname = f"RGB: {self.air_writer.color}"
                    self._show_message(f"COLOR CHANGED {cname}", 60)
            
            # Allow air writer to process the hand position
            self.air_writer.process_hand(state, now)

    def _update_pad_visibility(self, dt: float):
        target = self._pad_visibility_target
        if self._pad_visibility_alpha == target:
            return

        step = self._pad_visibility_speed * dt
        if self._pad_visibility_alpha < target:
            self._pad_visibility_alpha = min(target, self._pad_visibility_alpha + step)
        else:
            self._pad_visibility_alpha = max(target, self._pad_visibility_alpha - step)

    def _render_toggle_banner(self, surface: pygame.Surface):
        if not self._toggle_banner:
            return

        now = time.time()
        elapsed = now - self._toggle_banner["start"]
        duration = self._toggle_banner["duration"]
        if elapsed >= duration:
            self._toggle_banner = None
            return

        progress = elapsed / duration
        text = self._toggle_banner["text"]
        activated = self._toggle_banner["activated"]

        text_surf = self.fm["big"].render(text, True, Colors.WHITE)
        scale = 0.78 + 0.30 * min(1.0, progress / 0.25)
        scale += 0.06 * math.sin(progress * math.pi * 3.0)
        scale = max(0.55, scale)
        scaled_size = (
            max(1, int(text_surf.get_width() * scale)),
            max(1, int(text_surf.get_height() * scale)),
        )
        text_surf = pygame.transform.smoothscale(text_surf, scaled_size)

        if progress < 0.18:
            alpha = int(255 * (progress / 0.18))
        else:
            alpha = int(255 * max(0.0, 1.0 - ((progress - 0.18) / 0.82)))
        text_surf.set_alpha(alpha)

        glow_surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        cx = WINDOW_WIDTH // 2
        cy = WINDOW_HEIGHT // 2 - 40
        base_color = Colors.ACCENT_BLUE if activated else Colors.ACCENT_CYAN
        glow_color = (80, 160, 255) if activated else (100, 240, 255)

        for offset, glow_alpha in [(4, 50), (2, 85), (1, 120)]:
            glow = self.fm["big"].render(text, True, glow_color)
            glow = pygame.transform.smoothscale(
                glow,
                (
                    max(1, int(glow.get_width() * scale)),
                    max(1, int(glow.get_height() * scale)),
                ),
            )
            glow.set_alpha(int(glow_alpha * max(0.0, 1.0 - progress)))
            glow_rect = glow.get_rect(center=(cx + offset, cy + offset))
            glow_surface.blit(glow, glow_rect)

        if activated:
            pulse_surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
            pulse_progress = min(1.0, elapsed / 0.7)
            radius = int(max(WINDOW_WIDTH, WINDOW_HEIGHT) * 0.10 + pulse_progress * max(WINDOW_WIDTH, WINDOW_HEIGHT) * 0.55)
            pulse_alpha = int(130 * (1.0 - pulse_progress))
            pygame.draw.circle(pulse_surface, (*base_color, pulse_alpha), (cx, WINDOW_HEIGHT // 2), radius, 10)
            pygame.draw.circle(pulse_surface, (*glow_color, pulse_alpha // 2), (cx, WINDOW_HEIGHT // 2), max(10, radius // 2), 2)
            surface.blit(pulse_surface, (0, 0))

            sweep_surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
            sweep_progress = min(1.0, elapsed / 0.8)
            sweep_x = int(-WINDOW_WIDTH * 0.25 + sweep_progress * WINDOW_WIDTH * 1.35)
            sweep_rect = pygame.Rect(sweep_x, HEADER_HEIGHT, WINDOW_WIDTH // 5, WINDOW_HEIGHT - HEADER_HEIGHT - FOOTER_HEIGHT)
            pygame.draw.rect(sweep_surface, (40, 140, 255, int(40 * (1.0 - sweep_progress))), sweep_rect)
            pygame.draw.rect(sweep_surface, (120, 220, 255, int(70 * (1.0 - sweep_progress))), sweep_rect.inflate(-sweep_rect.width // 3, 0))
            surface.blit(sweep_surface, (0, 0))

        surface.blit(glow_surface, (0, 0))

        shadow = self.fm["big"].render(text, True, (0, 0, 0))
        shadow.set_alpha(max(0, alpha // 2))
        surface.blit(shadow, (cx - text_surf.get_width() // 2 + 4, cy - text_surf.get_height() // 2 + 4))
        surface.blit(text_surf, (cx - text_surf.get_width() // 2, cy - text_surf.get_height() // 2))

    # ── Hit Callback ──────────────────────────────────────────

    def _on_hit(self, event: HitEvent):
        """Called on every confirmed drum hit."""
        anchor = (float(event.x), float(event.y))
        for state in self._latest_hand_states:
            if state.hand_id == event.hand_id:
                anchor = (float(state.strike_point.x), float(state.strike_point.y))
                break
        self.sticks.on_hit(event.hand_id, anchor, (float(event.pad.cx), float(event.pad.cy)))

        # Play sound
        self.sound_bank.play(event.pad.sound_key, event.velocity)

        # Spawn effects
        self.effects.spawn_hit(
            x=event.x, y=event.y,
            color=event.pad.color,
            pad_rx=event.pad.rx,
            pad_ry=event.pad.ry,
            velocity=event.velocity,
            pad_name=event.pad.name,
        )

        # Record if recording
        if self.recorder.is_recording:
            self.recorder.record_hit(event.pad.sound_key, event.velocity)

    # ── Input ─────────────────────────────────────────────────

    def _handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self._running = False

            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_F11:
                    self._toggle_fullscreen()
                else:
                    self._consume_first_gesture()
                self._handle_key(ev.key)

            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if self.fullscreen_button.hit_test(ev.pos):
                    self._toggle_fullscreen()
                else:
                    self._consume_first_gesture()

            elif ev.type == pygame.VIDEORESIZE:
                pass  # Handled by RESIZABLE flag

    def _handle_key(self, key: int):
        if SHOW_TUTORIAL and not self.tutorial.completed and key != pygame.K_ESCAPE:
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                self.tutorial.skip()
                self._show_message("Tutorial skipped — let's jam!")
                return

        if key in (pygame.K_ESCAPE, pygame.K_q):
            self._running = False

        elif key == pygame.K_SPACE:
            if self.recorder.is_recording:
                self.recorder.stop_recording()
                self._show_message("⏹  Recording stopped")
            else:
                self.recorder.start_recording()
                self._show_message("⏺  Recording… play your beat!")

        elif key == pygame.K_p:
            if self.recorder.is_playing:
                self.recorder.stop_playback()
                self._show_message("⏹  Playback stopped")
            elif self.recorder.pattern:
                self.recorder.start_playback()
                self._show_message("▶  Looping your beat!")
            else:
                self._show_message("⚠️  Nothing recorded yet")

        elif key == pygame.K_UP:
            self.recorder.bpm = self.recorder.bpm + 5
            self._show_message(f"♩ BPM → {self.recorder.bpm:.0f}")

        elif key == pygame.K_DOWN:
            self.recorder.bpm = self.recorder.bpm - 5
            self._show_message(f"♩ BPM → {self.recorder.bpm:.0f}")

        elif key == pygame.K_s:
            if self.mode == MODE_WRITING:
                self._save_drawing()
            else:
                path = self.recorder.save()
                if path:
                    self._show_message(f"💾  Saved: {os.path.basename(path)}")
                else:
                    self._show_message("⚠️  Nothing to save")
                    
        elif key == pygame.K_c:
            if self.mode == MODE_WRITING:
                self.air_writer.cycle_color()
                self._show_message(f"COLOR CHANGED RGB: {self.air_writer.color}", 60)

        elif key == pygame.K_r:
            self.engine.reset_stats()
            self._show_message("↺  Stats reset")

        # ── Letter keys mapped to pads (e.g. Q W E A S D ...)
        else:
            try:
                kname = pygame.key.name(key).upper()
            except Exception:
                kname = ""

            if len(kname) == 1 and kname.isalpha():
                # Let the engine handle cooldowns and callbacks
                _ = self.engine.trigger_pad_by_key(kname, enabled=(self.mode == MODE_DRUMMING))

    def _save_drawing(self):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"drawing_{timestamp}.png"
        path = os.path.join(RECORDINGS_DIR, filename)
        os.makedirs(RECORDINGS_DIR, exist_ok=True)
        pygame.image.save(self.screen, path)
        self._show_message(f"💾 Saved Drawing: {filename}", 60)

    def _show_message(self, text: str, duration: int = 150):
        self._message  = text
        self._msg_timer = duration

    # ── Frame Processing ──────────────────────────────────────

    def _get_camera_frame(self) -> np.ndarray | None:
        """Get latest camera frame or generate test pattern."""
        if self.camera.frame is not None:
            return self.camera.frame.copy()

        # Fallback: dark gradient test pattern
        frame = np.zeros((CAMERA_HEIGHT, CAMERA_WIDTH, 3), dtype=np.uint8)
        frame[:] = [8, 10, 18]
        cv2.putText(frame, "No Camera — Using Test Mode",
                    (WINDOW_WIDTH//2 - 200, WINDOW_HEIGHT//2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (80, 85, 100), 2)
        return frame

    def _process_playback(self):
        """Fire sounds for due playback events."""
        if not self.recorder.is_playing:
            return

        events = self.recorder.get_due_events()
        for ev in events:
            self.sound_bank.play(ev.sound_key, ev.velocity)
            pad = self.engine.get_pad_by_sound(ev.sound_key)
            if pad:
                pad.hit_intensity = ev.velocity
                self.effects.spawn_hit(
                    x=float(pad.cx), y=float(pad.cy),
                    color=pad.color,
                    pad_rx=pad.rx, pad_ry=pad.ry,
                    velocity=ev.velocity,
                    pad_name=pad.name,
                )

    def _cv_frame_to_pygame(self, frame: np.ndarray) -> pygame.Surface:
        """Convert OpenCV BGR frame → pygame RGB surface, scaled to window."""
        # Resize to window
        if frame.shape[1] != WINDOW_WIDTH or frame.shape[0] != WINDOW_HEIGHT:
            frame = cv2.resize(frame, (WINDOW_WIDTH, WINDOW_HEIGHT),
                               interpolation=cv2.INTER_LINEAR)
        # BGR → RGB
        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        surf  = pygame.surfarray.make_surface(rgb.transpose(1, 0, 2))
        return surf

    # ── Render Pipeline ───────────────────────────────────────

    def _render_background_bars(self, frame: np.ndarray):
        """Draw subtle horizontal scan lines for depth."""
        h, w = frame.shape[:2]
        for y in range(0, h, 4):
            frame[y] = (frame[y].astype(np.float32) * 0.88).astype(np.uint8)

    def _render_vignette(self, surface: pygame.Surface):
        """Soft dark vignette around edges."""
        vig = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        center = (WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2)
        for i in range(8):
            r   = int(max(WINDOW_WIDTH, WINDOW_HEIGHT) * (0.5 + i * 0.07))
            a   = int(40 * (8 - i) / 8)
            pygame.draw.ellipse(vig, (0, 0, 0, a),
                                (center[0] - r, center[1] - r//2,
                                 r*2, r))
        surface.blit(vig, (0, 0))

    def _render_recording_ring(self, surface: pygame.Surface):
        """Pulsing recording progress ring around screen border."""
        if not self.recorder.is_recording:
            return
        prog = self.recorder.record_progress
        t    = time.time()
        pulse = (math.sin(t * 12) + 1) / 2

        # Progress arc on border
        col  = lerp_color2((180, 20, 20), Colors.RED_HOT, pulse)
        pygame.draw.rect(surface, col,
                         (0, 0, WINDOW_WIDTH, 3))
        pygame.draw.rect(surface, col,
                         (0, WINDOW_HEIGHT-3, WINDOW_WIDTH, 3))
        # Progress bar top
        pw = int(WINDOW_WIDTH * prog)
        pygame.draw.rect(surface, Colors.RED_HOT, (0, 0, pw, 5))

    def _render_playback_indicator(self, surface: pygame.Surface):
        """Thin animated bar showing loop position."""
        if not self.recorder.is_playing:
            return
        prog = self.recorder.play_progress
        px   = int(WINDOW_WIDTH * prog)
        pygame.draw.rect(surface, Colors.GREEN_NEON,
                         (0, WINDOW_HEIGHT - 3, px, 3))
        # Glowing dot
        pygame.draw.circle(surface, Colors.GREEN_NEON,
                           (px, WINDOW_HEIGHT - 1), 5)

    def _render_hud_message(self, surface: pygame.Surface):
        """Center-screen floating message."""
        if self._msg_timer <= 0:
            return
        self._msg_timer -= 1
        alpha  = min(255, self._msg_timer * 6)
        y_off  = max(0, 30 - self._msg_timer) * 2

        txt    = self.fm["heading"].render(self._message, True, Colors.WHITE)
        txt.set_alpha(alpha)

        # Shadow
        shadow = self.fm["heading"].render(self._message, True, (0, 0, 0))
        shadow.set_alpha(alpha // 2)

        cx = WINDOW_WIDTH  // 2
        cy = WINDOW_HEIGHT // 2 - 80 + y_off

        # Pill background
        pill_w = txt.get_width()  + 40
        pill_h = txt.get_height() + 20
        pill   = pygame.Surface((pill_w, pill_h), pygame.SRCALPHA)
        pill.fill((0, 0, 0, int(alpha * 0.6)))
        pygame.draw.rect(pill, (255, 255, 255, int(alpha * 0.3)),
                         (0, 0, pill_w, pill_h), 1, border_radius=12)
        pill.set_alpha(alpha)
        surface.blit(pill, (cx - pill_w//2, cy - pill_h//2))

        surface.blit(shadow, (cx - txt.get_width()//2 + 1,
                               cy - txt.get_height()//2 + 1))
        surface.blit(txt,    (cx - txt.get_width()//2,
                               cy - txt.get_height()//2))

    def _render_hand_info(self, surface: pygame.Surface,
                          hand_states):
        """Small hand velocity readouts."""
        for state in hand_states:
            sp   = state.strike_point
            col  = (0, 180, 255) if state.handedness == "Right" \
                   else (255, 140, 0)
            side = state.handedness[0]

            speed_txt = self.fm["tiny"].render(
                f"{side}: {sp.speed:.0f}px/f",
                True, col
            )
            x = int(sp.x) + 15
            y = int(sp.y) - 20
            x = max(5, min(WINDOW_WIDTH  - speed_txt.get_width()  - 5, x))
            y = max(5, min(WINDOW_HEIGHT - speed_txt.get_height() - 5, y))
            speed_txt.set_alpha(180)
            surface.blit(speed_txt, (x, y))

    # ── Main Loop ─────────────────────────────────────────────

    def run(self):
        """🎬 Main application loop."""
        import math

        global lerp_color2

        def lerp_color2(c1, c2, t):
            t = max(0.0, min(1.0, t))
            return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))

        try:
            while self._running:
                # ── FPS ──────────────────────────────────────
                now = time.time()
                dt  = now - self._last_t
                self._last_t = now
                if dt > 0:
                    self._fps_hist.append(1.0 / dt)
                self._fps = np.mean(self._fps_hist) if self._fps_hist else 0

                # ── Events ───────────────────────────────────
                self._handle_events()

                # ── Camera ───────────────────────────────────
                raw_frame = self._get_camera_frame()

                # ── Hand Tracking ────────────────────────────
                hand_states = self.tracker.process(raw_frame)
                self._latest_hand_states = hand_states
                self._update_gesture_toggle(hand_states, now)
                self._process_writing_gestures(hand_states, now)

                # ── Draw skeleton on CV frame ─────────────────
                self.tracker.draw_skeleton(raw_frame, hand_states)
                
                if self.mode == MODE_WRITING:
                    self.air_writer.render_cv2(raw_frame)

                # ── Drum Hit Detection ────────────────────────
                hits = self.engine.update(hand_states, enabled=(self.mode == MODE_DRUMMING))

                # ── Tutorial State ─────────────────────────
                if SHOW_TUTORIAL and not self.tutorial.completed:
                    self.tutorial.update(hand_states, hits)

                # ── Playback ─────────────────────────────────
                self._process_playback()

                # ── Effects Update ───────────────────────────
                self.effects.update()

                # ── Effects on CV frame ──────────────────────
                self.effects.render_on_frame(raw_frame)

                # ── Drumstick animation ─────────────────────
                self.sticks.update(dt, hand_states)

                # ── Pad visibility animation ────────────────
                self._update_pad_visibility(dt)

                # ── CV → Pygame ──────────────────────────────
                cam_surf = self._cv_frame_to_pygame(raw_frame)
                self.screen.blit(cam_surf, (0, 0))

                # ── Vignette ─────────────────────────────────
                self._render_vignette(self.screen)

                # ── Pad Overlay ──────────────────────────────
                self.pad_surf.fill((0, 0, 0, 0))
                if self._pad_visibility_alpha > 0.5:
                    self.pad_overlay.render(self.pad_surf, hand_states)
                    if self._pad_visibility_alpha >= 254:
                        self.screen.blit(self.pad_surf, (0, 0))
                    else:
                        pad_layer = self.pad_surf.copy()
                        pad_layer.set_alpha(int(self._pad_visibility_alpha))
                        self.screen.blit(pad_layer, (0, 0))

                # ── Effects Pygame Layer ──────────────────────
                self.effects_surf.fill((0, 0, 0, 0))
                self.effects.render_on_pygame(
                    self.effects_surf, self.fm["heading"])
                self.screen.blit(self.effects_surf, (0, 0))

                # ── UI Layer ─────────────────────────────────
                self.ui_surf.fill((0, 0, 0, 0))

                # Header & Footer
                self.header.render(
                    self.ui_surf, self._fps,
                    self.recorder.state,
                    self.recorder.bpm,
                    self.engine.hit_count,
                    self.effects.beat_pulse_intensity,
                )
                self.fullscreen_button.render(self.ui_surf, self._fullscreen)
                self.footer.render(self.ui_surf)

                # Beat grid
                grid_data = self.recorder.get_grid_data()
                self.beat_grid.render(
                    self.ui_surf, grid_data,
                    self.recorder.is_recording,
                    self.recorder.is_playing,
                )

                # Stats
                self.stats_panel.render(self.ui_surf)

                # Recording / Playback indicators
                self._render_recording_ring(self.ui_surf)
                self._render_playback_indicator(self.ui_surf)

                # Hand info
                self._render_hand_info(self.ui_surf, hand_states)

                # Drumsticks
                self.sticks.render(self.ui_surf)

                # HUD message
                self._render_hud_message(self.ui_surf)

                # Toggle banner and transition FX
                self._render_toggle_banner(self.ui_surf)

                self.screen.blit(self.ui_surf, (0, 0))

                # Tutorial overlay
                if SHOW_TUTORIAL and not self.tutorial.completed:
                    self.tutorial.render(self.screen, self.engine.pads)

                # ── Flip ─────────────────────────────────────
                pygame.display.flip()
                self.clock.tick(FPS_TARGET)

        except KeyboardInterrupt:
            print("\n👋  Interrupted by user")
        finally:
            self._cleanup()

    # ── Cleanup ───────────────────────────────────────────────

    def _cleanup(self):
        print("\n🧹  Shutting down...")
        self.camera.stop()
        self.tracker.release()
        pygame.mixer.quit()
        pygame.quit()
        cv2.destroyAllWindows()
        print("✅  Goodbye!\n")


# ══════════════════════════════════════════════════════════════
#   Entry Point
# ══════════════════════════════════════════════════════════════

def main():
    # Validate Python version
    if sys.version_info < (3, 10):
        print("❌  Python 3.10+ required")
        sys.exit(1)

    # Validate deps
    missing = []
    for pkg in ["cv2", "mediapipe", "pygame", "numpy", "scipy"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"❌  Missing packages: {', '.join(missing)}")
        print("   Run: pip install -r requirements.txt")
        sys.exit(1)

    app = AirDrumApp()
    app.run()


if __name__ == "__main__":
    main()
