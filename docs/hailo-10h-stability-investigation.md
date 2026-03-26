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

## Status

Reported to Hailo community forum on 2026-03-26. Hailo staff confirmed they are investigating internally. Awaiting response with fix, firmware update, or RMA instructions.

Forum thread: "Hailo-10H COMMUNICATION_CLOSED after ~5000 frames of continuous inference (AI HAT+ 2, Pi 5)"

## Recommendations for Next Steps

1. **Wait for Hailo response** - they may have a firmware patch or identify a hardware defect
2. **Try HailoRT 4.23 with correct Hailo-10H firmware** - the 4.23 release has "stability fixes" and "better memory and buffer management" but the h10 firmware packaging is broken
3. **Test on Pi 5 8GB** - more system memory might help with DMA buffer allocation
4. **Try a different HAT unit** - if Hailo confirms hardware issue
5. **Consider Hailo-8L** as fallback - simpler firmware loading, more mature driver, but lower TOPS
