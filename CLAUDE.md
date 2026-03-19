# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Summary

open-PROX is a real-time vehicle proximity awareness system for motorsport track days. It runs on a Raspberry Pi 5 with Hailo AI HAT+ 2, using side-mounted fisheye cameras to detect nearby vehicles and render an ACC/iRacing-style top-down radar display on a 720x720 DSI LCD.

The full project plan lives in `open-PROX-project-plan-v5.md`.

## Tech Stack

- **Platform:** Raspberry Pi 5 (8GB) + Hailo-10H AI HAT+ 2 (40 TOPS)
- **Language:** Python
- **Vision:** OpenCV (capture, calibration, stereo), HailoRT (YOLO-nano inference)
- **Display:** Pygame (720x720, 30fps render loop)
- **Cameras:** OV9281 global shutter monochrome, 120fps 720p MJPG, USB 2.0
- **Display hardware:** Waveshare 4" DSI LCD (C), connected via DSI + JST-PH 4-pin (not pogo pins)

## Pipeline Architecture

```
Camera Ingest → Detection → Range Estimation → Tracking → Fusion → Display
```

1. **Ingest** (`ingest/`): USB capture with buffer-arrival timestamps. Config B adds stereo timestamp pairing (16ms sync window at 120fps).
2. **Detect** (`detect/`): HailoRT YOLO-nano for real targets, contour detector for bench testing. Lens model converts pixel coords to bearing angles.
3. **Range** (`range/`): Monocular known-width estimation (v1, both configs). Stereo disparity (v2, Config B, 60mm baseline, reliable 3-8m). Radar fusion (v3, future).
4. **Track** (`track/`): SORT with Kalman filters. Contacts coast for 500ms, drop after 1000ms.
5. **Fusion** (`fusion/`): Passthrough stub now, future radar CAN integration.
6. **Display** (`display/`): Pygame 720x720, host vehicle centred, coloured blips with velocity vectors and trail ghosting, orange coverage cone overlay.

## Camera Configurations

- **Config A (v1 target):** One camera per side, direct to USB 3.0 ports. Monocular range only.
- **Config B (v2):** Two cameras per side via powered USB 2.0 hubs on USB 3.0 ports. Adds stereo depth.

All four cameras share the RP1 USB 3.0 controller. Bandwidth is fine (~80-120 Mbps vs 5 Gbps); the concern is RP1 interrupt/scheduling overhead with four concurrent streams.

## Build Phases (build in this order)

0. **Display Mock** — Synthetic targets, full visual design. Desktop only, no hardware needed. **Start here.**
1. **Lens Calibration** — Derive focal_length_pixels. Required before range estimation.
2. **Single Camera Pipeline** (Config A) — Ingest, detection, monocular range, both sides live.
3. **Tracking** — SORT tracker, persistent IDs, coasting, trail ghosting.
4. **USB Profiling** (Config B prep) — Four cameras concurrent, measure interrupt overhead.
5. **Vehicle Installation** (Config A) — RAM mounts, alignment tool on vehicle.
6. **Dual Camera + Stereo** (Config B) — Powered hubs, sync engine, stereo calibration.
7. **Radar Fusion** (future) — Passive CAN tap on openTPT can_b1_1.

## Key Config Values

Configuration lives in `config.py`. Key values:
- `CAMERA_CONFIG`: `"single"` (Config A) or `"dual"` (Config B)
- `BENCH_TEST_MODE`: enables bench testing with Hot Wheels at 1:64 scale
- `BENCH_DETECTOR`: `"hailo"` or `"contour"` (contour needs no training)
- `MONO_ORIENTATION_THRESHOLD`: controls side-on to head-on crossover (switches width→height estimate)
- `DETECTION_CLASSES`: COCO classes `[2, 3, 5, 7]` (car, motorcycle, bus, truck)
- Camera devices use udev symlinks: `/dev/video-left`, `/dev/video-right`, etc.

## Track Data Structure

Each tracked contact is a dict with: `id`, `side` (LEFT/RIGHT/BOTH), `angle_deg`, `range_m`, `range_method` (mono/stereo/radar), `velocity`, `closing_kph`, `state` (ACTIVE/COASTED/LOST), `orientation` (SIDE/HEAD_ON/UNKNOWN), `bbox`.

## Design Decisions

- Timestamps are captured on buffer arrival, before MJPG decode.
- Monocular range uses `range = (known_width * focal_length_px) / bbox_width_px`, switching to height-based when aspect ratio indicates head-on approach.
- Stereo sync is software timestamp pairing (no hardware sync on OV9281 UVC), 16ms acceptance window.
- Waveshare display driver is kernel-version specific — `install.sh` pins the kernel with `apt-mark hold`.
- Display touch uses I2C0 (GPIO 2/3) via the JST-PH 4-pin header.
- System is fully independent from openTPT; future radar fusion is passive CAN RX only.

## Commands

```bash
# Install (on Pi 5)
sudo bash install.sh        # Kernel pin + Waveshare driver + udev rules

# Run
python main.py

# Dependencies
pip install -r requirements.txt
```
