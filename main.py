#!/usr/bin/env python3
"""open-PROX - Proximity Awareness System.

On Pi with camera + Hailo: live detection pipeline.
On desktop or without hardware: synthetic targets.

Supports CSI (picamera2) and USB (V4L2) cameras.
"""

import os
import signal
import subprocess
import sys
import time
import threading
import config
from display.renderer import Renderer


# -- Hailo recovery helpers --

def _reset_hailo():
    """Try to reset the Hailo device via PCIe bus reset. Requires root."""
    try:
        subprocess.run(
            ["sudo", "rmmod", "hailo1x_pci"],
            capture_output=True, timeout=5
        )
        time.sleep(1)
        # PCIe remove + rescan
        pci_addr = "0001:01:00.0"
        remove_path = f"/sys/bus/pci/devices/{pci_addr}/remove"
        if os.path.exists(remove_path):
            subprocess.run(
                ["sudo", "sh", "-c", f"echo 1 > {remove_path}"],
                capture_output=True, timeout=5
            )
            time.sleep(2)
        subprocess.run(
            ["sudo", "sh", "-c", "echo 1 > /sys/bus/pci/rescan"],
            capture_output=True, timeout=5
        )
        time.sleep(3)
        subprocess.run(
            ["sudo", "modprobe", "hailo1x_pci"],
            capture_output=True, timeout=5
        )
        # Wait for firmware to load
        for _ in range(10):
            if os.path.exists("/dev/hailo0"):
                print("Hailo device reset successfully")
                return True
            time.sleep(1)
    except Exception as e:
        print(f"Hailo reset failed: {e}")
    return False


def _open_cameras():
    """Open cameras based on CAM_TYPE config. Returns list of camera objects."""
    cameras = []

    if config.CAM_TYPE == "csi":
        from ingest.csi_camera import CsiCamera
        for device, side in [(config.CSI_RIGHT_DEVICE, "RIGHT"),
                             (config.CSI_LEFT_DEVICE, "LEFT")]:
            if device < 0:
                continue
            cam = CsiCamera(device, side)
            try:
                cam.open()
                cameras.append(cam)
                print(f"CSI camera {side}: picam{device}")
            except Exception as e:
                print(f"WARNING: Cannot open {side} CSI camera {device}: {e}")
    else:
        from ingest.camera import Camera
        for device, side in [(config.CAM_RIGHT_DEVICE, "RIGHT"),
                             (config.CAM_LEFT_DEVICE, "LEFT")]:
            if device < 0:
                continue
            cam = Camera(device, side)
            if cam.open():
                cameras.append(cam)
                print(f"USB camera {side}: /dev/video{device}")
            else:
                print(f"WARNING: Cannot open {side} camera on /dev/video{device}")

    return cameras


def _detect_camera_available():
    """Check if any camera is available for live pipeline."""
    if config.CAM_TYPE == "csi":
        from picamera2 import Picamera2
        # CSI cameras may take a few seconds to register after boot
        for attempt in range(5):
            try:
                info = Picamera2.global_camera_info()
                if len(info) > 0:
                    return True
            except Exception:
                pass
            if attempt < 4:
                time.sleep(2)
        return False
    else:
        import cv2
        for dev in [config.CAM_RIGHT_DEVICE, config.CAM_LEFT_DEVICE]:
            if dev < 0:
                continue
            cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
            if cap.isOpened():
                cap.release()
                return True
            cap.release()
        return False


