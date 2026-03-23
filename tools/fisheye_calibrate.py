#!/usr/bin/env python3
"""Fisheye lens calibration using a checkerboard pattern.

Print a 9x6 checkerboard (10x7 squares) on A4 paper. Measure the square size
in mm after printing. Hold the checkerboard in front of the camera at various
angles and positions across the FOV. The script auto-captures when corners are
detected and stable.

Outputs: intrinsic matrix (K), distortion coefficients (D), and saves to
calibration.json in the project root.

Usage on Pi:
    SDL_VIDEODRIVER=kmsdrm ~/prox-env/bin/python3 -u tools/fisheye_calibrate.py
    SDL_VIDEODRIVER=kmsdrm ~/prox-env/bin/python3 -u tools/fisheye_calibrate.py --square-size 25
"""

import argparse
import json
import time
import cv2
import numpy as np
import pygame

# Checkerboard inner corners
BOARD_W = 9
BOARD_H = 6
DISPLAY_SIZE = 720
CAM_WIDTH = 1280
CAM_HEIGHT = 720
CENTRE = DISPLAY_SIZE // 2
USABLE_R = 320

MIN_CAPTURES = 15
MAX_CAPTURES = 40
STABLE_FRAMES = 10           # frames of stable detection before auto-capture
MOVE_THRESHOLD_PX = 30       # corners must move this far between captures


def setup_camera():
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, 30)
    return cap


def corners_moved(new_corners, last_corners, threshold):
    """Check if the board has moved enough since last capture."""
    if last_corners is None:
        return True
    diff = np.abs(new_corners - last_corners).mean()
    return diff > threshold


def _try_calibrate(obj_points, img_points, img_size, flags):
    """Single calibration attempt. Returns (rms, K, D) or raises."""
    N = len(obj_points)
    K = np.zeros((3, 3))
    D = np.zeros((4, 1))
    rvecs = [np.zeros((1, 1, 3), dtype=np.float64) for _ in range(N)]
    tvecs = [np.zeros((1, 1, 3), dtype=np.float64) for _ in range(N)]
    rms, K, D, rvecs, tvecs = cv2.fisheye.calibrate(
        obj_points, img_points, img_size,
        K, D, rvecs, tvecs, flags,
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-6),
    )
    return rms, K, D


