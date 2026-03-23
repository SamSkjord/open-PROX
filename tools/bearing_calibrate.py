#!/usr/bin/env python3
"""Empirical pixel-to-bearing calibration for fisheye lens.

Uses a bright point source (phone flashlight) as a target. Place it at known
angles from the camera's optical axis. The script detects the bright spot,
records pixel distance from frame centre, and fits a fisheye projection model.

Setup options:
  A) Protractor: camera at centre, target at marked angles.
  B) Wall method: camera at distance D from a wall, target at offset X from
     centre mark. Angle = atan(X / D). Enter offset in mm, script computes angle.

Interactive via SSH. Display shows feed with target detection.

Usage:
    SDL_VIDEODRIVER=kmsdrm ~/prox-env/bin/python3 -u tools/bearing_calibrate.py
    SDL_VIDEODRIVER=kmsdrm ~/prox-env/bin/python3 -u tools/bearing_calibrate.py --wall-distance 1000
"""

import argparse
import json
import math
import threading
import queue
import cv2
import numpy as np
import pygame

DISPLAY_SIZE = 720
CAM_WIDTH = 1280
CAM_HEIGHT = 720
CENTRE = DISPLAY_SIZE // 2


def setup_camera():
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, 30)
    return cap


def find_bright_spot(frame):
    """Find the brightest point in the frame. Returns (x, y) in frame coords or None."""
    grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(grey, (15, 15), 0)

    # Threshold to find bright spots
    max_val = blurred.max()
    if max_val < 200:
        return None

    _, thresh = cv2.threshold(blurred, int(max_val * 0.85), 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    # Find the brightest contour centroid
    best = max(contours, key=cv2.contourArea)
    M = cv2.moments(best)
    if M["m00"] < 1:
        return None

    x = M["m10"] / M["m00"]
    y = M["m01"] / M["m00"]
    return (x, y)


def fit_fisheye_models(samples):
    """Fit different fisheye projection models to (r_pixels, theta_deg) samples.

    Models:
      Equidistant:  r = f * theta
      Equisolid:    r = 2 * f * sin(theta / 2)
      Stereographic: r = 2 * f * tan(theta / 2)
      Polynomial:   r = a0 + a1*theta + a2*theta^2 + a3*theta^3

    Returns dict with best model info.
    """
    r_vals = np.array([s[0] for s in samples])
    theta_deg = np.array([s[1] for s in samples])
    theta_rad = np.radians(theta_deg)

    results = {}

    # Equidistant: r = f * theta  ->  f = r / theta
    mask = theta_rad > 0.01
    if mask.sum() >= 2:
        f_eq = np.mean(r_vals[mask] / theta_rad[mask])
        r_pred = f_eq * theta_rad
        rms = np.sqrt(np.mean((r_vals - r_pred) ** 2))
        results["equidistant"] = {"f": float(f_eq), "rms": float(rms)}

    # Equisolid: r = 2f * sin(theta/2)  ->  f = r / (2 * sin(theta/2))
    if mask.sum() >= 2:
        sin_half = np.sin(theta_rad[mask] / 2)
        sin_half[sin_half < 0.001] = 0.001
        f_es = np.mean(r_vals[mask] / (2 * sin_half))
        r_pred = 2 * f_es * np.sin(theta_rad / 2)
        rms = np.sqrt(np.mean((r_vals - r_pred) ** 2))
        results["equisolid"] = {"f": float(f_es), "rms": float(rms)}

    # Stereographic: r = 2f * tan(theta/2)
    safe = theta_rad < np.radians(170)
    if (mask & safe).sum() >= 2:
        tan_half = np.tan(theta_rad[mask & safe] / 2)
        tan_half[tan_half < 0.001] = 0.001
        f_st = np.mean(r_vals[mask & safe] / (2 * tan_half))
        r_pred_safe = 2 * f_st * np.tan(theta_rad[safe] / 2)
        rms = np.sqrt(np.mean((r_vals[safe] - r_pred_safe) ** 2))
        results["stereographic"] = {"f": float(f_st), "rms": float(rms)}

    # Polynomial: r = a0 + a1*theta + a2*theta^2 + a3*theta^3
    if len(samples) >= 4:
        coeffs = np.polyfit(theta_rad, r_vals, 3)
        r_pred = np.polyval(coeffs, theta_rad)
        rms = np.sqrt(np.mean((r_vals - r_pred) ** 2))
        results["polynomial"] = {
            "coeffs": [float(c) for c in coeffs],
            "rms": float(rms),
        }

    return results


def input_thread_func(prompt_q, result_q):
    while True:
        prompt = prompt_q.get()
        if prompt is None:
            break
        try:
            val = input(prompt)
            result_q.put(val.strip())
        except EOFError:
            result_q.put(None)
            break


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wall-distance", type=float, default=0,
                        help="Distance to wall in mm. If set, enter offsets instead of angles.")
    args = parser.parse_args()
    wall_mode = args.wall_distance > 0

    pygame.init()
    screen = pygame.display.set_mode((DISPLAY_SIZE, DISPLAY_SIZE))
    font = pygame.font.SysFont("monospace", 16)
    font_big = pygame.font.SysFont("monospace", 20)
    clock = pygame.time.Clock()

    cap = setup_camera()
    if not cap.isOpened():
        print("ERROR: Cannot open camera")
        return

    # Principal point (frame centre - good default for fisheye)
    pp_x = CAM_WIDTH / 2.0
    pp_y = CAM_HEIGHT / 2.0

    samples = []  # (r_pixels, theta_degrees)
    awaiting_input = False
    current_spot = None
    current_r = None

    prompt_q = queue.Queue()
    result_q = queue.Queue()
    input_t = threading.Thread(target=input_thread_func, args=(prompt_q, result_q), daemon=True)
    input_t.start()

    print("=== BEARING CALIBRATION ===")
    print(f"Camera: {CAM_WIDTH}x{CAM_HEIGHT}")
    print(f"Principal point: ({pp_x:.0f}, {pp_y:.0f})")
    if wall_mode:
        print(f"Wall mode: distance = {args.wall_distance}mm")
        print("Enter offset from centre in mm (positive = right/down)")
    else:
        print("Enter angle from optical axis in degrees")
    print()
    print("Point a bright light (phone flashlight) at the camera.")
    print("Move it to known angles, press Enter when prompted.")
    print("Type 'q' to finish and compute results.")
    print("Type 's' to skip (re-detect).")
    print()

    # Prompt for first point
    print("Start with the light at 0 degrees (dead centre of lens).")
    if wall_mode:
        prompt_q.put("  Offset from centre in mm (0 for centre): ")
    else:
        prompt_q.put("  Angle in degrees (0 for centre): ")
    awaiting_input = True

    running = True
    done = False

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
        fh, fw = frame_rgb.shape[:2]
        spot = find_bright_spot(frame)

        # Letterbox display
        scale_d = DISPLAY_SIZE / fw
        disp_h = int(fh * scale_d)
        y_off = (DISPLAY_SIZE - disp_h) // 2
        display_frame = cv2.resize(frame_rgb, (DISPLAY_SIZE, disp_h))
        screen.fill((0, 0, 0))
        surf = pygame.surfarray.make_surface(display_frame.swapaxes(0, 1))
        screen.blit(surf, (0, y_off))

        # Draw principal point crosshair
        pp_dx = int(pp_x * scale_d)
        pp_dy = int(pp_y * scale_d) + y_off
        pygame.draw.circle(screen, (50, 50, 50), (pp_dx, pp_dy), 5, 1)

        # Draw detected spot
        if spot is not None:
            sx = int(spot[0] * scale_d)
            sy = int(spot[1] * scale_d) + y_off
            pygame.draw.circle(screen, (255, 0, 0), (sx, sy), 8, 2)
            # Line from principal point to spot
            pygame.draw.line(screen, (255, 0, 0), (pp_dx, pp_dy), (sx, sy), 1)

            r = math.sqrt((spot[0] - pp_x) ** 2 + (spot[1] - pp_y) ** 2)
            current_spot = spot
            current_r = r

        # Draw captured samples
        for r_px, theta_d in samples:
            # Draw as dots on a radial line at the right distance
            angle_disp = math.radians(theta_d)
            dot_x = int(pp_dx + r_px * scale_d * math.cos(angle_disp))
            dot_y = int(pp_dy + r_px * scale_d * math.sin(angle_disp))
            pygame.draw.circle(screen, (0, 150, 0), (dot_x, dot_y), 3)

        # HUD
        if spot is not None and current_r is not None:
            txt = font_big.render(f"r = {current_r:.0f} px", True, (255, 100, 100))
            screen.blit(txt, (CENTRE - txt.get_width() // 2, y_off + 15))

        txt = font.render(f"{len(samples)} samples", True, (150, 150, 150))
        screen.blit(txt, (CENTRE - txt.get_width() // 2, DISPLAY_SIZE - y_off - 25))

        if done:
            txt = font_big.render("Done - see SSH", True, (0, 255, 0))
            screen.blit(txt, (CENTRE - txt.get_width() // 2, CENTRE - 10))

        # Check for input
        if awaiting_input:
            try:
                val = result_q.get_nowait()
                if val is None or val.lower() == 'q':
                    if len(samples) >= 3:
                        done = True
                        awaiting_input = False
                    else:
                        print("  Need at least 3 samples. Keep going.")
                        if wall_mode:
                            prompt_q.put("  Offset in mm: ")
                        else:
                            prompt_q.put("  Angle in degrees: ")
                elif val.lower() == 's':
                    print("  Skipped. Reposition and try again.")
                    if wall_mode:
                        prompt_q.put("  Offset in mm: ")
                    else:
                        prompt_q.put("  Angle in degrees: ")
                else:
                    try:
                        num = float(val)
                        if wall_mode:
                            theta = math.degrees(math.atan2(abs(num), args.wall_distance))
                        else:
                            theta = abs(num)

                        if current_r is not None:
                            samples.append((current_r, theta))
                            print(f"  Captured: r={current_r:.1f}px  theta={theta:.1f}deg")
                            print()
                            print(f"Move light to next angle ({len(samples)} samples so far).")
                            if wall_mode:
                                prompt_q.put("  Offset in mm (or 'q' to finish): ")
                            else:
                                prompt_q.put("  Angle in degrees (or 'q' to finish): ")
                        else:
                            print("  No bright spot detected. Point the light at the camera.")
                            if wall_mode:
                                prompt_q.put("  Offset in mm: ")
                            else:
                                prompt_q.put("  Angle in degrees: ")
                    except ValueError:
                        print("  Invalid number.")
                        if wall_mode:
                            prompt_q.put("  Offset in mm: ")
                        else:
                            prompt_q.put("  Angle in degrees: ")
            except queue.Empty:
                pass

        # Compute and display results
        if done and samples:
            results = fit_fisheye_models(samples)

            print()
            print("=== RESULTS ===")
            print(f"Samples: {len(samples)}")
            print()

            best_name = None
            best_rms = float("inf")
            for name, info in results.items():
                rms = info["rms"]
                if name == "polynomial":
                    c = info["coeffs"]
                    print(f"  {name}: rms={rms:.2f}px  coeffs={[f'{x:.4f}' for x in c]}")
                else:
                    print(f"  {name}: f={info['f']:.1f}px  rms={rms:.2f}px")
                if rms < best_rms:
                    best_rms = rms
                    best_name = name

            print()
            print(f"Best fit: {best_name} (rms={best_rms:.2f}px)")

            # Build lookup table (every 0.5 degrees)
            best = results[best_name]
            lut = {}
            for theta_d_10 in range(0, 1800, 5):
                theta_d = theta_d_10 / 10.0
                theta_r = math.radians(theta_d)
                if best_name == "equidistant":
                    r = best["f"] * theta_r
                elif best_name == "equisolid":
                    r = 2 * best["f"] * math.sin(theta_r / 2)
                elif best_name == "stereographic":
                    if theta_d >= 170:
                        break
                    r = 2 * best["f"] * math.tan(theta_r / 2)
                elif best_name == "polynomial":
                    r = np.polyval(best["coeffs"], theta_r)
                lut[f"{theta_d:.1f}"] = round(float(r), 1)

            # Save
            cal_data = {
                "lens": "1.7mm fisheye",
                "sensor": "OV9281",
                "resolution": [CAM_WIDTH, CAM_HEIGHT],
                "principal_point": [float(pp_x), float(pp_y)],
                "best_model": best_name,
                "models": results,
                "samples": [{"r_px": s[0], "theta_deg": s[1]} for s in samples],
                "lookup_table_deg_to_px": lut,
            }
            with open("calibration.json", "w") as f:
                json.dump(cal_data, f, indent=2)
            print()
            print("Saved to calibration.json")
            print()

            # Print sample table
            print("Angle -> Pixel radius:")
            for td in [0, 10, 20, 30, 45, 60, 75, 90]:
                key = f"{float(td):.1f}"
                if key in lut:
                    print(f"  {td:3d}deg -> {lut[key]:.0f}px")

            running = False

        pygame.display.flip()
        clock.tick(30)

    prompt_q.put(None)
    cap.release()
    pygame.quit()


if __name__ == "__main__":
    main()
