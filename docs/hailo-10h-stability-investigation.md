# Hailo-10H AI HAT+ 2 Stability Investigation

Date: 2026-03-26
Hardware: Raspberry Pi 5 2GB + Hailo AI HAT+ 2 (Hailo-10H, 40 TOPS)
Software: Raspbian Lite (Trixie), hailo-h10-all 5.1.1, kernel 6.12.47

## The Problem

The Hailo-10H loses its PCIe communication channel after approximately 2-3 minutes of continuous inference, regardless of what else is running on the system. The error is `HAILO_COMMUNICATION_CLOSED(62)` - the PCIe VDMA link drops entirely.

## Definitive Test

A bare stress test with no camera, no display, no pygame - just VDevice + InferModel + dummy numpy data in a loop - crashes at frame ~5334 (~2 min 16s at 39fps). Adding `pcie_aspm=off` to the kernel cmdline extends this to frame ~6246 (~3 min 9s), confirming PCIe power management is a contributing factor but not the root cause.

```python
vd = VDevice()
im = vd.create_infer_model("yolov8m_h10.hef")
im.input().set_format_type(FormatType.UINT8)
ctx = im.configure()
cm = ctx.__enter__()
bufs = {o.name: np.empty(o.shape, dtype=np.float32) for o in im.outputs}
bindings = cm.create_bindings(output_buffers=bufs)
dummy = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)

# Crashes at frame ~5334 without pcie_aspm=off
# Crashes at frame ~6246 with pcie_aspm=off
while True:
    bindings.input().set_buffer(np.array(dummy))
    cm.run([bindings], 30000)
```

## What We Tried (and ruled out)

### Software / Code
- **Single-threaded vs threaded vs multiprocessing**: Same crash in all modes
- **Context manager fix**: Stored `infer_model.configure()` context manager to prevent GC teardown. Correct practice but not the cause
- **Pre-allocated bindings**: Allocate output buffers and bindings once, reuse per frame. Reduces memory pressure but doesn't fix crash
- **Display FPS**: Tried 60fps and 30fps. No difference
- **Proximity glow removal**: Removed GPU-heavy concentric circle drawing. Improved time-to-crash slightly but didn't fix it
- **SRCALPHA surface removal**: Replaced all SRCALPHA surfaces with colorkey transparency. No fix
- **Different numpy versions**: Tested numpy <2.0 (required) and 2.x (breaks hailo_platform)
- **Different opencv versions**: <4.11 for numpy compatibility

### System / Kernel
- **Kernel 6.12.47**: Original kernel, Hailo firmware loads ~50% of boots
- **Kernel 6.12.75**: Newer kernel, same crash behaviour
- **EEPROM update**: `rpi-eeprom-update -a` - improved boot reliability but didn't fix runtime crash
- **dkms installation order**: Installed dkms before hailo-h10-all as documented. Correct but doesn't fix crash
- **pcie_aspm=off**: Added to cmdline.txt. Extended crash point by ~40% (5334 to 6246 frames) but didn't eliminate it
- **dtparam=pciex1_gen=3**: Explicit Gen3 enable. No consistent effect - RPi docs say HAT+ 2 auto-negotiates
- **dtparam=pciex1_gen=2**: Force Gen2. No fix

### Driver / Firmware
- **HailoRT 5.1.1**: Current stable from apt. Has the crash
- **HailoRT 5.2.0**: Manual .deb install. Driver module fails to load on kernel 6.12.47 with "Invalid argument". Empty dkms.conf in the package (packaging bug)
- **HailoRT 4.23.0** (hailo-all): Latest release (March 2026). Only ships Hailo-8 firmware, not Hailo-10H. Requires h10-hailort-pcie-driver alongside it for the 10H firmware files
- **Multiple fresh OS images**: Reflashed SD card 4 times. Same behaviour on each

### Hardware
- **FPC ribbon cable reseating**: Done multiple times, no improvement
- **HAT reseating**: Removed and reseated on GPIO header, no improvement
- **Active cooling**: Confirmed. Pi stays at 48C. HAT heatsink is cool
- **Power supply**: Tested with adequate supply
- **PCIe link status**: `lspci` shows Speed 8GT/s, Width x1 (downgraded from x4). The x1 width is expected - Pi 5 only has one PCIe lane. The "downgraded" label is because the Hailo chip supports x4

## Boot Reliability

The Hailo firmware loading is also unreliable - approximately 50% of cold boots fail with "Timeout waiting for firmware file on stage 2". The Hailo-10H has no onboard flash; ~90MB of firmware is DMA-transferred from the host over PCIe every boot. EEPROM update improved this somewhat but didn't eliminate it.

Power cycling via a TP-Link Kasa smart plug (192.168.199.69) automates the boot retries.

## dmesg After Runtime Crash

