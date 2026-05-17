# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Summary

open-PROX is a real-time vehicle proximity awareness system for motorsport track days. It runs on a Raspberry Pi 5 with Hailo AI HAT+ 2, using side-mounted cameras to detect nearby vehicles and render an ACC-style top-down proximity radar on a 720x720 DSI LCD.

The full project plan lives in `open-PROX-project-plan-v5.md`.

## Tech Stack

- **Platform:** Raspberry Pi 5 (2GB) + Hailo-10H AI HAT+ 2 (40 TOPS)
- **Language:** Python
- **Vision:** OpenCV (capture, calibration), HailoRT (YOLOv8m inference)
- **Display:** Pygame (720x720, 30fps render loop via SDL2 KMSDRM)
- **Cameras:** OV9281 global shutter monochrome USB camera, 1280x720 MJPG 30fps
- **Display hardware:** Waveshare 4" DSI LCD (C), connected via DSI + JST-PH 4-pin

## Commands

```bash
# Run on desktop (synthetic targets, no hardware needed)
python main.py

# Dependencies (desktop)
pip install -r requirements.txt

# Run on Pi
cd ~/open-PROX && SDL_VIDEODRIVER=kmsdrm ~/prox-env/bin/python3 main.py
```

## Pi Setup (Raspbian Lite)

Raspbian Lite has no X11/Wayland - pygame renders via SDL2 KMSDRM directly to the DSI framebuffer.

```bash
# 1. config.txt (add to [all] section)
dtoverlay=vc4-kms-dsi-waveshare-panel,4_0_inchC

# 2. Update EEPROM (required for reliable Hailo PCIe)
sudo rpi-eeprom-update -a
sudo reboot

# 3. System packages (dkms MUST be installed before hailo)
sudo apt-get update && sudo apt-get full-upgrade -y
sudo apt-get install -y dkms
sudo apt-get install -y \
  libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
  python3-dev build-essential \
  hailo-h10-all

# 4. Blacklist Hailo-8 driver + disable PCIe ASPM
echo 'blacklist hailo_pci' | sudo tee /etc/modprobe.d/hailo-blacklist.conf
sudo sed -i 's/$/ pcie_aspm=off/' /boot/firmware/cmdline.txt
sudo reboot

# 5. Verify Hailo
hailortcli fw-control identify

# 6. Python venv
python3 -m venv ~/prox-env
~/prox-env/bin/pip install --no-binary pygame pygame
~/prox-env/bin/pip install "numpy<2.0" "opencv-python-headless<4.11"

# 7. Symlink hailo into venv
SITE=$(~/prox-env/bin/python3 -c 'import site; print(site.getsitepackages()[0])')
ln -sf /usr/lib/python3/dist-packages/hailo_platform $SITE/hailo_platform

# 8. Deploy code (use git clone, NOT scp - scp from Windows introduces null bytes)
git clone https://github.com/SamSkjord/open-PROX.git ~/open-PROX
# After code changes, use: cd ~/open-PROX && git pull
# IMPORTANT: clear __pycache__ after any redeployment:
find ~/open-PROX -name "__pycache__" -exec rm -rf {} + 2>/dev/null
```

**Key details:**
- The pip wheel for pygame does not include KMSDRM support. You must `--no-binary pygame` to compile against system SDL2 libs.
- `dkms` must be installed BEFORE `hailo-h10-all` or the kernel module won't build properly.
- EEPROM must be updated (`rpi-eeprom-update -a`) for reliable Hailo PCIe HAT+ auto-detection.
- `numpy` must be <2.0 - hailo_platform 5.1.1 uses `numpy.dtype` which was removed in numpy 2.0.
- `opencv-python-headless` must be <4.11 to remain compatible with numpy <2.0.
- Both `hailo_pci` (Hailo-8) and `hailo1x_pci` (Hailo-10H) drivers ship in the package. They conflict on `hailo_chardev`. Blacklisting `hailo_pci` is required for `/dev/hailo0` to appear.
- Do NOT manually set `dtparam=pciex1_gen=3` - the AI HAT+ 2 auto-negotiates Gen3. Forcing it can cause instability.
- Add `pcie_aspm=off` to `/boot/firmware/cmdline.txt` - PCIe power management causes Hailo DMA drops under sustained load.
- Deploy code via `git clone` / `git pull`, NOT `scp` from Windows. SCP introduces null bytes that corrupt Python files. Always clear `__pycache__` after redeployment.
- Multiprocessing uses `spawn` start method (set in `__main__` guard). `fork` causes SIGBUS with KMSDRM.

## Pipeline Architecture

```
Camera Ingest -> Detection -> Range Estimation -> Tracking -> Fusion -> Display
```

