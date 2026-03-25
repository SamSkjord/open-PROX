# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Summary

open-PROX is a real-time vehicle proximity awareness system for motorsport track days. It runs on a Raspberry Pi 5 with Hailo AI HAT+ 2, using side-mounted fisheye cameras to detect nearby vehicles and render an ACC-style top-down proximity radar on a 720x720 DSI LCD.

The full project plan lives in `open-PROX-project-plan-v5.md`.

## Tech Stack

- **Platform:** Raspberry Pi 5 (2GB, upgrading to 8GB if needed) + Hailo-10H AI HAT+ 2 (40 TOPS)
- **Language:** Python
- **Vision:** OpenCV (capture, calibration, stereo), HailoRT (YOLOv8m inference)
- **Display:** Pygame (720x720, 60fps render loop)
- **Cameras:** OV9281 global shutter monochrome, 120-degree FOV, CSI (picamera2) or USB (V4L2) via config
- **Display hardware:** Waveshare 4" DSI LCD (C), connected via DSI + JST-PH 4-pin (not pogo pins)

## Commands

```bash
# Run on desktop (synthetic targets, no hardware needed)
python main.py

# Dependencies (desktop)
pip install -r requirements.txt

# Install (on Pi 5 only)
sudo bash install.sh        # Kernel pin + Waveshare driver + udev rules
```

## Pi Setup (Raspbian Lite)

Raspbian Lite has no X11/Wayland - pygame renders via SDL2 KMSDRM directly to the DSI framebuffer.

```bash
# Install SDL2 and Python dev headers
sudo apt-get install -y libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev python3-dev

# Create venv and build pygame from source (must link against system SDL2 for KMSDRM)
python3 -m venv ~/prox-env
~/prox-env/bin/pip install --no-binary pygame pygame

# Deploy code (from dev machine, no rsync on Pi)
scp -r display/ tools/ *.py requirements.txt pi@<PI_IP>:~/open-PROX/

# Run on Pi
cd ~/open-PROX && SDL_VIDEODRIVER=kmsdrm ~/prox-env/bin/python3 main.py
```

**Key detail:** The pip wheel for pygame does not include KMSDRM support. You must `--no-binary pygame` to compile against the system SDL2 libs.

## Hailo AI HAT+ 2 Setup

```bash
# Install Hailo-10H metapackage (driver, runtime, Python bindings, TAPPAS)
sudo apt-get install -y hailo-h10-all

# Blacklist the Hailo-8 driver (conflicts with Hailo-10H driver over sysfs name)
echo 'blacklist hailo_pci' | sudo tee /etc/modprobe.d/hailo-blacklist.conf

# Symlink system hailo_platform into venv (installed to /usr/lib/python3/dist-packages)
SITE=$(~/prox-env/bin/python3 -c 'import site; print(site.getsitepackages()[0])')
ln -sf /usr/lib/python3/dist-packages/hailo_platform $SITE/hailo_platform

# Also need numpy in venv for hailo_platform
~/prox-env/bin/pip install numpy

# Verify
hailortcli fw-control identify
~/prox-env/bin/python3 -c "from hailo_platform import VDevice; VDevice()"
```

**Key detail:** Both `hailo_pci` (Hailo-8) and `hailo1x_pci` (Hailo-10H) drivers ship in the package. They conflict on the `hailo_chardev` sysfs class name. Blacklisting `hailo_pci` is required for `/dev/hailo0` to appear.

**PCIe Gen3 required:** The AI HAT+ 2 requires explicit Gen3 enablement in config.txt: `dtparam=pciex1_gen=3`. Without this, PCIe link training is unreliable and the Hailo firmware upload fails intermittently ("Timeout waiting for firmware file on stage 2/3"). See https://www.raspberrypi.com/documentation/computers/ai.html#PCIe-Gen-3

## Pipeline Architecture

```
Camera Ingest → Detection → Range Estimation → Tracking → Fusion → Display
```