No useful kernel-level errors after the crash. The Hailo driver doesn't log anything - the device just silently drops the PCIe connection. Only the userspace HailoRT library reports `COMMUNICATION_CLOSED`.

After the crash, `/dev/hailo0` becomes inaccessible. `VDevice()` fails with `HAILO_DRIVER_OPERATION_FAILED(36)`. Only a full power cycle (not just reboot) recovers the device.

Calling `rmmod hailo1x_pci && modprobe hailo1x_pci` does not recover - the PCIe device is in a failed state that requires a bus-level power cycle.

## GPU DMA Interaction (Partially Confirmed)

Early investigation found that pygame's GPU-heavy rendering (SRCALPHA surfaces, concentric circle drawing for proximity glow) accelerated the crash. The Pi 5's V3D GPU uses DMA for surface compositing, which shares the memory bus with the Hailo's PCIe VDMA.

However, the bare stress test (no pygame at all) still crashes, proving the GPU is not the primary cause. The GPU DMA load may reduce the time-to-crash by competing for bus bandwidth, but the underlying issue is in the Hailo firmware/hardware.

## Current Workarounds

1. **Graceful degradation**: Pipeline continues without detection when Hailo drops. HUD shows "HAILO DOWN"
2. **pcie_aspm=off**: Extends runtime by ~40%
3. **Pre-rendered glow sprites**: Reduces GPU DMA load, extending runtime slightly
4. **Multiprocessing isolation**: Detection runs in a separate process. Doesn't fix the crash but isolates the failure cleanly

## Update: 2026-03-29

### HailoRT 5.2.0 fixes standalone crash

Installed 5.2.0 driver and runtime from Hailo developer zone .deb files. Required Python 3.12 built from source (Trixie ships 3.13, the 5.2.0 wheel is cp312 only).

Bare stress test: **11773 frames, 5 minutes, 0 errors** (vs 5334 frames crash on 5.1.1).
Camera + Hailo (no display): **7754 frames, 5 minutes, 0 errors**.

### DRM/GPU conflict identified

With 5.2.0, the Hailo still crashes immediately when pygame renders via KMSDRM. The conflict is between DRM page flips and Hailo PCIe VDMA at the kernel level. Confirmed by:
- card0 (rp1dsi - DSI controller, no GPU)
- card1 (v3d - GPU) - blacklisting this delays but doesn't fix the crash
- card2 (vc6 - video core/HDMI)

Even with V3D blacklisted and process isolation (multiprocessing spawn), KMSDRM display kills Hailo.

### Framebuffer workaround

Bypassing DRM entirely by writing directly to `/dev/fb0` via mmap:
- SDL dummy driver for pygame surface operations (no DRM, no GPU)
- Raw BGRA pixel writes to the DSI framebuffer
- **5 minutes, zero Hailo errors** - confirmed working

Trade-offs:
- No touch input (SDL dummy driver has no input handling) - needs evdev reader
- Lower framerate (CPU pixel copy vs GPU compositing)
- Console cursor bleedthrough (partially fixed by unbinding VT consoles)

### Package state for 5.2.0

```
hailort               5.2.0  (from .deb)
hailort-pcie-driver   5.2.0  (from .deb, DKMS built for 6.12.75)
hailo-tappas-core     5.2.0  (from .deb)
hailo-gen-ai-model-zoo 5.2.0 (from .deb)
hailo-models          1.0.0-2 (from apt, .hef files)
Python:               3.12.9 (built from source, venv ~/prox-env-312)
hailort wheel:        5.2.0-cp312 (in 3.12 venv)
Firmware:             /lib/firmware/hailo/hailo10h/ (from old h10-hailort-pcie-driver 5.1.1)
Kernel:               6.12.75+rpt-rpi-2712
V3D:                  blacklisted in /etc/modprobe.d/v3d-blacklist.conf
```

Note: numpy must be <2.0, opencv-python-headless <4.11.

## Status

Reported to Hailo community forum on 2026-03-26. Follow-up posted 2026-03-29 with DRM/GPU conflict details. Hailo staff recommended 5.2.0 upgrade.

Forum thread: "Hailo-10H COMMUNICATION_CLOSED after ~5000 frames of continuous inference (AI HAT+ 2, Pi 5)"

## Recommendations for Next Steps

1. **Add evdev touch input** - replace pygame's event handling with direct `/dev/input/event1` reading (Goodix touchscreen)
2. **Optimize framebuffer write** - current CPU pixel copy is slow, consider pre-allocated buffers or ctypes memcpy
3. **Fix console cursor bleedthrough** - VT unbind works but resets on reboot, add to startup
4. **Wait for Hailo response** on DRM conflict - they may have a kernel driver fix
5. **Test on Pi 5 8GB** - more headroom for DMA buffers
