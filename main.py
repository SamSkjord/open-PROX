#!/usr/bin/env python3
"""open-PROX - Proximity Awareness System.

On Pi with camera + Hailo: live detection pipeline.
On desktop or without hardware: synthetic targets.

Supports CSI (picamera2) and USB (V4L2) cameras.
"""

import time
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
        from picamera2 import Picamera2
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

    detector = None
    try:
        detector = YoloDetector()
        renderer.detect_status = "OK"
        print("Hailo detector ready")
    except Exception as e:
        print(f"WARNING: Cannot init Hailo detector: {e}")
        renderer.detect_status = "ERROR"

    print(f"Pipeline running - {len(cameras)} camera(s)")

    try:
        running = True
        while running:
            running = renderer.handle_events()

            all_contacts = []
            for cam in cameras:
                if not cam.grab():
                    continue

                renderer.set_camera_frame(cam.frame_rgb, cam.side)

                if detector is not None:
                    try:
                        detections = detector.detect(cam.frame_rgb)
                    except Exception as e:
                        print(f"Detection error ({cam.side}): {e}")
                        continue

                    contacts = detections_to_contacts(
                        detections, cam.frame_rgb.shape[1],
                        cam.timestamp_ns, cam.side
                    )
                    all_contacts.extend(contacts)

            fused = fuse(all_contacts)
            tracked = tracker.update(fused)
            renderer.render(tracked)
    finally:
        if detector is not None:
            detector.close()
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
