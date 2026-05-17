Hi Michael,

Good news - replacing the Hailo-10H HAT module fixed it.

Background: while waiting on logging info, I swapped to a second Pi5 to rule out the board. Same crash, same `HAILO_COMMUNICATION_CLOSED(62)` signature, even faster (3.2s and 3.8s on two trials). So clearly not a Pi-specific issue.

Then I swapped the Hailo module itself for a fresh unit on the original Pi. Two back-to-back 5-minute stress runs at sustained 29 fps with no crash, no errors, no warnings:

- Trial 1: 8940+ frames, 310s, clean exit on timeout
- Trial 2: 8970+ frames, 310s, clean exit on timeout

Same Pi, same HailoRT 5.2.0, same HEF, same USB camera, same `async_stress.py` reproducer that was crashing within 4 seconds yesterday. The only variable that changed is the physical Hailo HAT module.

Looks like the original unit had a hardware fault that surfaced as repeatable VDMA/SOC wedges under camera+inference load. The variance we saw earlier (9s to 300+s) was probably the fault becoming more deterministic as the chip degraded.

Thanks for all the help digging into this - the driver source analysis and SCU log discussion were valuable even if the root cause turned out to be hardware. Closing the thread from my end.

Best,
Sam
