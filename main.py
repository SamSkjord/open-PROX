#!/usr/bin/env python3
"""open-PROX - Proximity Awareness System.

On Pi with camera + Hailo: live detection pipeline.
On desktop or without hardware: synthetic targets.
"""

import sys
import config
from display.renderer import Renderer


def run_live():
    """Live camera pipeline: ingest -> detect -> range -> track -> display."""
    from ingest.camera import Camera
    from detect.yolo import YoloDetector
    from range.monocular import detections_to_contacts
    from track.sort import SortTracker

    renderer = Renderer()
    tracker = SortTracker()

    camera = Camera()
    if not camera.open():
        print("ERROR: Cannot open camera")
        return

    try:
        detector = YoloDetector()
    except Exception as e:
        print(f"ERROR: Cannot init Hailo detector: {e}")
        camera.close()
        return

    print("Pipeline running")

    try:
        running = True
        while running:
            running = renderer.handle_events()

            if not camera.grab():
                continue

            renderer.set_camera_frame(camera.frame_rgb)

            try:
                detections = detector.detect(camera.frame_rgb)
            except Exception as e:
                print(f"Detection error: {e}")
                continue

            raw_contacts = detections_to_contacts(
                detections, camera.frame_rgb.shape[1], camera.timestamp_ns
            )

            contacts = tracker.update(raw_contacts)
            renderer.render(contacts)
    finally:
        detector.close()
        camera.close()
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
    try:
        from hailo_platform import VDevice
        import cv2
        # Quick check: can we open a camera?
        cap = cv2.VideoCapture(config.CAM_DEVICE, cv2.CAP_V4L2)
        has_cam = cap.isOpened()
        cap.release()
        if has_cam:
            print("Hardware detected - starting live pipeline")
            run_live()
            return
    except (ImportError, Exception):
        pass

    print("No hardware - starting with synthetic targets")
    run_synthetic()


if __name__ == "__main__":
    main()