1. **Ingest** (`ingest/csi_camera.py`, `ingest/camera.py`): CSI capture via picamera2 (OV9281 monochrome, RGB888 output) or USB V4L2 at 1280x720. Monotonic timestamps on buffer arrival. `CAM_TYPE` in config selects backend.
2. **Detect** (`detect/yolo.py`): YOLOv8m on Hailo-10H via InferModel API. Runs in a background thread to prevent DMA conflicts with KMSDRM display. NMS postprocessing on-device. Filters to vehicle classes only (car, motorcycle, bus, truck). Auto-recovers on Hailo session drops.
3. **Range** (`range/monocular.py`): Known-width estimation (`range = width_m * focal_px / bbox_px`). Bearing from pixel position using fisheye FOV mapping. Stereo disparity (v2, Config B, future). Radar fusion (v3, future).
4. **Track** (`track/sort.py`): SORT with 4-state Kalman filter (angle, range, d_angle, d_range). Hungarian assignment with greedy fallback. Persistent IDs, velocity/closing speed estimation. Coasting 500ms (2500ms if occluded by adjacent track), drop after 1000ms.
5. **Fusion** (`fusion/`): Not yet implemented. Future radar CAN integration.
6. **Display** (`display/renderer.py`): ACC-style proximity radar with camera view toggle. Prox view: range rings, crosshairs, proximity glow, trails, blips, host vehicle, HUD. Camera view: letterboxed feed with detection boxes and range labels.

## Display Architecture (Phase 0 - implemented)

The display replicates the ACC proximity radar aesthetic:

- **Renderer** (`display/renderer.py`): Pygame 720x720 orchestrator. Pre-renders crosshairs at init. Manages trail history per track ID. Composites layers: range rings -> crosshairs -> coverage cones -> proximity glow -> trails -> blips -> host vehicle -> HUD. Touch-and-hold 2s cycles camera views (RIGHT/LEFT), quick tap returns to prox radar.
- **Contact blips** (`display/contact_blip.py`): White rotated car-shaped polygons. Heading derived from velocity vector. Coasted contacts rendered in grey.
- **Proximity glow** (`display/proximity_glow.py`): Orange radial glow around contacts within `GLOW_RANGE_M`. Intensity and radius scale with proximity.
- **Coverage cones** (`display/coverage_cone.py`): Semi-transparent orange FOV arcs (left at 270°, right at 90°). Off by default.
- **Vehicle icon** (`display/vehicle_icon.py`): Light-outlined host car silhouette at centre.
- **Synthetic targets** (`tools/synthetic_targets.py`): Five moving contacts for display development - overtakers, closer, stationary, intermittent.

Coordinate system: centre = host vehicle, up = forward. Polar `(angle_deg, range_m)` where 0° = ahead, 90° = right, 180° = behind, 270° = left. `DISPLAY_RANGE_M` maps to half the display width.

## Camera Configurations

- **Current:** OV9281 monochrome CSI camera (120-degree FOV, global shutter), connected to CAM0 port via 22-pin FPC. Pi 5 config.txt requires `dtoverlay=ov9281,cam0` (cam0 parameter maps to the port not used by DSI display).
- **Config A (v1 target):** One camera per side, monocular range only.
- **Config B (v2):** Two cameras per side. Adds stereo depth.

USB cameras with software timestamp sync - MIPI CSI-2 cable length (~150mm limit) rules out CamArray for cabin-mounted Pi with cameras at bodywork. Permanent install uses through-mount: bare board cameras in ASA enclosures, only M12 lens protruding through grommetted bodywork hole.

## Build Phases

0. **Display Mock** - Complete. ACC-style radar with synthetic targets.
1. **Lens Calibration** - Deferred. 6108 lens won't focus; 1.7mm fisheye attached. Checkerboard calibration attempted (high RMS). Empirical bearing LUT planned for on-car validation.
2. **Single Camera Pipeline** (Config A) - Complete (single side). CSI ingest via picamera2, YOLOv8m detection on Hailo-10H (threaded), monocular range estimation. Camera view with detection boxes available via touch-and-hold. Tested on Pi 5 with OV9281 CSI camera.
3. **Tracking** - Complete. SORT tracker with Kalman filters, persistent IDs, velocity/closing speed estimation, coasting (500ms normal, 2500ms occluded), occlusion detection. Tested with synthetic targets.
4. **USB Profiling** (Config B prep) - Four cameras concurrent, measure interrupt overhead.
5. **Vehicle Installation** (Config A) - RAM mounts, alignment tool on vehicle.
6. **Dual Camera + Stereo** (Config B) - Powered hubs, sync engine, stereo calibration.
7. **Radar Fusion** (future) - Passive CAN tap on openTPT can_b1_1.

