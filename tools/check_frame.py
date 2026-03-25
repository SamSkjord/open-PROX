#!/usr/bin/env python3
"""Check what picamera2 actually returns for frame data."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingest.csi_camera import CsiCamera

cam = CsiCamera(0, "RIGHT")
cam.open()
time.sleep(0.5)
cam.grab()
f = cam.frame_rgb
print(f"shape: {f.shape}, dtype: {f.dtype}, min: {f.min()}, max: {f.max()}")
print(f"contiguous: {f.flags['C_CONTIGUOUS']}")
cam.close()
print("done")
