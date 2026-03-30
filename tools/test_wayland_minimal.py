#!/usr/bin/env python3
"""Minimal test: camera + hailo + pygame wayland, no heavy rendering."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2, numpy as np, pygame, config
from detect.yolo import YoloDetector

pygame.init()
screen = pygame.display.set_mode((config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT))
font = pygame.font.SysFont("consolas", 16)
clock = pygame.time.Clock()
print(f"display: {pygame.display.get_driver()}")

cap = cv2.VideoCapture(config.CAM_RIGHT_DEVICE, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAM_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAM_HEIGHT)
cap.set(cv2.CAP_PROP_FPS, config.CAM_FPS)
print(f"camera: {cap.isOpened()}")

det = YoloDetector()
print("detector ready")

start = time.time()
count = 0
errors = 0
while time.time() - start < 120:
    for e in pygame.event.get():
        pass
    ret = cap.grab()
    if not ret:
        continue
    ret, frame = cap.retrieve()
    if not ret:
        continue
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    try:
        dets = det.detect(rgb)
        count += 1
    except Exception as e:
        errors += 1
        if errors == 1:
            print(f"ERROR at {count}: {e}")
        if errors > 5:
            break

    # Minimal render - just fill + text, no camera blit
    screen.fill((8, 8, 8))
    hud = font.render(f"f:{count} d:{len(dets)} e:{errors}", True, (200, 200, 200))
    screen.blit(hud, (10, 10))
    pygame.display.flip()
    clock.tick(config.DISPLAY_FPS)

    if count % 100 == 0:
        print(f"{count} frames, {errors} errors")

elapsed = time.time() - start
print(f"done: {count} frames, {elapsed:.0f}s, {errors} errors")
det.close()
cap.release()
pygame.quit()
