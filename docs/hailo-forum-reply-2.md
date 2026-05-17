Hi Michael,

Pulled `hailo-apps` (the new official repo) and re-ran `hailo-detect-simple` against it. Two trials with USB camera + HailoRT 5.2.0:

- Trial 1: crash at frame 7867, about 262 seconds in, sustained 30 FPS.
- Trial 2: crash at frame 2470, about 82 seconds in, sustained 30 FPS.

Both crashed with the same `HAILO_COMMUNICATION_CLOSED(62)`:

```
[HailoRT] [error] Failed to send request, status = HAILO_COMMUNICATION_CLOSED(62)
ERROR: Failed to run async inference, status = 62
```

So the new `hailo-apps` reproduces the same crash. Compared to the deprecated `hailo_apps_infra` test (crashed at frame 567, around 30 seconds, at 19 FPS), the new app runs longer and at higher throughput, but the underlying firmware wedge still hits within minutes. The variance between trial 1 and trial 2 is the same bimodal pattern (some runs short, some runs long) we saw on the standalone Python reproducer.

Trial 3 attempt failed differently: the SOC firmware came up enough for `/dev/hailo0` to appear, but `hailortcli fw-control identify` was not yet responsive, and `hailo-detect-simple` failed at startup with `Ioctl HAILO_SOC_CONNECT failed due to connection refused / HAILO_CONNECTION_REFUSED(89)`. Subsequent power cycles hit the firmware-load boot lottery (`Failed writing SOC firmware on stage 2`). One of those firmware-load failures triggered a kernel oops in `print_scu_log` inside `hailo1x_pci`:

```
[   11.683329] hailo1x 0001:01:00.0: Timeout waiting for firmware file
[   11.683334] hailo1x 0001:01:00.0: Failed writing SOC firmware on stage 2
[   11.858786] pc : print_scu_log+0xa8/0x190 [hailo1x_pci]
[   11.864388] lr : print_scu_log+0x98/0x190 [hailo1x_pci]
[   11.951234]  print_scu_log+0xa8/0x190 [hailo1x_pci]
[   11.956434]  hailo_activate_board+0x464/0x818 [hailo1x_pci]
[   11.962327]  hailo_pcie_probe+0x464/0x6c8 [hailo1x_pci]
```

So even when firmware load fails, the diagnostic log path itself is faulting. Probably worth a separate look on your side, because it likely loses the SCU log content that would explain why stage 2 timed out.

To summarise where we are:

1. New `hailo-apps` reproduces the crash with the same signature as the deprecated `hailo_apps_infra` and as the standalone Python reproducer.
2. Standalone Python reproducer (no GStreamer, no hailo-apps in either form) reproduces it independently.
3. The `print_scu_log` oops is a separate issue but blocks debugging when firmware load fails.

Happy to run anything else you suggest. Same harness, same Pi.

Thanks,
Sam
