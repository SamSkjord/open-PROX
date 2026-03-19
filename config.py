# ── Display ────────────────────────────────────────────────────────
DISPLAY_WIDTH = 720
DISPLAY_HEIGHT = 720
DISPLAY_FPS = 60
DISPLAY_RANGE_M = 5.0
DISPLAY_BG_COLOUR = (8, 8, 8)

TRAIL_FRAMES = 8

# ── Blip geometry ─────────────────────────────────────────────────
BLIP_LENGTH_PX = 32
BLIP_WIDTH_PX = 16

# ── Proximity glow ───────────────────────────────────────────────
GLOW_COLOUR = (255, 120, 0)     # orange
GLOW_MAX_ALPHA = 70             # peak opacity (0-255)
GLOW_RANGE_M = 2.0              # contacts closer than this get a glow
GLOW_RADIUS_PX = 140            # glow circle radius at closest range

# ── Range rings ───────────────────────────────────────────────────
RANGE_RING_INTERVAL_M = 1.0
RANGE_RING_COLOUR = (30, 30, 30)

# ── Coverage cones ────────────────────────────────────────────────
COVERAGE_CONES_ENABLED = False
LENS_FOV_DEG = 155.0            # per side, 2.1mm fisheye

# ── Tracking thresholds ──────────────────────────────────────────
TRACK_COAST_MS = 500
TRACK_DROP_MS = 1000
OCCLUDED_COAST_MS = 2500
