# ── Display ────────────────────────────────────────────────────────
DISPLAY_WIDTH = 720
DISPLAY_HEIGHT = 720
DISPLAY_FPS = 30
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
LENS_FOV_DEG = 155.0            # per side, 1.7mm fisheye

# ── Tracking thresholds ──────────────────────────────────────────
TRACK_COAST_MS = 500
TRACK_DROP_MS = 1000
OCCLUDED_COAST_MS = 2500

# ── Camera ─────────────────────────────────────────────────────────
CAM_WIDTH = 1280
CAM_HEIGHT = 720
CAM_FPS = 30
CAM_TYPE = "usb"                # "csi" for CSI (picamera2), "usb" for USB (V4L2)
# CSI cameras: picamera2 index (0 = first CSI camera)
CSI_RIGHT_DEVICE = 0
CSI_LEFT_DEVICE = -1            # -1 = not connected
# USB cameras: /dev/video index
CAM_RIGHT_DEVICE = 0
CAM_LEFT_DEVICE = -1            # -1 = not connected
# Detection rate cap (Hz) - 0 = unlimited (threaded detection handles contention)
DETECT_MAX_FPS = 0

# ── Detection ──────────────────────────────────────────────────────
HAILO_MODEL_PATH = "/usr/share/hailo-models/yolov8m_h10.hef"
DETECT_CONFIDENCE = 0.5
# COCO class IDs for vehicles
VEHICLE_CLASS_IDS = {2, 3, 5, 7}  # car, motorcycle, bus, truck

# ── Range estimation ───────────────────────────────────────────────
VEHICLE_WIDTH_M = 1.8           # typical track car width
FOCAL_LENGTH_PX = 500.0         # approximate for 1.7mm fisheye at frame centre
