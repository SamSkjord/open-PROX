# open-PROX — Proximity Awareness System
## Project Plan v5 — Corrected USB Topology

---

## Project Overview

open-PROX is a dedicated vehicle proximity awareness system for motorsport track day use, providing a real-time top-down ACC-style radar display showing vehicle positions around the host car. It runs on a dedicated Raspberry Pi 5 with Hailo AI HAT+ 2, independent from the existing openTPT telemetry system.

The display aesthetic is modelled on the ACC/iRacing proximity radar — host vehicle centred, top-down vehicle-frame-fixed view, coloured contact blips with velocity vectors and trail ghosting, coverage cone overlay.

---

## Pi 5 USB Architecture

The Pi 5 uses the RP1 south bridge for USB. The four physical ports are on two internal buses, not four independent controllers:

```
RP1 USB 3.0 controller  →  USB 3.0 port 1 (top)
                         →  USB 3.0 port 2 (bottom)

RP1 USB 2.0 controller  →  USB 2.0 port 1 (top)
                         →  USB 2.0 port 2 (bottom)
```

The two USB 3.0 ports share one controller. The two USB 2.0 ports share the other. There are two USB buses total, not four.

**Bandwidth is not the constraint.** OV9281 at 120fps 720p MJPG is approximately 20-30 Mbps per camera depending on scene complexity. Four cameras is 80-120 Mbps total -- well within USB 2.0's 480 Mbps ceiling, let alone USB 3.0's 5 Gbps. The cameras are USB 2.0 devices regardless of which port they connect to.

**The practical constraint is RP1 interrupt and scheduling overhead** from four cameras generating concurrent frame transfers on one controller. Manageable on Pi 5 with Hailo handling inference offload, but worth profiling during bench phase.

### USB Port Allocation

```
USB 3.0 port 1 ──► Powered 2-port USB 2.0 hub ──► Camera LEFT_A
                                                 └──► Camera LEFT_B

USB 3.0 port 2 ──► Powered 2-port USB 2.0 hub ──► Camera RIGHT_A
                                                 └──► Camera RIGHT_B

USB 2.0 port 1 ──► USB-CAN adapter (radar fusion, future, stub now)

USB 2.0 port 2 ──► Spare
```

All four cameras share the USB 3.0 controller. In Config A (single camera per side), one camera per USB 3.0 port, no hubs required.

### Why Powered Hubs

- OV9281 cameras are USB 2.0 devices -- USB 3.0 ports give no speed benefit
- Powered hubs avoid drawing camera power from Pi's current-limited USB ports
- Powered hubs with quality regulators are more stable on vehicle 12V supply than bus-powered
- One USB cable per side from hub to Pi -- cleaner routing than four individual cables to cabin
- Camera cables terminate at the hub at the mount point, shorter runs to each camera

### Hub Specification

Small powered USB 2.0 hub per side. Requirements:
- External power input (not bus-powered)
- 2 ports minimum per hub
- Per-port power switching preferred but not essential
- Compact form factor for mounting alongside cameras
- Industrial or semi-industrial preferred for temperature tolerance

---

## Hardware Bill of Materials

### Config A — Single Camera Per Side

| Component | Qty | Source | Notes |
|---|---|---|---|
| Raspberry Pi 5 8GB | 1 | The Pi Hut | Dedicated unit |
| Raspberry Pi AI HAT+ 2 | 1 | The Pi Hut | Hailo-10H 40 TOPS, PCIe, Pi 5 only |
| Argon THRML 30mm Active Cooler | 1 | The Pi Hut | Verify stacking with AI HAT+ 2 spacers |
| Waveshare 4inch DSI LCD (C) | 1 | The Pi Hut / Waveshare | 720x720, IPS, 10-point touch, optical bonding |
| DSI-Cable-12cm (22-pin, Pi 5) | 1 | Waveshare | Confirm included, order separately if not |
| JST-PH 4-pin cable | 1 | Check openTPT parts first | Display power + I2C touch, bypasses pogo pins |
| Kayeton KYT-U100-GS2L waterproof | 2 | Kayeton direct | OV9281, 120fps, 720p, global shutter, monochrome |
| M12 lens 1.39mm (~180°) | 2 + 2 spare | Kayeton direct | Specify at order time |
| M12 lens 1.7mm (~130°) | 2 + 2 spare | Kayeton direct | Order both, test on vehicle |
| M12 lens spanner | 1 | Any | Prevent vibration loosening |
| USB-A cable 2m | 2 | Any | Camera to hub at mount point |
| USB-A cable 3m | 2 | Any | Hub to Pi in cabin |
| 12V to USB-C PD buck converter 5V/5A | 1 | Any | Vehicle 12V to Pi 5 |
| SD card 32GB Samsung/SanDisk Endurance | 1 | Any | Power-cut tolerance |
| RAM cross bar clamp mounts | 2 | RAM Mounts | Roof rack, no drilling |
| RAM ball heads 1/4" thread | 2 | RAM Mounts | 1/4" mates with Kayeton case thread |
| Hot Wheels cars varied | 6-10 | Any | Bench testing |
| Digital calipers | 1 | Any | Measure Hot Wheels width |

