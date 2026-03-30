#!/usr/bin/env python3
"""Test Wayland display with Hailo detection."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
pygame.init()
print(f"SDL driver: {pygame.display.get_driver()}")
screen = pygame.display.set_mode((720, 720))
screen.fill((0, 255, 0))
pygame.display.flip()
print("WAYLAND DISPLAY OK - green screen")
time.sleep(3)

# Now test with Hailo
from detect.yolo import YoloDetector
import numpy as np
import config

det = YoloDetector()
print("Hailo detector ready")

dummy = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
start = time.time()
count = 0
errors = 0
while time.time() - start < 60:
    try:
        dets = det.detect(dummy)
        count += 1
    except Exception as e:
        errors += 1
        if errors == 1:
            print(f"ERROR at frame {count}: {e}")
        if errors > 5:
            break
    screen.fill((0, int(255 * (count % 30) / 30), 0))
    pygame.display.flip()
    if count % 100 == 0:
        print(f"{count} frames, {errors} errors")

print(f"done: {count} frames, {time.time()-start:.0f}s, {errors} errors")
det.close()
pygame.quit()
