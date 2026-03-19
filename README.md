# open-PROX

Real-time vehicle proximity awareness system for motorsport track days.

open-PROX provides an ACC-style top-down proximity radar showing nearby vehicle positions around the host car. Side-mounted fisheye cameras detect vehicles, estimate range and bearing, and render white car-shaped blips with orange proximity warnings on a cockpit-mounted 720x720 display.

![Status](https://img.shields.io/badge/status-Phase%200%20complete-blue)
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
5. **Display** — ACC-style proximity radar at 60fps: white car-shaped blips, orange proximity glow, fading crosshairs, 5m range

## Hardware

| Component | Purpose |
|---|---|
| Raspberry Pi 5 (2GB) | Compute (upgrade to 8GB if needed under real load) |
| Hailo AI HAT+ 2 (Hailo-10H) | 40 TOPS inference accelerator |
| Waveshare 4" DSI LCD (C) | 720x720 IPS cockpit display |
| Arducam B0332 (x2 or x4) | OV9281 bare board cameras, 120fps global shutter, USB |
| M12 lenses | 2.1mm fisheye (~155°) for vehicle, 6108 rectilinear (~85°) for bench |
| RAM cross bar clamp mounts | Roof rack mounting, no drilling |

Two camera configurations are supported:

- **Config A** — One camera per side (v1 target). Monocular range estimation. No hubs needed.
- **Config B** — Two cameras per side on a rigid baseline mount. Adds stereo depth (60mm baseline, reliable 3-8m). Requires powered USB 2.0 hubs.

Permanent installation uses through-mount cameras — bare boards in ASA enclosures with only the M12 lens protruding through grommetted bodywork.

See the full BOM in [open-PROX-project-plan-v5.md](open-PROX-project-plan-v5.md).

## Quick Start

```bash
git clone https://github.com/SamSkjord/open-PROX.git
cd open-PROX
pip install -r requirements.txt
python main.py
```

Phase 0 runs on any desktop with Python and Pygame — no Pi or cameras needed. Synthetic targets demonstrate the radar display.

### Pi 5 Installation

```bash
sudo bash install.sh        # Kernel pin + Waveshare driver + udev rules
pip install -r requirements.txt
python main.py
```

## Configuration

All settings live in `config.py`. Key options:

| Setting | Default | Purpose |
|---|---|---|
| `DISPLAY_RANGE_M` | `5.0` | Radar display radius in metres |
| `DISPLAY_FPS` | `60` | Render frame rate |
| `GLOW_RANGE_M` | `2.0` | Orange proximity warning threshold |
| `COVERAGE_CONES_ENABLED` | `False` | Show camera FOV overlay |
| `BLIP_LENGTH_PX` | `32` | Contact car blip size |
| `TRACK_COAST_MS` | `500` | Coast time before dropping contact |
| `OCCLUDED_COAST_MS` | `2500` | Extended coast when occluded by adjacent car |

## Build Phases

| Phase | Description | Hardware Required | Status |
|---|---|---|---|
| 0 | Display mock with synthetic targets | None (desktop) | Complete |
| 1 | Lens calibration and alignment tool | Camera + Pi | Next |
| 2 | Single camera pipeline with monocular range | Config A | |
| 3 | SORT tracking, persistent IDs, trail ghosting | Config A | |
| 4 | USB profiling for 4-camera scheduling | 4 cameras | |
| 5 | Vehicle installation and real-world validation | Config A on vehicle | |
| 6 | Dual camera pipeline with stereo depth | Config B | |
| 7 | Radar fusion via CAN bus | CAN adapter | |

## Range Estimation

Three methods, layered by availability:

1. **Monocular known-width** (v1) — `range = (real_width * focal_length_px) / bbox_width_px`. Switches to height-based estimate when bounding box aspect ratio indicates head-on approach. Accuracy ~10-15%.
2. **Stereo disparity** (v2, Config B) — OpenCV StereoBM/SGBM on rectified pairs. 60mm baseline reliable at 3-8m, monocular fallback beyond.
3. **Radar fusion** (v3, future) — Passive CAN tap on vehicle radar. Precise range and closing velocity on rear arc.

## Bench Testing

Bench tests use 1:64 scale Hot Wheels on a flat surface. Set `BENCH_TEST_MODE = True` and measure actual car width with calipers (`BENCH_OBJECT_WIDTH_MM`). The contour detector (`BENCH_DETECTOR = "contour"`) requires no model training — useful for validating range estimation and tracking before the Hailo pipeline is ready.

Calibration starts with the 6108 rectilinear lens for clean validation of monocular range maths against a ruler, before introducing fisheye distortion with the 2.1mm lens.

## Relation to openTPT

open-PROX is fully independent from the [openTPT](https://github.com/SamSkjord/openTPT) telemetry system. When radar fusion is active (v3), the proximity Pi passively listens on openTPT's `can_b1_1` CAN bus (RX only, no TX). Neither system depends on the other.

## Not In Scope (v1)

- Audio or haptic alerts
- Active intervention
- Forward arc detection
- Public road use
- IMU/GPS heading-up rotation