### Config B Additions — Dual Camera Per Side

| Component | Qty | Notes |
|---|---|---|
| Kayeton KYT-U100-GS2L waterproof | 2 more (4 total) | |
| M12 lens pairs | 2 more pairs | Match focal length to first pair |
| Powered 2-port USB 2.0 hub | 2 | One per side, external power input |
| 12V to USB power cable for hubs | 2 | Power hubs from vehicle supply |
| USB-A cable 2m | 2 more (4 total camera-to-hub) | |
| Rigid baseline mount plates | 2 | 3D print PETG on Ender 3, one per side |

---

## Display Connection

### Hardware

- **Video:** DSI-Cable-12cm into 22-pin DSI1 port on Pi 5 (not 15-pin FPC -- Pi 3/4 only)
- **Power + Touch:** JST-PH 4-pin wired cable, display 4-pin header to Pi 5 GPIO
- **Pogo pins:** Not used. Pi 5 has lower-profile GPIO header than Pi 4, pogo contact unreliable

### 4-Pin Header Pinout

| Pin | Signal | Pi 5 GPIO |
|---|---|---|
| 1 | 5V | Pin 2 or 4 (5V) |
| 2 | GND | Pin 6 (GND) |
| 3 | SDA | GPIO 2, Pin 3 |
| 4 | SCL | GPIO 3, Pin 5 |

I2C0 is the display default (DIP switch factory setting). GPIO 2/3 are I2C0.

### Driver Installation

```bash
git clone https://github.com/waveshare/Waveshare-DSI-LCD
cd Waveshare-DSI-LCD
uname -a                          # Note kernel version
cd <kernel_version>/64
sudo bash ./WS_xinchDSI_MAIN.sh 40C I2C0
sudo reboot
```

### config.txt

```
dtoverlay=vc4-kms-v3d
dtoverlay=vc4-kms-dsi-waveshare-panel,4_0_inchC
```

### Kernel Pinning

```bash
# In install.sh — prevent silent kernel updates breaking display driver
sudo apt-mark hold raspberrypi-kernel
sudo apt-mark hold raspberrypi-kernel-headers
```

Update kernel deliberately: unhold, update, reinstall Waveshare driver, rehold.

---

## Range Estimation Strategy

### Method 1 — Monocular Known-Width (v1, both configs)

```
range = (known_real_width * focal_length_pixels) / bounding_box_width_pixels
```

Focal length in pixels from lens calibration. Known width from config. Orientation handling: switch to height-based estimate when bounding box aspect ratio indicates head-on approach. `MONO_ORIENTATION_THRESHOLD` controls crossover.

Accuracy: ±10-15%. Sufficient for proximity display. **Makes Config A a complete ranging system.**

### Method 2 — Stereo Disparity (v2, Config B only)

OpenCV StereoBM/SGBM on rectified stereo pairs. 60mm fixed baseline reliable at 3-8m, monocular fallback beyond. Overrides monocular for in-range targets when active.

### Method 3 — Radar Fusion (v3, future)

Passive CAN tap on openTPT can_b1_1. Precise range and closing velocity on rear arc. Overrides camera methods for rear arc contacts.

---

## Camera Configurations

### Config A — Single Camera Per Side

One OV9281 per side, one camera per USB 3.0 port. No hubs required.

```
USB 3.0 port 1 → Camera LEFT   (direct, no hub)
USB 3.0 port 2 → Camera RIGHT  (direct, no hub)
```

Coverage: 180° (1.39mm) or 130° (1.7mm) per side.
Range: Monocular known-width.
V1 deployment target.

### Config B — Dual Camera Per Side

Two OV9281 per side on 3D-printed PETG rigid baseline mount.

```
USB 3.0 port 1 → Powered hub → Camera LEFT_A + Camera LEFT_B
USB 3.0 port 2 → Powered hub → Camera RIGHT_A + Camera RIGHT_B
```

Coverage: Stereo overlap zone ~120-140° per side.
Range: Monocular baseline, stereo disparity where reliable, fused.
Sync: Software timestamp pairing at 120fps, 16ms acceptance window.

---

## Bench Test Plan — Hot Wheels Scale

