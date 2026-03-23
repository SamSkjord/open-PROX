#!/usr/bin/env python3
"""Lens calibration using a known-width object at measured distances.

Shows camera feed with crosshairs and pixel measurement grid.
Detects the largest dark-bordered rectangle (A4 paper with dark border tape).

Mark your A4 paper edges with dark tape so it stands out from background.
Or use any known-width object with clear edges.

SSH console shows instructions and prompts for distance input.
Display is laid out for a circular 720px screen (content centred, no edge text).

Usage on Pi:
    SDL_VIDEODRIVER=kmsdrm ~/prox-env/bin/python3 -u tools/lens_calibrate.py
"""

import sys
import time
import threading
import cv2
import numpy as np
import pygame

# -- Configuration --
OBJECT_WIDTH_MM = 297.0       # A4 landscape width (change if using different object)
DISPLAY_SIZE = 720
CAM_WIDTH = 1280
CAM_HEIGHT = 720
CENTRE = DISPLAY_SIZE // 2
# Circular display usable radius (content stays inside this)
USABLE_R = 320


def setup_camera():
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, 30)
    return cap


def find_paper_contour(frame):
    """Find the largest roughly-rectangular contour. Returns (pixel_width, box_points) or (None, None)."""
    grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(grey, (5, 5), 0)

    # Use Canny edges - works better than threshold for finding paper edges
    edges = cv2.Canny(blurred, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edges = cv2.dilate(edges, kernel, iterations=2)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, None

    # Find largest contour that's roughly rectangular
    best = None
    best_area = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 3000:
            continue
        rect = cv2.minAreaRect(cnt)
        rect_area = rect[1][0] * rect[1][1]
        if rect_area < 1:
            continue
        # Rectangularity: how well the contour fills its bounding rect
        rectangularity = area / rect_area
        if rectangularity > 0.6 and area > best_area:
            best = cnt
            best_area = area

    if best is None:
        return None, None

    rect = cv2.minAreaRect(best)
    box = cv2.boxPoints(rect)
    w = max(rect[1])
    h = min(rect[1])
    # Reject if aspect ratio is too extreme or too square for A4
    aspect = w / h if h > 0 else 0
    if aspect < 1.1 or aspect > 3.0:
        return None, None

    return w, np.intp(box)


def input_thread_func(prompts_queue, results_queue):
    """Background thread to read distances from SSH stdin."""
    while True:
        prompt = prompts_queue.get()
        if prompt is None:
            break
        try:
            val = input(prompt)
            results_queue.put(val.strip())
        except EOFError:
            results_queue.put(None)
            break


def main():
    import queue

    pygame.init()
    screen = pygame.display.set_mode((DISPLAY_SIZE, DISPLAY_SIZE))
    font = pygame.font.SysFont("monospace", 16)
    font_big = pygame.font.SysFont("monospace", 20)
    clock = pygame.time.Clock()

    cap = setup_camera()
    if not cap.isOpened():
        print("ERROR: Cannot open camera")
        return

    samples = []
    stable_history = []
    stable_threshold = 8  # px tolerance
    stable_needed = 20

    print("=== LENS CALIBRATION ===")
    print(f"Object width: {OBJECT_WIDTH_MM}mm (A4 landscape)")
    print()
    print("Hold A4 paper (landscape) in front of camera.")
    print("Green outline = detected paper.")
    print("When stable, enter the distance in mm when prompted.")
    print("Type 'q' to finish and compute results.")
    print()

    # Input thread for SSH console
    prompt_q = queue.Queue()
    result_q = queue.Queue()
    input_t = threading.Thread(target=input_thread_func, args=(prompt_q, result_q), daemon=True)
    input_t.start()

    awaiting_distance = False
    last_stable_px = None

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        ret, frame = cap.read()
        if not ret:
            continue

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        paper_w, box = find_paper_contour(frame)

        # Crop to square for display
        fh, fw = frame_rgb.shape[:2]
        cx = fw // 2
        half = min(fw, fh) // 2
        square = frame_rgb[:, cx - half:cx + half]
        display_frame = cv2.resize(square, (DISPLAY_SIZE, DISPLAY_SIZE))
        surf = pygame.surfarray.make_surface(display_frame.swapaxes(0, 1))
        screen.blit(surf, (0, 0))

        # Draw detection overlay
        if box is not None:
            scale_d = DISPLAY_SIZE / (half * 2)
            pts = [(int((p[0] - (cx - half)) * scale_d), int(p[1] * scale_d)) for p in box]
            pygame.draw.polygon(screen, (0, 255, 0), pts, 2)

        # Draw crosshairs (subtle, within circular area)
        pygame.draw.line(screen, (50, 50, 50), (CENTRE - USABLE_R, CENTRE), (CENTRE + USABLE_R, CENTRE), 1)
        pygame.draw.line(screen, (50, 50, 50), (CENTRE, CENTRE - USABLE_R), (CENTRE, CENTRE + USABLE_R), 1)

        # Stability tracking
        if paper_w is not None and paper_w > 30:
            if stable_history and abs(paper_w - np.median(stable_history[-10:])) < stable_threshold:
                stable_history.append(paper_w)
            else:
                stable_history = [paper_w]
        else:
            stable_history = []

        # Check for distance input
        if awaiting_distance:
            try:
                val = result_q.get_nowait()
                if val is None or val.lower() == 'q':
                    running = False
                else:
                    try:
                        dist_mm = float(val)
                        focal_px = (last_stable_px * dist_mm) / OBJECT_WIDTH_MM
                        samples.append((dist_mm, last_stable_px, focal_px))
                        print(f"  -> f = {focal_px:.1f} px")
                        print()
                        awaiting_distance = False
                        stable_history = []
                    except ValueError:
                        print("  Invalid number, try again.")
                        prompt_q.put(f"  Distance in mm: ")
            except queue.Empty:
                pass

        # When stable and not already prompting, ask for distance
        if not awaiting_distance and len(stable_history) >= stable_needed:
            last_stable_px = np.median(stable_history)
            awaiting_distance = True
            print(f"Paper detected: {last_stable_px:.1f} px wide")
            prompt_q.put(f"  Distance in mm (or 'q' to finish): ")

        # HUD - keep text within circular area
        if paper_w is not None:
            txt = font_big.render(f"{paper_w:.0f} px", True, (0, 255, 0))
            screen.blit(txt, (CENTRE - txt.get_width() // 2, CENTRE + USABLE_R - 60))
        else:
            txt = font.render("No detection", True, (255, 80, 80))
            screen.blit(txt, (CENTRE - txt.get_width() // 2, CENTRE + USABLE_R - 60))

        # Stability bar (centred)
        bar_total = 200
        bar_x = CENTRE - bar_total // 2
        bar_y = CENTRE - USABLE_R + 20
        progress = min(1.0, len(stable_history) / stable_needed)
        pygame.draw.rect(screen, (40, 40, 40), (bar_x, bar_y, bar_total, 10))
        if progress > 0:
            c = (0, 255, 0) if progress >= 1 else (255, 165, 0)
            pygame.draw.rect(screen, c, (bar_x, bar_y, int(bar_total * progress), 10))

        # Show sample count
        if samples:
            txt = font.render(f"{len(samples)} samples", True, (150, 150, 150))
            screen.blit(txt, (CENTRE - txt.get_width() // 2, bar_y + 16))

        if awaiting_distance:
            txt = font_big.render("Enter distance in SSH", True, (255, 255, 0))
            screen.blit(txt, (CENTRE - txt.get_width() // 2, CENTRE - 15))

        pygame.display.flip()
        clock.tick(30)

    # Results
    if samples:
        focal_values = [s[2] for s in samples]
        focal_avg = np.mean(focal_values)
        focal_std = np.std(focal_values)
        print()
        print(f"=== RESULT ===")
        print(f"focal_length_px = {focal_avg:.1f} +/- {focal_std:.1f}")
        print(f"Lens: 1.7mm fisheye")
        print(f"Object: {OBJECT_WIDTH_MM}mm")
        for d, px, f in samples:
            print(f"  {d}mm: {px:.1f}px -> f={f:.1f}")

    prompt_q.put(None)
    cap.release()
    pygame.quit()


if __name__ == "__main__":
    main()
