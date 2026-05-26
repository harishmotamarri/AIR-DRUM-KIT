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

# ── Drum Pad Layout (normalized 0-1 coords, then scaled) ──────
# Each pad: (name, center_x, center_y, radius, color_rgb, sound_key)
DRUM_PADS = [
    # ═══ LEFT HAND ZONE (Right side of screen) ═══
    # Name           cx     cy     rx    ry    Color              Sound Key    Finger
    ("L-CRASH",      0.85,  0.35,  55,   35,   (180, 100, 255),  "crash",     "left_index"),
    ("L-RIDE",       0.78,  0.45,  50,   32,   (100, 220, 180),  "ride",      "left_middle"),
    ("L-HIHAT",      0.88,  0.55,  50,   32,   (255, 220, 50 ),  "hihat",     "left_ring"),
    ("L-OPENHAT",    0.80,  0.65,  50,   32,   (255, 170, 30 ),  "openhat",   "left_pinky"),
    ("L-TOM1",       0.72,  0.75,  55,   35,   (255, 120, 60 ),  "tom1",      "left_thumb"),
    
    # ═══ RIGHT HAND ZONE (Left side of screen) ═══
    ("R-KICK",       0.15,  0.75,  60,   40,   (220, 60,  60 ),  "kick",      "right_thumb"),
    ("R-SNARE",      0.25,  0.55,  55,   35,   (60,  180, 220),  "snare",     "right_index"),
    ("R-CLAP",       0.18,  0.45,  50,   32,   (80,  255, 150),  "clap",      "right_middle"),
    ("R-TOM2",       0.30,  0.65,  50,   32,   (255, 80,  140),  "tom2",      "right_ring"),
    ("R-PERC",       0.22,  0.35,  45,   28,   (200, 150, 255),  "perc",      "right_pinky"),
    
    # ═══ CENTER ZONE (Both hands) ═══
    ("SNARE-C",      0.50,  0.50,  70,   45,   (60,  180, 220),  "snare",     "any"),
    ("KICK-C",       0.50,  0.80,  80,   50,   (220, 60,  60 ),  "kick",      "any"),
]

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