def calibrate_fisheye(obj_points, img_points, img_size):
    """Run OpenCV fisheye calibration with progressive fallbacks."""
    flag_sets = [
        # Strict
        cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC | cv2.fisheye.CALIB_CHECK_COND | cv2.fisheye.CALIB_FIX_SKEW,
        # Relaxed
        cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC | cv2.fisheye.CALIB_FIX_SKEW,
        # Minimal
        cv2.fisheye.CALIB_FIX_SKEW,
    ]

    N = len(obj_points)

    # Try full set with each flag combo
    for i, flags in enumerate(flag_sets):
        try:
            rms, K, D = _try_calibrate(obj_points, img_points, img_size, flags)
            print(f"  Calibrated with flag set {i} ({N} frames), RMS={rms:.4f}")
            return rms, K, D
        except cv2.error:
            pass

    # Try removing frames one at a time (leave-one-out)
    print(f"  Full set failed. Trying leave-one-out ({N} frames)...")
    for skip in range(N):
        subset_obj = [obj_points[j] for j in range(N) if j != skip]
        subset_img = [img_points[j] for j in range(N) if j != skip]
        for flags in flag_sets:
            try:
                rms, K, D = _try_calibrate(subset_obj, subset_img, img_size, flags)
                print(f"  Calibrated after removing frame {skip}, RMS={rms:.4f}")
                return rms, K, D
            except cv2.error:
                pass

    # Try with random subsets of 15
    print(f"  Leave-one-out failed. Trying random subsets...")
    indices = list(range(N))
    for attempt in range(50):
        np.random.shuffle(indices)
        subset_size = max(15, N // 2)
        sub_idx = sorted(indices[:subset_size])
        subset_obj = [obj_points[j] for j in sub_idx]
        subset_img = [img_points[j] for j in sub_idx]
        for flags in flag_sets:
            try:
                rms, K, D = _try_calibrate(subset_obj, subset_img, img_size, flags)
                print(f"  Calibrated with {subset_size}-frame subset (attempt {attempt+1}), RMS={rms:.4f}")
                return rms, K, D
            except cv2.error:
                pass

    print("  All calibration attempts failed.")
    return None, None, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--square-size", type=float, default=25.0,
                        help="Checkerboard square size in mm (measure after printing)")
    args = parser.parse_args()

    square_size_mm = args.square_size

    pygame.init()
    screen = pygame.display.set_mode((DISPLAY_SIZE, DISPLAY_SIZE))
    font = pygame.font.SysFont("monospace", 16)
    font_big = pygame.font.SysFont("monospace", 20)
    clock = pygame.time.Clock()

    cap = setup_camera()
    if not cap.isOpened():
        print("ERROR: Cannot open camera")
        return

    # Object points in world coords (z=0 plane)
    objp = np.zeros((BOARD_W * BOARD_H, 1, 3), dtype=np.float64)
    objp[:, 0, :2] = np.mgrid[0:BOARD_W, 0:BOARD_H].T.reshape(-1, 2) * square_size_mm

    obj_points = []   # 3D points
    img_points = []   # 2D points
    last_captured_corners = None
    stable_count = 0
    last_stable_corners = None
    calibrating = False
    result_text = []
    cooldown_until = 0

    print(f"=== FISHEYE CALIBRATION ===")
    print(f"Checkerboard: {BOARD_W}x{BOARD_H} inner corners")
    print(f"Square size: {square_size_mm}mm")
    print(f"Need {MIN_CAPTURES}-{MAX_CAPTURES} captures")
    print()
    print("Hold checkerboard in front of camera.")
    print("Move it around to cover different positions and angles.")
    print("Auto-captures when detection is stable.")
    print()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_c and len(obj_points) >= MIN_CAPTURES:
                    calibrating = True

        ret, frame = cap.read()
        if not ret:
            continue

        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Detect checkerboard
        flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE + cv2.CALIB_CB_FAST_CHECK
        found, corners = cv2.findChessboardCorners(grey, (BOARD_W, BOARD_H), flags)

        if found:
            corners = cv2.cornerSubPix(
                grey, corners, (5, 5), (-1, -1),
                (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.01)
            )

        # Letterbox full frame into display (black bars top/bottom)
        fh, fw = frame_rgb.shape[:2]
        scale_d = DISPLAY_SIZE / fw
        disp_h = int(fh * scale_d)
        y_off = (DISPLAY_SIZE - disp_h) // 2
        display_frame = cv2.resize(frame_rgb, (DISPLAY_SIZE, disp_h))
        screen.fill((0, 0, 0))
        surf = pygame.surfarray.make_surface(display_frame.swapaxes(0, 1))
        screen.blit(surf, (0, y_off))

        # Draw detected corners
        if found:
            for pt in corners:
                px = int(pt[0][0] * scale_d)
                py = int(pt[0][1] * scale_d) + y_off
                pygame.draw.circle(screen, (0, 255, 0), (px, py), 3)

        # Subtle crosshairs
        pygame.draw.line(screen, (40, 40, 40), (CENTRE - USABLE_R, CENTRE), (CENTRE + USABLE_R, CENTRE), 1)
        pygame.draw.line(screen, (40, 40, 40), (CENTRE, CENTRE - USABLE_R), (CENTRE, CENTRE + USABLE_R), 1)

        # Auto-capture logic
        now = time.monotonic()
        if found and not calibrating and now > cooldown_until:
            if last_stable_corners is not None:
                diff = np.abs(corners - last_stable_corners).mean()
                if diff < 3.0:
                    stable_count += 1
                else:
                    stable_count = 0
            else:
                stable_count = 0
            last_stable_corners = corners.copy()

            if stable_count >= STABLE_FRAMES:
                if corners_moved(corners, last_captured_corners, MOVE_THRESHOLD_PX):
                    obj_points.append(objp)
                    img_points.append(corners.astype(np.float64))
                    last_captured_corners = corners.copy()
                    n = len(obj_points)
                    print(f"  Capture {n}/{MIN_CAPTURES} (move board to new position)")
                    stable_count = 0
                    cooldown_until = now + 1.0  # 1s cooldown

                    if n >= MAX_CAPTURES:
                        calibrating = True
                else:
                    stable_count = 0
        else:
            stable_count = 0
            last_stable_corners = None

        # Calibrate
        if calibrating and not result_text:
            print()
            print("Calibrating...")
            rms, K, D = calibrate_fisheye(obj_points, img_points, (fw, fh))
            if K is not None:
                fx = K[0, 0]
                fy = K[1, 1]
                ppx = K[0, 2]
                ppy = K[1, 2]
                result_text = [
                    f"RMS error: {rms:.4f}",
                    f"fx={fx:.1f}  fy={fy:.1f}",
                    f"cx={ppx:.1f}  cy={ppy:.1f}",
                    f"D=[{D[0][0]:.4f}, {D[1][0]:.4f}, {D[2][0]:.4f}, {D[3][0]:.4f}]",
                ]
                print()
                print("=== RESULT ===")
                for line in result_text:
                    print(f"  {line}")

                # Save
                cal_data = {
                    "lens": "1.7mm fisheye",
                    "sensor": "OV9281",
                    "resolution": [fw, fh],
                    "square_size_mm": square_size_mm,
                    "num_captures": len(obj_points),
                    "rms_error": float(rms),
                    "K": K.tolist(),
                    "D": D.tolist(),
                    "fx": float(fx),
                    "fy": float(fy),
                    "cx": float(ppx),
                    "cy": float(ppy),
                }
                with open("calibration.json", "w") as f:
                    json.dump(cal_data, f, indent=2)
                print()
                print("Saved to calibration.json")
            else:
                result_text = ["Calibration failed - try more captures"]
                calibrating = False

        # HUD
        n = len(obj_points)

        if result_text:
            y = CENTRE - len(result_text) * 14
            for line in result_text:
                txt = font_big.render(line, True, (0, 255, 0))
                screen.blit(txt, (CENTRE - txt.get_width() // 2, y))
                y += 28
        else:
            # Capture count
            colour = (255, 255, 0) if n < MIN_CAPTURES else (0, 255, 0)
            txt = font_big.render(f"{n}/{MIN_CAPTURES}", True, colour)
            screen.blit(txt, (CENTRE - txt.get_width() // 2, CENTRE - USABLE_R + 15))

            # Status
            if found:
                status = "Hold steady..."
                s_colour = (0, 255, 0)
                if stable_count > 0:
                    bar_w = int((stable_count / STABLE_FRAMES) * 200)
                    bar_x = CENTRE - 100
                    bar_y = CENTRE + USABLE_R - 50
                    pygame.draw.rect(screen, (40, 40, 40), (bar_x, bar_y, 200, 8))
                    pygame.draw.rect(screen, (255, 165, 0), (bar_x, bar_y, bar_w, 8))
            else:
                status = "Show checkerboard"
                s_colour = (200, 200, 200)

            txt = font.render(status, True, s_colour)
            screen.blit(txt, (CENTRE - txt.get_width() // 2, CENTRE + USABLE_R - 30))

        pygame.display.flip()
        clock.tick(30)

    cap.release()
    pygame.quit()


if __name__ == "__main__":
    main()
