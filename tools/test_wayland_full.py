#!/usr/bin/env python3
"""Test YoloDetector + camera + pygame under Wayland for 2 minutes."""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import pygame
import config
from detect.yolo import YoloDetector

pygame.init()
screen = pygame.display.set_mode((config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT))
clock = pygame.time.Clock()
font = pygame.font.SysFont("consolas", 16)
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

    # Render camera feed
    fh, fw = rgb.shape[:2]
    scale = config.DISPLAY_WIDTH / fw
    disp_h = int(fh * scale)
    y_off = (config.DISPLAY_HEIGHT - disp_h) // 2
    resized = cv2.resize(rgb, (config.DISPLAY_WIDTH, disp_h))
    surf = pygame.surfarray.make_surface(resized.swapaxes(0, 1))
    screen.fill((0, 0, 0))
    screen.blit(surf, (0, y_off))

    # Draw detection boxes
    for d in dets:
        x1 = int(d.x1 * scale)
        y1 = int(d.y1 * scale) + y_off
        x2 = int(d.x2 * scale)
        y2 = int(d.y2 * scale) + y_off
        pygame.draw.rect(screen, (255, 100, 0), (x1, y1, x2 - x1, y2 - y1), 2)
        label = font.render(f"{d.score:.0%} c{d.class_id}", True, (255, 100, 0))
        screen.blit(label, (x1, max(0, y1 - 18)))

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
