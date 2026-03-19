# open-PROX

Real-time vehicle proximity awareness system for motorsport track days.

open-PROX provides an ACC/iRacing-style top-down radar display showing nearby vehicle positions around the host car. Side-mounted fisheye cameras detect vehicles, estimate range and bearing, and render coloured contact blips with velocity vectors and trail ghosting on a cockpit-mounted 720x720 display.

![Status](https://img.shields.io/badge/status-pre--release-orange)
![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%205-red)
![License](https://img.shields.io/badge/license-TBD-lightgrey)

## How It Works

```
Cameras ─► Ingest ─► Detection (Hailo AI) ─► Range Estimation ─► Tracking ─► Display
```

1. **Ingest** — USB capture from side-mounted OV9281 global shutter cameras at 120fps 720p monochrome
2. **Detection** — YOLO-nano inference offloaded to Hailo-10H (40 TOPS) via HailoRT, with a contour-based fallback for bench testing
3. **Range** — Monocular known-width estimation (v1), stereo disparity (v2), radar fusion (v3 future)
4. **Tracking** — SORT with Kalman filters, persistent contact IDs, coast/drop lifecycle
5. **Display** — Pygame 720x720 at 30fps: host vehicle centred, coloured blips (green/amber/red by closing speed), velocity vectors, trail ghosting, coverage cone overlay

## Hardware

| Component | Purpose |
|---|---|
| Raspberry Pi 5 (8GB) | Compute |
| Hailo AI HAT+ 2 (Hailo-10H) | 40 TOPS inference accelerator |
| Waveshare 4" DSI LCD (C) | 720x720 IPS cockpit display |
| Kayeton KYT-U100-GS2L (x2 or x4) | OV9281 waterproof cameras, 120fps global shutter |
| M12 fisheye lens (1.39mm 180° or 1.7mm 130°) | Wide-angle coverage per side |
| RAM cross bar clamp mounts | Roof rack mounting, no drilling |

Two camera configurations are supported:

- **Config A** — One camera per side (v1 target). Monocular range estimation. No hubs needed.
- **Config B** — Two cameras per side on a rigid baseline mount. Adds stereo depth (60mm baseline, reliable 3-8m). Requires powered USB 2.0 hubs.

See the full BOM in [open-PROX-project-plan-v5.md](open-PROX-project-plan-v5.md).

## Installation

### Prerequisites

- Raspberry Pi 5 with Raspberry Pi OS (64-bit)
- Hailo AI HAT+ 2 installed and recognised
- Waveshare 4" DSI LCD (C) connected via DSI + JST-PH 4-pin header

### Setup

```bash
git clone https://github.com/SamSkjord/open-PROX.git
cd open-PROX

# Install system dependencies, display driver, kernel pin, and udev rules
sudo bash install.sh

# Install Python dependencies
pip install -r requirements.txt
```

### Run

```bash
python main.py
```

### Desktop Development (no hardware)

Phase 0 uses synthetic targets for display development. No cameras or Pi hardware required — runs on any machine with Python and Pygame.

## Configuration

All settings live in `config.py`. Key options:

| Setting | Default | Purpose |
|---|---|---|
| `CAMERA_CONFIG` | `"single"` | `"single"` (Config A) or `"dual"` (Config B) |
| `BENCH_TEST_MODE` | `False` | Enable bench testing with 1:64 scale Hot Wheels |
| `BENCH_DETECTOR` | `"hailo"` | `"hailo"` or `"contour"` (no training needed) |
| `DISPLAY_RANGE_M` | `25.0` | Radar display radius in metres |
| `DETECTION_CONFIDENCE_MIN` | `0.45` | Minimum detection confidence |
| `TRACK_COAST_MS` | `500` | Time before coasted contact is dropped |

Camera devices use udev symlinks (`/dev/video-left`, `/dev/video-right`, etc.) for stable identification across reboots.

## Build Phases

| Phase | Description | Hardware Required |
|---|---|---|
| 0 | Display mock with synthetic targets | None (desktop) |
| 1 | Lens calibration and alignment tool | Camera + Pi |
| 2 | Single camera pipeline with monocular range | Config A |
| 3 | SORT tracking, persistent IDs, trail ghosting | Config A |
| 4 | USB profiling for 4-camera scheduling | 4 cameras |
| 5 | Vehicle installation and real-world validation | Config A on vehicle |
| 6 | Dual camera pipeline with stereo depth | Config B |
| 7 | Radar fusion via CAN bus | CAN adapter |

## Range Estimation

Three methods, layered by availability:

1. **Monocular known-width** (v1) — `range = (real_width * focal_length_px) / bbox_width_px`. Switches to height-based estimate when bounding box aspect ratio indicates head-on approach. Accuracy ~10-15%.
2. **Stereo disparity** (v2, Config B) — OpenCV StereoBM/SGBM on rectified pairs. 60mm baseline reliable at 3-8m, monocular fallback beyond.
3. **Radar fusion** (v3, future) — Passive CAN tap on vehicle radar. Precise range and closing velocity on rear arc.

## Bench Testing

Bench tests use 1:64 scale Hot Wheels on a flat surface. Set `BENCH_TEST_MODE = True` and measure actual car width with calipers (`BENCH_OBJECT_WIDTH_MM`). The contour detector (`BENCH_DETECTOR = "contour"`) requires no model training — useful for validating range estimation and tracking before the Hailo pipeline is ready.

## Relation to openTPT

open-PROX is fully independent from the [openTPT](https://github.com/SamSkjord/openTPT) telemetry system. When radar fusion is active (v3), the proximity Pi passively listens on openTPT's `can_b1_1` CAN bus (RX only, no TX). Neither system depends on the other.

## Not In Scope (v1)

- Audio or haptic alerts
- Active intervention
- Forward arc detection
- Public road use
- IMU/GPS heading-up rotation