### Scale Reference (1:64)

Measure actual test car with calipers. Set as `BENCH_OBJECT_WIDTH_MM`.

| Real world | Bench equivalent |
|---|---|
| 2m | 31mm |
| 5m | 78mm |
| 10m | 156mm |
| 20m | 313mm |
| 30m | 469mm |

### Bench Setup

- White or grey flat surface, 600mm x 1200mm minimum
- OV9281 on articulated arm at door-mirror equivalent height and angle
- Even diffuse lighting, no strong shadows
- Fixed Hot Wheels at centre as host vehicle representation

### Detector Strategy

**Contour detection (fast start):** OpenCV background subtraction on static surface. No training required. Enable via `BENCH_DETECTOR = "contour"`. Use for ranging and tracking validation.

**YOLO fine-tune:** 50-100 labelled frames, 10 epochs. Use when validating Hailo inference pipeline specifically.

### Test Sequence

1. Lens calibration — derive focal_length_pixels
2. Monocular range accuracy — known positions vs estimates
3. Multi-target static — three cars simultaneously
4. Tracking continuity — ID stability through traverse and occlusion
5. Orientation sensitivity — side-on to head-on, verify height fallback
6. Display end-to-end — BENCH_TEST_MODE on, blip positions match physical
7. Config B stereo — range vs ruler ground truth (when second pair available)
8. USB scheduling profiling — four cameras concurrent, CPU interrupt overhead

---

## Repository Structure

```
open-PROX/
├── main.py
├── config.py
├── CLAUDE.md                  # This document
├── requirements.txt
├── install.sh                 # Kernel hold + Waveshare driver + udev rules
├── ingest/
│   ├── camera_ingestor.py     # USB capture, timestamp on buffer arrival
│   └── sync_engine.py         # Stereo timestamp pairing (Config B)
├── detect/
│   ├── hailo_detector.py      # HailoRT YOLO-nano inference
│   ├── contour_detector.py    # Background subtraction (bench)
│   └── lens_model.py          # Fisheye/rectilinear, pixel-to-angle
├── range/
│   ├── mono_range.py          # Known-width monocular range estimation
│   └── stereo_depth.py        # Stereo disparity (Config B)
├── track/
│   ├── sort_tracker.py        # SORT with Kalman filters
│   └── track_store.py         # Contact list, coast/drop logic
├── fusion/
│   └── fusion_engine.py       # Passthrough stub, radar fusion later
├── display/
│   ├── renderer.py            # Pygame 720x720 display loop
│   ├── contact_blip.py        # Blip, trail ghosting, range label
│   ├── coverage_cone.py       # Orange coverage overlay
│   └── vehicle_icon.py        # Host vehicle centred
├── calibration/
│   ├── alignment_tool.py      # Live split view, aim verification
│   ├── stereo_calibrator.py   # Checkerboard capture, OpenCV calibration
│   └── calibration_store.py   # Rectification maps to disk
└── tools/
    ├── jitter_analyser.py     # USB timestamp delta histogram
    ├── usb_profiler.py        # CPU interrupt overhead with N cameras
    ├── synthetic_targets.py   # Fake contacts for display dev
    └── quick_sync.sh
```

---

## Configuration (config.py)

```python
# ── Camera ─────────────────────────────────────────────────────────
CAMERA_CONFIG = "single"        # "single" | "dual"

# Config A
CAMERA_LEFT_DEVICE = "/dev/video-left"
CAMERA_RIGHT_DEVICE = "/dev/video-right"

# Config B
CAMERA_LEFT_A_DEVICE = "/dev/video-left-a"
CAMERA_LEFT_B_DEVICE = "/dev/video-left-b"
CAMERA_RIGHT_A_DEVICE = "/dev/video-right-a"
CAMERA_RIGHT_B_DEVICE = "/dev/video-right-b"

CAMERA_FPS = 120
CAMERA_RESOLUTION = (1280, 720)

# ── Stereo sync (Config B) ─────────────────────────────────────────
SYNC_WINDOW_MS = 16.0
SYNC_BUFFER_FRAMES = 5
SYNC_DETECTION_RATE = 30

# ── Lens ───────────────────────────────────────────────────────────
LENS_TYPE = "fisheye"           # "fisheye" | "rectilinear"
LENS_FOV_DEG = 180.0
STEREO_BASELINE_MM = 60.0

# ── Monocular range ────────────────────────────────────────────────
MONO_RANGE_ENABLED = True
MONO_OBJECT_WIDTH_M = 1.9
MONO_OBJECT_HEIGHT_M = 1.5
MONO_MIN_BOX_WIDTH_PX = 20
MONO_ORIENTATION_THRESHOLD = 0.6

# ── Bench test ─────────────────────────────────────────────────────
BENCH_TEST_MODE = False
BENCH_OBJECT_WIDTH_MM = 30.0    # Measure with calipers
BENCH_OBJECT_HEIGHT_MM = 14.0
BENCH_DETECTOR = "hailo"        # "hailo" | "contour"
BENCH_DISPLAY_RANGE_M = 0.5

# ── Detection ──────────────────────────────────────────────────────
DETECTION_CONFIDENCE_MIN = 0.45
DETECTION_CLASSES = [2, 3, 5, 7]  # COCO car, motorcycle, bus, truck

# ── Tracking ───────────────────────────────────────────────────────
TRACK_COAST_MS = 500
TRACK_DROP_MS = 1000
TRACK_MAX_DISTANCE_M = 30.0

# ── Display ────────────────────────────────────────────────────────
DISPLAY_WIDTH = 720
DISPLAY_HEIGHT = 720
DISPLAY_FPS = 30
DISPLAY_RANGE_M = 25.0
TRAIL_FRAMES = 8
THRESH_AMBER_KPH = 15.0
THRESH_RED_KPH = 30.0

# ── Radar fusion stub ──────────────────────────────────────────────
RADAR_FUSION_ENABLED = False
RADAR_CAN_CHANNEL = "can_b1_1"
RADAR_DBC_PATH = "opendbc/toyota_prius_2017_adas.dbc"
```

