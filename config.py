"""
╔══════════════════════════════════════════════════════════════╗
║           AIR DRUM KIT - Configuration Center               ║
╚══════════════════════════════════════════════════════════════╝
"""

# ── Display Settings ──────────────────────────────────────────
WINDOW_WIDTH        = 1280
WINDOW_HEIGHT       = 720
FPS_TARGET          = 60
WINDOW_TITLE        = "🥁 Air Drum Kit — Play the Air"

# ── Camera Settings ───────────────────────────────────────────
CAMERA_INDEX        = 0
CAMERA_WIDTH        = 1280
CAMERA_HEIGHT       = 720
FLIP_HORIZONTAL     = True   # Mirror mode feels natural

# ── Hand Tracking ─────────────────────────────────────────────
MAX_HANDS           = 2
DETECTION_CONF      = 0.7
TRACKING_CONF       = 0.7
VELOCITY_SMOOTHING  = 3     # Frames for velocity average
HIT_VELOCITY_THRESH = 12     # Pixels/frame to trigger hit
COOLDOWN_FRAMES     = 5     # Prevent double-triggers

# ── Drum Pad Layout (normalized 0-1 canvas coords) ───────────
from dataclasses import dataclass


@dataclass(frozen=True)
class PadSpec:
    id: str
    label: str
    x: float
    y: float
    w: float
    h: float
    shape: str
    color: str
    sample: str
    key: str | None = None


PADS = [
    PadSpec("crash",  "Crash",  0.18, 0.18, 0.14, 0.14, "circle",    "#6EC1E4", "assets/sfx/tollywood/crash1.wav",      "Q"),
    PadSpec("ride",   "Ride",   0.50, 0.18, 0.14, 0.14, "circle",    "#B28DFF", "assets/sfx/tollywood/ride1.wav",       "W"),
    PadSpec("splash", "Splash", 0.82, 0.18, 0.12, 0.12, "circle",    "#8EE3A6", "assets/sfx/tollywood/splash.wav",      "E"),
    PadSpec("hihatC", "Hi-Hat", 0.25, 0.40, 0.13, 0.13, "roundRect", "#FFC857", "assets/sfx/tollywood/hihat_closed.wav", "A"),
    PadSpec("snare",  "Snare",  0.50, 0.42, 0.16, 0.12, "roundRect", "#FF6B6B", "assets/sfx/tollywood/snare_devi.wav",   "S"),
    PadSpec("tom1",   "Tom 1",  0.72, 0.40, 0.13, 0.13, "roundRect", "#4D96FF", "assets/sfx/tollywood/tom1.wav",        "D"),
    PadSpec("tom2",   "Tom 2",  0.88, 0.48, 0.13, 0.13, "roundRect", "#3DDC97", "assets/sfx/tollywood/tom2.wav",        "F"),
    PadSpec("perc",   "Perc",   0.12, 0.52, 0.12, 0.12, "roundRect", "#FF9F1C", "assets/sfx/tollywood/dundubhi.wav",     "Z"),
    PadSpec("clap",   "Clap",   0.22, 0.58, 0.12, 0.12, "roundRect", "#FFD6A5", "assets/sfx/tollywood/folk_clap.wav",    "X"),
    PadSpec("kickL",  "Kick L", 0.44, 0.78, 0.18, 0.18, "circle",    "#A8DADC", "assets/sfx/tollywood/kick_left_thump.wav",  "J"),
    PadSpec("kickR",  "Kick R", 0.56, 0.78, 0.18, 0.18, "circle",    "#A8DADC", "assets/sfx/tollywood/kick_right_thump.wav", "K"),
]

# Backwards-compatible alias for older imports.
DRUM_PADS = PADS

FINGER_LANDMARKS = {
    "thumb":  4,
    "index":  8,
    "middle": 12,
    "ring":   16,
    "pinky":  20,
    "wrist":  0,
}

SHOW_TUTORIAL       = True
TUTORIAL_TIMEOUT    = 300    # frames (~5 seconds per step at 60fps)
# ── Visual Effects ────────────────────────────────────────────
RIPPLE_DURATION     = 25     # frames
RIPPLE_MAX_RADIUS   = 120
PARTICLE_COUNT      = 18     # particles per hit
PARTICLE_LIFETIME   = 40
FLASH_DURATION      = 6
GLOW_LAYERS         = 4

# ── Beat Recorder ─────────────────────────────────────────────
MAX_RECORD_BARS     = 4
BEATS_PER_BAR       = 16     # 16th note grid
DEFAULT_BPM         = 95
MIN_BPM             = 60
MAX_BPM             = 180

# ── Audio ─────────────────────────────────────────────────────
SAMPLE_RATE         = 44100
AUDIO_CHANNELS      = 2
AUDIO_BUFFER        = 128    # ← REDUCED from 512 for faster response
MAX_POLY            = 48  
# ── Colors (RGB) ──────────────────────────────────────────────
class Colors:
    BG_DARK         = (8,   10,  18 )
    BG_MID          = (15,  18,  30 )
    ACCENT_BLUE     = (40,  140, 255)
    ACCENT_PURPLE   = (160, 60,  255)
    ACCENT_CYAN     = (0,   220, 255)
    WHITE           = (255, 255, 255)
    GRAY_LIGHT      = (180, 185, 200)
    GRAY_MID        = (80,  85,  100)
    GRAY_DARK       = (30,  32,  45 )
    RED_HOT         = (255, 60,  60 )
    GREEN_NEON      = (60,  255, 120)
    YELLOW_NEON     = (255, 230, 0  )
    ORANGE          = (255, 150, 0  )
    HIT_WHITE       = (255, 255, 255)

# ── UI Layout ─────────────────────────────────────────────────
HEADER_HEIGHT       = 60
FOOTER_HEIGHT       = 80
SIDEBAR_WIDTH       = 0      # Full width layout

# ── Recording Output ──────────────────────────────────────────
RECORDINGS_DIR      = "recordings"