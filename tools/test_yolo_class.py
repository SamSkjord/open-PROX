#!/usr/bin/env python3
"""Test YoloDetector class with USB camera + pygame."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
from detect.yolo import YoloDetector
import pygame
import config

pygame.init()
screen = pygame.display.set_mode((config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT))
print("pygame ok")

cap = cv2.VideoCapture(config.CAM_RIGHT_DEVICE, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAM_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAM_HEIGHT)
cap.set(cv2.CAP_PROP_FPS, config.CAM_FPS)
print(f"camera: {cap.isOpened()}")

det = YoloDetector()
print("detector ok")

for i in range(200):
    ret = cap.grab()
    if not ret:
        continue
    ret, frame = cap.retrieve()
    if not ret:
        continue
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    dets = det.detect(frame_rgb)
    screen.fill((0, 0, 0))
    pygame.display.flip()
    if (i + 1) % 50 == 0:
        print(f"frame {i+1}: {len(dets)} dets ok")

det.close()
cap.release()
pygame.quit()
print("all done")