---

## Track Data Structure

```python
{
    'id': int,
    'side': 'LEFT' | 'RIGHT' | 'BOTH',
    'angle_deg': float,
    'range_m': float | None,
    'range_method': 'mono' | 'stereo' | 'radar' | None,
    'range_confidence': float,
    'velocity': (float, float),
    'closing_kph': float,
    'confidence': float,
    'age_frames': int,
    'last_seen_ns': int,
    'state': 'ACTIVE' | 'COASTED' | 'LOST',
    'sources': set,
    'bbox': (x, y, w, h),
    'orientation': 'SIDE' | 'HEAD_ON' | 'UNKNOWN',
}
```

---

## Build Phases

### Phase 0 — Display Mock (START HERE, desktop only)
Synthetic targets, full visual design. No hardware required.

### Phase 1 — Lens Calibration and Alignment Tool
Derives focal_length_pixels. Required before any range estimation.

### Phase 2 — Single Camera Pipeline with Monocular Range (Config A)
Camera ingest, detection, monocular range. Both sides live. Bench tests 1-6.

### Phase 3 — Tracking
SORT tracker, persistent IDs, coasting, trail ghosting. Bench test 4.

### Phase 4 — USB Profiling (Config B preparation)
Add `usb_profiler.py` — run four cameras concurrently, measure CPU interrupt overhead, confirm scheduling headroom before committing to Config B hardware.

### Phase 5 — Vehicle Installation (Config A)
RAM mount, cable routing, alignment tool on vehicle, real-world validation.

### Phase 6 — Dual Camera Pipeline with Stereo Depth (Config B)
Powered hubs, second camera pair, sync engine, stereo calibration, disparity. Bench test 7-8.

### Phase 7 — Radar Fusion (future)
Passive CAN tap, FusionEngine implementation.

---

## Known Constraints

| Issue | Config | Mitigation |
|---|---|---|
| All 4 cameras share USB 3.0 controller | B | Bandwidth fine, profile interrupt overhead in Phase 4 |
| Powered hubs need vehicle 12V feed | B | Tap vehicle supply alongside Pi buck converter |
| Pogo pins unreliable on Pi 5 | Both | JST 4-pin wired header, pogo pins unused |
| Waveshare driver kernel-version specific | Both | Pin kernel in install.sh |
| Monocular range degrades head-on | Both | Height fallback, orientation detection |
| 60mm stereo baseline limits range >10m | B | Monocular fallback, radar fusion in v3 |
| No hardware sync OV9281 UVC | B | Software timestamp sync at 120fps |
| YOLO not trained on Hot Wheels | Both | Contour detector for bench phase |
| MJPG only at 120fps | Both | Timestamp before decode |
| Argon cooler + AI HAT+ 2 stacking | Both | Verify before ordering |

---

## Interface with openTPT

Proximity Pi listens passively on openTPT's can_b1_1 (RX only, no TX) when radar fusion active. Neither system depends on the other.

Future optional: proximity Pi exposes UDP socket broadcasting contact list for openTPT lateral awareness overlay.

---

## NOT In Scope

- Audio or haptic alerts (display only for v1)
- Active intervention
- Forward arc detection
- Public road use
- IMU/GPS heading-up display rotation (v2)