## Key Config Values

Configuration lives in `config.py`. Sections: display, blip geometry, proximity glow, range rings, coverage cones, tracking thresholds, camera, detection, range estimation.

- `DISPLAY_RANGE_M`: Radar radius - 5m (tight ACC-style proximity view)
- `DISPLAY_FPS`: Render rate - 60fps
- `GLOW_RANGE_M`: Orange proximity warning threshold - 2m
- `COVERAGE_CONES_ENABLED`: Camera FOV overlay - off by default
- `OCCLUDED_COAST_MS`: Extended coast when adjacent track present - 2500ms
- `CAM_TYPE`: Camera backend - "csi" (picamera2) or "usb" (V4L2)
- `CSI_RIGHT_DEVICE` / `CSI_LEFT_DEVICE`: picamera2 camera index (-1 = not connected)
- `CAM_RIGHT_DEVICE` / `CAM_LEFT_DEVICE`: V4L2 device index (-1 = not connected)
- `DETECT_MAX_FPS`: Detection rate cap - 0 = unlimited
- `HAILO_MODEL_PATH`: YOLOv8m HEF for Hailo-10H
- `DETECT_CONFIDENCE`: YOLO confidence threshold - 0.5
- `VEHICLE_CLASS_IDS`: COCO classes {2, 3, 5, 7} (car, motorcycle, bus, truck)
- `VEHICLE_WIDTH_M`: Assumed vehicle width for monocular range - 1.8m
- `FOCAL_LENGTH_PX`: Approximate focal length for 1.7mm fisheye - 500px

## Track Data Structure

Each tracked contact is a dict with: `id`, `side` (LEFT/RIGHT/BOTH), `angle_deg`, `range_m`, `range_method` (mono/stereo/radar/synthetic), `velocity` (vx, vy in m/s), `closing_kph`, `state` (ACTIVE/COASTED/LOST), `occluded` (bool), `orientation` (SIDE/HEAD_ON/UNKNOWN), `bbox`.

## Design Decisions

- Timestamps captured on buffer arrival, before MJPG decode.
- Monocular range: `range = (known_width * focal_length_px) / bbox_width_px`, switching to height-based when aspect ratio indicates head-on approach.
- Stereo sync is software timestamp pairing (no hardware sync on OV9281 UVC), 16ms acceptance window.
- Waveshare display worked out-of-the-box on kernel 6.12.75 without pinning. Kernel hold removed.
- Detection runs in a background thread - Hailo PCIe DMA and KMSDRM page flips conflict when on the same thread, causing HAILO_COMMUNICATION_CLOSED errors.
- Hailo-10H has no onboard flash - firmware (~90MB) is DMA-transferred from host over PCIe every boot. Requires `dtparam=pciex1_gen=3` for reliable link training. SIGTERM handler ensures clean VDevice release on shutdown.
- Pi 5 CSI/DSI port mapping: `dtoverlay=ov9281,cam0` maps camera to the port NOT used by the Waveshare DSI display. Without `cam0`, both land on the same port.
- picamera2 must be symlinked into the venv along with its dependencies (libcamera, videodev2, prctl, etc.) since it's installed as a system package.
- HUD shows Hailo status (INIT/DOWN/RESET) at bottom of prox view when detection is unavailable. Detect thread retries every 10s with PCIe bus reset fallback.
- System is fully independent from openTPT; future radar fusion is passive CAN RX only.
- Occlusion handling: extended coast (2500ms vs 500ms) when track drops with adjacent active track present. No separate occlusion reasoning layer.
