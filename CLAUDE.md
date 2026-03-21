# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Summary

open-PROX is a real-time vehicle proximity awareness system for motorsport track days. It runs on a Raspberry Pi 5 with Hailo AI HAT+ 2, using side-mounted fisheye cameras to detect nearby vehicles and render an ACC-style top-down proximity radar on a 720x720 DSI LCD.

The full project plan lives in `open-PROX-project-plan-v5.md`.

## Tech Stack

- **Platform:** Raspberry Pi 5 (2GB, upgrading to 8GB if needed) + Hailo-10H AI HAT+ 2 (40 TOPS)
- **Language:** Python
- **Vision:** OpenCV (capture, calibration, stereo), HailoRT (YOLO-nano inference)
- **Display:** Pygame (720x720, 60fps render loop)
- **Cameras:** Arducam B0332 - OV9281 global shutter monochrome, 120fps 720p MJPG, USB 2.0
- **Display hardware:** Waveshare 4" DSI LCD (C), connected via DSI + JST-PH 4-pin (not pogo pins)

## Commands

```bash
# Run (works on desktop with synthetic targets, no hardware needed)
python main.py

# Dependencies
pip install -r requirements.txt

# Install (on Pi 5 only)
sudo bash install.sh        # Kernel pin + Waveshare driver + udev rules
```

## Pipeline Architecture

```
Camera Ingest → Detection → Range Estimation → Tracking → Fusion → Display
```

1. **Ingest** (`ingest/`): USB capture with buffer-arrival timestamps. Config B adds stereo timestamp pairing (16ms sync window at 120fps).
2. **Detect** (`detect/`): HailoRT YOLO-nano for real targets, contour detector for bench testing. Lens model converts pixel coords to bearing angles.
3. **Range** (`range/`): Monocular known-width estimation (v1, both configs). Stereo disparity (v2, Config B, 60mm baseline, reliable 3-8m). Radar fusion (v3, future).
4. **Track** (`track/`): SORT with Kalman filters. Contacts coast for 500ms (2500ms if occluded), drop after 1000ms.
5. **Fusion** (`fusion/`): Passthrough stub now, future radar CAN integration.
6. **Display** (`display/`): ACC-style proximity radar - white car-shaped blips, orange proximity glow for close contacts, fading crosshairs, subtle range rings. 5m display range.

## Display Architecture (Phase 0 - implemented)

The display replicates the ACC proximity radar aesthetic:

- **Renderer** (`display/renderer.py`): Pygame 720x720 orchestrator. Pre-renders crosshairs at init. Manages trail history per track ID. Composites layers: range rings → crosshairs → coverage cones → proximity glow → trails → blips → host vehicle → HUD.
- **Contact blips** (`display/contact_blip.py`): White rotated car-shaped polygons. Heading derived from velocity vector. Coasted contacts rendered in grey.
- **Proximity glow** (`display/proximity_glow.py`): Orange radial glow around contacts within `GLOW_RANGE_M`. Intensity and radius scale with proximity.
- **Coverage cones** (`display/coverage_cone.py`): Semi-transparent orange FOV arcs (left at 270°, right at 90°). Off by default.
- **Vehicle icon** (`display/vehicle_icon.py`): Light-outlined host car silhouette at centre.
- **Synthetic targets** (`tools/synthetic_targets.py`): Five moving contacts for display development - overtakers, closer, stationary, intermittent.

Coordinate system: centre = host vehicle, up = forward. Polar `(angle_deg, range_m)` where 0° = ahead, 90° = right, 180° = behind, 270° = left. `DISPLAY_RANGE_M` maps to half the display width.

## Camera Configurations

- **Config A (v1 target):** One camera per side, direct to USB 3.0 ports. Monocular range only.
- **Config B (v2):** Two cameras per side via powered USB 2.0 hubs on USB 3.0 ports. Adds stereo depth.

USB cameras with software timestamp sync - MIPI CSI-2 cable length (~150mm limit) rules out CamArray for cabin-mounted Pi with cameras at bodywork. Permanent install uses through-mount: bare board cameras in ASA enclosures, only M12 lens protruding through grommetted bodywork hole.

## Build Phases

0. **Display Mock** - Complete. ACC-style radar with synthetic targets.
1. **Lens Calibration** - Derive focal_length_pixels. Start with 6108 rectilinear (~85°) for clean validation, then swap to 2.1mm fisheye (~155°) for vehicle.
2. **Single Camera Pipeline** (Config A) - Ingest, detection, monocular range, both sides live.
3. **Tracking** - SORT tracker, persistent IDs, coasting (extended to 2500ms when occluded), trail ghosting.
4. **USB Profiling** (Config B prep) - Four cameras concurrent, measure interrupt overhead.
5. **Vehicle Installation** (Config A) - RAM mounts, alignment tool on vehicle.
6. **Dual Camera + Stereo** (Config B) - Powered hubs, sync engine, stereo calibration.
7. **Radar Fusion** (future) - Passive CAN tap on openTPT can_b1_1.

## Key Config Values

Configuration lives in `config.py`. Currently contains display-only settings (Phase 0). Camera, detection, and tracking sections will be added in later phases.

- `DISPLAY_RANGE_M`: Radar radius - 5m (tight ACC-style proximity view)
- `DISPLAY_FPS`: Render rate - 60fps
- `GLOW_RANGE_M`: Orange proximity warning threshold - 2m
- `COVERAGE_CONES_ENABLED`: Camera FOV overlay - off by default
- `OCCLUDED_COAST_MS`: Extended coast when adjacent track present - 2500ms

## Track Data Structure

Each tracked contact is a dict with: `id`, `side` (LEFT/RIGHT/BOTH), `angle_deg`, `range_m`, `range_method` (mono/stereo/radar/synthetic), `velocity` (vx, vy in m/s), `closing_kph`, `state` (ACTIVE/COASTED/LOST), `occluded` (bool), `orientation` (SIDE/HEAD_ON/UNKNOWN), `bbox`.

## Design Decisions

- Timestamps captured on buffer arrival, before MJPG decode.
- Monocular range: `range = (known_width * focal_length_px) / bbox_width_px`, switching to height-based when aspect ratio indicates head-on approach.
- Stereo sync is software timestamp pairing (no hardware sync on OV9281 UVC), 16ms acceptance window.
- Waveshare display driver is kernel-version specific - `install.sh` pins the kernel with `apt-mark hold`.
- System is fully independent from openTPT; future radar fusion is passive CAN RX only.
- Occlusion handling: extended coast (2500ms vs 500ms) when track drops with adjacent active track present. No separate occlusion reasoning layer.
