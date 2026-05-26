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
import os
os.environ['SDL_AUDIODRIVER'] = 'directsound'
from threading import Thread
from collections import deque

# ── Local imports ─────────────────────────────────────────────
from config import (
    WINDOW_WIDTH, WINDOW_HEIGHT, FPS_TARGET, WINDOW_TITLE,
    CAMERA_INDEX, CAMERA_WIDTH, CAMERA_HEIGHT, FLIP_HORIZONTAL,
    SAMPLE_RATE, AUDIO_CHANNELS, AUDIO_BUFFER, MAX_POLY,
    Colors, RECORDINGS_DIR, SHOW_TUTORIAL, TUTORIAL_TIMEOUT,
)
from sound_generator  import SoundBank
from hand_tracker     import HandTracker
from drum_engine      import DrumEngine, HitEvent
from visual_effects   import EffectsEngine
from beat_recorder    import BeatRecorder
from ui_components    import (Header, Footer, BeatGridUI,
                               PadOverlay, StatsPanel, TutorialOverlay,
                               FontManager)


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
        self.sound_bank = SoundBank()

    def _init_display(self):
        print("🖥  Initializing display...")
        pygame.init()
        self.screen = pygame.display.set_mode(
            (WINDOW_WIDTH, WINDOW_HEIGHT),
            pygame.RESIZABLE | pygame.DOUBLEBUF | pygame.HWSURFACE,
        )
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

    # ── Hit Callback ──────────────────────────────────────────

    def _on_hit(self, event: HitEvent):
        """Called on every confirmed drum hit."""
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
                self._handle_key(ev.key)

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
            path = self.recorder.save()
            if path:
                self._show_message(f"💾  Saved: {os.path.basename(path)}")
            else:
                self._show_message("⚠️  Nothing to save")

        elif key == pygame.K_r:
            self.engine.reset_stats()
            self._show_message("↺  Stats reset")

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

                # ── Draw skeleton on CV frame ─────────────────
                self.tracker.draw_skeleton(raw_frame, hand_states)

                # ── Drum Hit Detection ────────────────────────
                hits = self.engine.update(hand_states)

                # ── Tutorial State ─────────────────────────
                if SHOW_TUTORIAL and not self.tutorial.completed:
                    self.tutorial.update(hand_states, hits)

                # ── Playback ─────────────────────────────────
                self._process_playback()

                # ── Effects Update ───────────────────────────
                self.effects.update()

                # ── Effects on CV frame ──────────────────────
                self.effects.render_on_frame(raw_frame)

                # ── CV → Pygame ──────────────────────────────
                cam_surf = self._cv_frame_to_pygame(raw_frame)
                self.screen.blit(cam_surf, (0, 0))

                # ── Vignette ─────────────────────────────────
                self._render_vignette(self.screen)

                # ── Pad Overlay ──────────────────────────────
                self.pad_surf.fill((0, 0, 0, 0))
                self.pad_overlay.render(self.pad_surf, hand_states)
                self.screen.blit(self.pad_surf, (0, 0))

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

                # HUD message
                self._render_hud_message(self.ui_surf)

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