1. **Ingest** (`ingest/camera.py`): USB V4L2 capture at 1280x720 MJPG 30fps. Monotonic timestamps on buffer arrival.
2. **Detect** (`detect/yolo.py`): YOLOv8m on Hailo-10H via InferModel API. NMS on-device. Filters to vehicle classes only (car, motorcycle, bus, truck). Pre-allocated bindings (one-time init, reused per frame). Graceful degradation - pipeline continues without detection if Hailo unavailable.
3. **Range** (`range/monocular.py`): Known-width estimation (`range = width_m * focal_px / bbox_px`). Bearing from pixel position using fisheye FOV mapping.
4. **Track** (`track/sort.py`): SORT with 4-state Kalman filter (angle, range, d_angle, d_range). Hungarian assignment with greedy fallback. Persistent IDs, velocity/closing speed estimation. Coasting 500ms (2500ms if occluded by adjacent track), drop after 1000ms.
5. **Fusion** (`fusion/`): Not yet implemented. Future radar CAN integration.
6. **Display** (`display/renderer.py`): ACC-style proximity radar with camera view toggle. Prox view: range rings, crosshairs, trails, blips, host vehicle, HUD. Camera view: letterboxed feed with detection boxes and range labels.

## Display Architecture

- **Renderer** (`display/renderer.py`): Pygame 720x720 orchestrator at 30fps. Pre-renders crosshairs at init (colorkey, no SRCALPHA). Touch-and-hold 2s cycles camera views (RIGHT/LEFT), quick tap returns to prox radar. HUD shows detection status when Hailo is unavailable.
- **Contact blips** (`display/contact_blip.py`): White rotated car-shaped polygons. Heading derived from velocity vector. Coasted contacts rendered in grey. Trail dots drawn directly (no SRCALPHA surfaces).
- **Proximity glow** (`display/proximity_glow.py`): Disabled - GPU-heavy concentric circle drawing causes Hailo PCIe DMA conflicts. Will be re-implemented with pre-rendered sprites.
- **Coverage cones** (`display/coverage_cone.py`): Semi-transparent orange FOV arcs. Off by default.
- **Vehicle icon** (`display/vehicle_icon.py`): Light-outlined host car silhouette at centre.
- **Synthetic targets** (`tools/synthetic_targets.py`): Five moving contacts for desktop development.

Coordinate system: centre = host vehicle, up = forward. Polar `(angle_deg, range_m)` where 0 deg = ahead, 90 deg = right, 180 deg = behind, 270 deg = left. `DISPLAY_RANGE_M` maps to half the display width.

## Camera Configuration

- **Current:** OV9281 monochrome USB camera (120-degree FOV, global shutter), 1280x720 MJPG 30fps.
- **Config A (v1 target):** One camera per side, monocular range only.
- **Config B (v2):** Two cameras per side. Adds stereo depth.

## Build Phases

0. **Display Mock** - Complete. ACC-style radar with synthetic targets.
1. **Lens Calibration** - Deferred. Empirical bearing LUT planned for on-car validation.
2. **Single Camera Pipeline** (Config A) - Complete (single side). USB ingest, YOLOv8m detection on Hailo-10H, monocular range estimation. Camera view with detection boxes available via touch-and-hold.
3. **Tracking** - Complete. SORT tracker with Kalman filters, persistent IDs, velocity/closing speed estimation, coasting, occlusion detection.
4. **USB Profiling** (Config B prep) - Four cameras concurrent, measure interrupt overhead.
5. **Vehicle Installation** (Config A) - RAM mounts, alignment tool on vehicle.
6. **Dual Camera + Stereo** (Config B) - Powered hubs, sync engine, stereo calibration.
7. **Radar Fusion** (future) - Passive CAN tap on openTPT can_b1_1.

## Key Config Values

Configuration lives in `config.py`.

- `DISPLAY_RANGE_M`: Radar radius - 5m (tight ACC-style proximity view)
- `DISPLAY_FPS`: Render rate - 30fps (must match camera rate)
- `GLOW_RANGE_M`: Orange proximity warning threshold - 2m
- `COVERAGE_CONES_ENABLED`: Camera FOV overlay - off by default
- `OCCLUDED_COAST_MS`: Extended coast when adjacent track present - 2500ms
- `CAM_TYPE`: Camera backend - "usb" (V4L2) or "csi" (picamera2)
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
- Hailo-10H has no onboard flash - firmware (~90MB) is DMA-transferred from host over PCIe every boot. EEPROM update is critical for reliable boot.
- **GPU/Hailo DMA conflict:** SRCALPHA surfaces and heavy pygame draw calls (e.g. concentric circles for proximity glow) overwhelm the Pi 5 GPU DMA bus and cause the Hailo PCIe VDMA to lose its connection (HAILO_COMMUNICATION_CLOSED). All rendering must avoid SRCALPHA - use colorkey transparency or direct drawing instead. Proximity glow is disabled pending a pre-rendered sprite implementation.
- **Hailo context manager:** `infer_model.configure()` returns a context manager that MUST be stored as an instance variable. If only `__enter__()` is saved, Python GC collects the context manager and calls `__exit__()`, tearing down the Hailo session.
- **Hailo bindings:** Must be pre-allocated once at init and reused per frame. Per-frame allocation causes file descriptor leaks and memory pressure on 2GB Pi.
- HUD shows Hailo status (INIT/DOWN) at bottom of prox view when detection is unavailable. Pipeline continues with camera feed even without detection.
- System is fully independent from openTPT; future radar fusion is passive CAN RX only.
- Occlusion handling: extended coast (2500ms vs 500ms) when track drops with adjacent active track present. No separate occlusion reasoning layer.
- Never run `hailortcli` before `main.py` - it can leave the Hailo device in a dirty state.
- Never `kill -9` the process - use ESC or SIGTERM so the Hailo VDevice closes cleanly.