def run_live():
    """Live camera pipeline: ingest -> detect -> range -> fuse -> track -> display."""
    from detect.yolo import YoloDetector
    from range.monocular import detections_to_contacts
    from fusion.passthrough import fuse
    from track.sort import SortTracker

    renderer = Renderer()
    tracker = SortTracker()

    cameras = _open_cameras()
    if not cameras:
        print("ERROR: No cameras available")
        renderer.shutdown()
        return

    # Let auto-exposure settle for CSI cameras
    if config.CAM_TYPE == "csi":
        time.sleep(0.5)

    # -- Threaded detection (prevents Hailo DMA / KMSDRM conflicts) --
    detect_lock = threading.Lock()
    detect_results = {}  # side -> (detections, frame_width, timestamp_ns)
    detect_frames = {}   # side -> (frame, frame_width, timestamp_ns)
    detect_frame_ready = threading.Event()
    detect_shutdown = threading.Event()
    detect_interval = (1.0 / config.DETECT_MAX_FPS) if config.DETECT_MAX_FPS > 0 else 0

    def _try_init_detector():
        """Try to create a YoloDetector, with PCIe reset fallback."""
        try:
            det = YoloDetector()
            renderer.detect_status = "OK"
            return det
        except Exception as e:
            print(f"Hailo init failed: {e}")

        renderer.detect_status = "RECOVERING"
        print("Attempting Hailo PCIe reset...")
        if _reset_hailo():
            try:
                det = YoloDetector()
                renderer.detect_status = "OK"
                print("Hailo detector ready after reset")
                return det
            except Exception as e2:
                print(f"Hailo still failed after reset: {e2}")

        renderer.detect_status = "ERROR"
        return None

    def detect_thread():
        detector = _try_init_detector()
        if detector is not None:
            print("Hailo detector ready")

        last_detect_time = 0
        while not detect_shutdown.is_set():
            # If no detector, keep retrying every 10s
            if detector is None:
                if detect_shutdown.wait(timeout=10):
                    break
                detector = _try_init_detector()
                continue

            if not detect_frame_ready.wait(timeout=0.5):
                continue
            detect_frame_ready.clear()

            if detect_interval > 0:
                now = time.monotonic()
                if (now - last_detect_time) < detect_interval:
                    continue
                last_detect_time = now

            with detect_lock:
                frames_snapshot = dict(detect_frames)

            for side, (frame, fw, ts) in frames_snapshot.items():
                try:
                    dets = detector.detect(frame)
                    with detect_lock:
                        detect_results[side] = (dets, fw, ts)
                except Exception as e:
                    print(f"Detection error ({side}): {e}")
                    renderer.detect_status = "RECOVERING"
                    try:
                        detector.close()
                    except Exception:
                        pass
                    detector = None
                    time.sleep(1)
                    detector = _try_init_detector()
                    break

        if detector is not None:
            detector.close()

    det_thread = threading.Thread(target=detect_thread, daemon=True)
    det_thread.start()

    # -- Signal handling for clean shutdown --
    shutdown_requested = threading.Event()

    def _signal_handler(signum, frame):
        print(f"\nSignal {signum} received - shutting down")
        shutdown_requested.set()

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    print(f"Pipeline running - {len(cameras)} camera(s)")

    try:
        running = True
        while running and not shutdown_requested.is_set():
            running = renderer.handle_events()

            # Grab frames and submit for detection
            for cam in cameras:
                if not cam.grab():
                    continue

                renderer.set_camera_frame(cam.frame_rgb, cam.side)

                with detect_lock:
                    detect_frames[cam.side] = (
                        cam.frame_rgb.copy(), cam.frame_rgb.shape[1],
                        cam.timestamp_ns
                    )
                detect_frame_ready.set()

            # Collect latest detection results
            all_contacts = []
            with detect_lock:
                for side, (dets, fw, ts) in detect_results.items():
                    contacts = detections_to_contacts(dets, fw, ts, side)
                    all_contacts.extend(contacts)

            fused = fuse(all_contacts)
            tracked = tracker.update(fused)
            renderer.render(tracked)
    finally:
        print("Shutting down...")
        detect_shutdown.set()
        det_thread.join(timeout=5)
        for cam in cameras:
            cam.close()
        renderer.shutdown()
        print("Shutdown complete")


def run_synthetic():
    """Synthetic targets for desktop development."""
    from tools.synthetic_targets import SyntheticTargetGenerator
    from track.sort import SortTracker

    renderer = Renderer()
    generator = SyntheticTargetGenerator()
    tracker = SortTracker()

    running = True
    while running:
        running = renderer.handle_events()
        raw_contacts = generator.generate()
        contacts = tracker.update(raw_contacts)
        renderer.render(contacts)

    renderer.shutdown()


def main():
    # Try live pipeline first, fall back to synthetic
    has_hailo = False
    try:
        from hailo_platform import VDevice
        has_hailo = True
    except ImportError:
        pass

    if has_hailo and _detect_camera_available():
        print("Hardware detected - starting live pipeline")
        run_live()
        return

    print("No hardware - starting with synthetic targets")
    run_synthetic()


if __name__ == "__main__":
    main()
