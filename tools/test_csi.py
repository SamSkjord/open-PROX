#!/usr/bin/env python3
"""Quick test: CSI camera feed on display with YOLO detection overlay.

Run on Pi:
    cd ~/open-PROX && SDL_VIDEODRIVER=kmsdrm ~/prox-env/bin/python3 tools/test_csi.py

Press ESC or Q to quit.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import threading
import numpy as np
import config

# -- Camera --
from ingest.csi_camera import CsiCamera

cam = CsiCamera(camera_num=0, side="RIGHT")
print("Opening CSI camera...")
cam.open()
# Let auto-exposure settle
time.sleep(0.5)

# -- Detector in background thread --
from detect.yolo import YoloDetector

detect_lock = threading.Lock()
latest_detections = []
detect_frame = None
detect_frame_ready = threading.Event()
detect_shutdown = threading.Event()


def detect_thread():
    global latest_detections
    detector = None
    try:
        detector = YoloDetector()
        print("Hailo detector ready")
    except Exception as e:
        print(f"No Hailo detector ({e})")
        return

    while not detect_shutdown.is_set():
        # Wait for a frame to process
        if not detect_frame_ready.wait(timeout=0.5):
            continue
        detect_frame_ready.clear()

        with detect_lock:
            frame = detect_frame

        if frame is None:
            continue

        try:
            dets = detector.detect(frame)
            latest_detections = dets
        except Exception as e:
            print(f"detect error: {e}")
            # Try to recover
            try:
                detector.close()
            except Exception:
                pass
            time.sleep(1)
            try:
                detector = YoloDetector()
                print("Hailo detector recovered")
            except Exception as e2:
                print(f"Hailo recovery failed: {e2}")
                return

    if detector is not None:
        detector.close()


det_thread = threading.Thread(target=detect_thread, daemon=True)
det_thread.start()

# -- Display --
import pygame
import cv2

pygame.init()
screen = pygame.display.set_mode((config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT))
pygame.display.set_caption("CSI Camera Test")
clock = pygame.time.Clock()
font = pygame.font.SysFont("consolas", 16)

DETECT_INTERVAL_S = 1.0 / 10

print("Running - press ESC to quit")

try:
    running = True
    last_detect_time = 0
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False

        if not cam.grab():
            continue

        frame = cam.frame_rgb
        fh, fw = frame.shape[:2]

        # Submit frame for detection at capped rate
        now = time.monotonic()
        if (now - last_detect_time) >= DETECT_INTERVAL_S:
            last_detect_time = now
            with detect_lock:
                detect_frame = frame.copy()
            detect_frame_ready.set()

        detections = latest_detections

        # Letterbox into display
        scale = config.DISPLAY_WIDTH / fw
        disp_h = int(fh * scale)
        y_off = (config.DISPLAY_HEIGHT - disp_h) // 2

        resized = cv2.resize(frame, (config.DISPLAY_WIDTH, disp_h))
        surf = pygame.surfarray.make_surface(resized.swapaxes(0, 1))

        screen.fill((0, 0, 0))
        screen.blit(surf, (0, y_off))

        # Draw detection boxes
        for d in detections:
            x1 = int(d.x1 * scale)
            y1 = int(d.y1 * scale) + y_off
            x2 = int(d.x2 * scale)
            y2 = int(d.y2 * scale) + y_off
            colour = (255, 100, 0)
            pygame.draw.rect(screen, colour, (x1, y1, x2 - x1, y2 - y1), 2)
            label = f"{d.score:.0%} c{d.class_id}"
            txt = font.render(label, True, colour)
            screen.blit(txt, (x1, max(0, y1 - 18)))

        # HUD
        fps = clock.get_fps()
        hud = font.render(f"FPS: {fps:.0f}  det: {len(detections)}", True,
                          (200, 200, 200))
        screen.blit(hud, (10, 10))

        pygame.display.flip()
        clock.tick(config.DISPLAY_FPS)

finally:
    detect_shutdown.set()
    det_thread.join(timeout=5)
    cam.close()
    pygame.quit()
    print("Done")
