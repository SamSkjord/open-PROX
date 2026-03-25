#!/usr/bin/env python3
"""open-PROX - Proximity Awareness System.

On Pi with camera + Hailo: live detection pipeline.
On desktop or without hardware: synthetic targets.

Supports CSI (picamera2) and USB (V4L2) cameras.
"""

import time
import threading
import config
from display.renderer import Renderer


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
        try:
            from picamera2 import Picamera2
            info = Picamera2.global_camera_info()
            return len(info) > 0
        except Exception:
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

    def detect_thread():
        detector = None
        try:
            detector = YoloDetector()
            print("Hailo detector ready")
        except Exception as e:
            print(f"ERROR: Cannot init Hailo detector: {e}")
            return

        last_detect_time = 0
        while not detect_shutdown.is_set():
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

    print(f"Pipeline running - {len(cameras)} camera(s)")

    try:
        running = True
        while running:
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
        detect_shutdown.set()
        det_thread.join(timeout=5)
        for cam in cameras:
            cam.close()
        renderer.shutdown()


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
