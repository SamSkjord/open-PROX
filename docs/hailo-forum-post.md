Hi Michael,
Thanks for the followup, pulled and did some testing:

## Setup

Raspberry Pi 5 (2GB), Raspbian Lite Trixie, kernel( 6.12.75, Hailo-10H AI HAT+ 2 via PCIe. HailoRT 5.2.0, hailort-pcie-driver 5.2.0, `hailo-apps-infra` 26.3.0, Python 3.12. YOLOv8m HEF from `v5.2.0/hailo10h/yolov8m.hef`. `pcie_aspm=off` in cmdline.txt. PCIe link up at 8.0 GT/s x1. No `dtparam=pciex1_gen=3` forcing; it auto-negotiates Gen 3. USB camera on `/dev/video0` at 1280x720 MJPG 30fps. No display, no pygame, no custom PROX code in the tests below.

## Prior state on HailoRT 5.1.1

Running the bare inference stress with dummy data (no camera, no display) held up for 5 minutes at thousands of frames with zero errors. Adding the USB camera, also without a display, held up for 5 minutes with zero errors. The crash only appeared when camera + inference + display ran together, between 30 seconds and 4 minutes. Upgrading to HailoRT 5.2.0 fixed the standalone infinite-loop crash but did not fix the combined workload.

## Current state on HailoRT 5.2.0

Moving to 5.2.0 has changed the picture. Camera + inference without any display now also crashes, which was not the case on 5.1.1 in the same configuration.

To eliminate our code as a factor, I installed `hailo-apps-infra` 26.3.0 and ran the reference app `hailo-detect-simple` with a USB camera:

```
~/hailo-apps-infra/venv_hailo_apps/bin/hailo-detect-simple \
  --input usb --arch hailo10h --show-fps --disable-sync
```

Crash at frame 567, about 30 seconds in, at 19 FPS:

```
Frame count: 566
INFO | gstreamer.gstreamer_app | FPS measurement: 19.71, drop=0.00, avg=19.32
[HailoRT] [error] Failed to send request, status = HAILO_COMMUNICATION_CLOSED(62)
(Hailo Simple Detection App:14007): ERROR: Failed to run async inference, status = 62
```

This was pure GStreamer + `hailo_apps_infra` on HailoRT 5.2.0. No display, no pygame, no custom PROX code. It should be straightforward to reproduce on your side using the same HEF and a USB camera.

## Minimal Python async reproducer

I wrote a short standalone script to get precise timing and to vary parameters. It does V4L2 grab, letterbox preprocess, `wait_for_async_ready` + `run_async` + `job.wait(5000)` in a tight loop, and prints the frame count and elapsed time at every crash.

```python
import time, sys
import numpy as np
import cv2
from hailo_platform import VDevice, FormatType

cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_FPS, 30)

v = VDevice()
m = v.create_infer_model('/usr/share/hailo-models/yolov8m_h10.hef')
m.input().set_format_type(FormatType.UINT8)
ctx = m.configure()
cfg = ctx.__enter__()
ob = {o.name: np.empty(o.shape, dtype=np.float32) for o in m.outputs}
b = cfg.create_bindings(output_buffers=ob)
mh, mw = m.input().shape[:2]

start = time.monotonic(); n = 0
while True:
    ok, frame = cap.read()
    if not ok: continue
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    sc = min(mw/rgb.shape[1], mh/rgb.shape[0])
    nh, nw = int(rgb.shape[0]*sc), int(rgb.shape[1]*sc)
    rs = cv2.resize(rgb, (nw, nh))
    pad = np.full((mh, mw, 3), 114, dtype=np.uint8)
    yo, xo = (mh-nh)//2, (mw-nw)//2
    pad[yo:yo+nh, xo:xo+nw] = rs
    b.input().set_buffer(pad)
    try:
        cfg.wait_for_async_ready(1000)
        job = cfg.run_async([b])
        job.wait(5000)
    except Exception as e:
        print(f'CRASH frame={n} elapsed={time.monotonic()-start:.1f}s: {e}', flush=True)
        sys.exit(1)
    n += 1
    if n % 30 == 0:
        el = time.monotonic()-start
        print(f'frame={n} elapsed={el:.1f}s fps={n/el:.1f}', flush=True)
```

## Variance study

I wrapped the reproducer in a harness that power cycles the Pi between trials and records the crash time. Five trials at each of two CMA sizes:

- `cma=256M`: crash at 57.2s, 37.8s, 280.3s, 23.1s, 13.5s. Median 37.8s.
- `cma=320M`: crash at 9.2s, 43.6s, 18.5s, no-crash-in-300s, 23.5s. Median 23.5s.

Within each config the spread is 20x or more. Each batch had one trial that ran for several minutes cleanly, while others crashed in under 20 seconds. Differences between the two CMA sizes are smaller than the within-config variance. The distribution looks bimodal: about 80 percent of runs crash under 60 seconds, the rest run for multiple minutes.

This pattern is consistent with a timing-sensitive race rather than steady resource exhaustion. Raising CMA from 64M (the default, where `CmaFree` drops to double-digit kB under load) to 320M did not eliminate the crash. `gpu_mem=128` did not change the CMA ceiling, which is about 320M on this 2GB board because of how firmware lays out reserved regions. CMA pressure does not appear to be the root cause.

## Two failure signatures

Nine out of ten async trials failed with this signature:

```
[HailoRT] [error] CHECK failed - Waiting for async job to finish has failed with timeout (5000ms)
[HailoRT] [error] Ioctl HAILO_VDMA_LAUNCH_TRANSFER failed with 5
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_DRIVER_OPERATION_FAILED(36)
```

kernel log at crash:

```
hailo1x 0001:01:00.0: Timeout waiting for soc control (timeout_ms=1000)
hailo1x 0001:01:00.0: soc_close failed with err=-110
```

One out of ten trials (and the `hailo-detect-simple` run) failed with `HAILO_COMMUNICATION_CLOSED(62)` instead. These appear to be two surface symptoms of the same underlying event, depending on which codepath hits first.

## Driver source analysis

I read through the `hailort-pcie-driver` 5.2.0 DKMS source to localise the error paths.

`HAILO_VDMA_LAUNCH_TRANSFER` errno=5 (EIO) originates in `validate_channel_state` in `common/vdma_common.c`:

```c
if (channel->state.num_avail != hw_num_avail) {
    pr_err("Channel %d num-available HW mismatch (%ud!=%ud)\n", ...);
    return -EIO;
}
if (channel->state.num_avail != desc_list->num_launched) {
    pr_err("Channel %d num-available desc-list mismatch (%ud!=%ud)\n", ...);
    return -EIO;
}
```

Either the driver's software `num_avail` counter diverges from the hardware register, or two internal software counters diverge from each other. I have not yet captured these `pr_err` lines in dmesg during a crash.

`Timeout waiting for soc control` comes from `linux/pcie/src/soc.c:66` where `wait_for_completion_timeout` expires after 1 second. At that point the SOC firmware has stopped responding on the PCIe control channel. `soc_close` then also fails, so the firmware is not processing control messages at teardown either.

The sequence that fits all observations:

1. SOC firmware stops servicing the inference channel (no completion IRQ fires for the current transfer).
2. `job.wait(5000)` in hailort times out.
3. Subsequent VDMA ioctls fail with EIO because descriptor state has drifted from the hardware.
4. The Python VDevice destructor calls `soc_close`, which also times out since the firmware is unresponsive.
5. pyhailort surfaces either `HAILO_DRIVER_OPERATION_FAILED` or `HAILO_COMMUNICATION_CLOSED` depending on which ioctl caught the firmware stall first.

This points the root cause to the firmware side. The host driver and hailort are correctly detecting that the firmware went unresponsive. The high variance in crash time is consistent with a race or external-event-triggered firmware fault that only fires under specific timing conditions.

## Other observations

Firmware boot lottery: even on a clean power cycle, the SOC firmware load fails roughly 40 to 50 percent of the time with `Failed writing SOC firmware on stage 2` or `stage 3` followed by `Firmware load failed` and `Failed activating board -110`. This is independent of the runtime crash but may share a common cause since both involve the SOC side going unresponsive. EEPROM is up to date, cold-power delays of up to 45 seconds help but do not eliminate the lottery.

Sometimes after a crash, `rmmod hailo1x_pci && modprobe hailo1x_pci` fails with `Probing: Failed reading device BARs, device may be disconnected`, requiring a full mains power cycle of the Pi.

## Questions

1. Is there a verbose driver or HailoRT logging mode that would surface the descriptor state and any prior warnings before the wedge? Capturing the `pr_err` from `validate_channel_state` and the inference-side trace would help localise further.

2. Does the SOC firmware emit any log that can still be read over PCIe after the control channel stops responding? An HRT or SCU log dump path that works post-wedge would be valuable.

3. Is there a firmware watchdog that could auto-reset the SoC without a full power cycle? Currently my only recovery path after a wedge is mains power off and on, which also trips the firmware-load boot lottery roughly half the time.

4. Any targeted tests you want me to run? The reproducer above is short, and I can add instrumentation (capture dmesg at crash, try CSI camera to change the DMA path, run with a smaller model like yolov8n, add kernel-level tracing for VDMA ioctls), or vary API paths as you suggest.

Thanks,
Sam
