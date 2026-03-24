#!/usr/bin/env python3
"""open-PROX - Proximity Awareness System.

On Pi with camera + Hailo: live detection pipeline.
On desktop or without hardware: synthetic targets.

Supports one or two cameras (Config A: one per side, Config B: future stereo).
"""

import config
from display.renderer import Renderer


def run_live():
    """Live camera pipeline: ingest -> detect -> range -> fuse -> track -> display."""
    from ingest.camera import Camera
    from detect.yolo import YoloDetector
    from range.monocular import detections_to_contacts
    from fusion.passthrough import fuse
    from track.sort import SortTracker

    renderer = Renderer()
    tracker = SortTracker()

    # Open cameras
    cameras = []
    for device, side in [(config.CAM_RIGHT_DEVICE, "RIGHT"),
                         (config.CAM_LEFT_DEVICE, "LEFT")]:
        if device < 0:
            continue
        cam = Camera(device, side)
        if cam.open():
            cameras.append(cam)
            print(f"Camera {side}: /dev/video{device}")
        else:
            print(f"WARNING: Cannot open {side} camera on /dev/video{device}")

    if not cameras:
        print("ERROR: No cameras available")
        return

    try:
        detector = YoloDetector()
    except Exception as e:
        print(f"ERROR: Cannot init Hailo detector: {e}")
        for cam in cameras:
            cam.close()
        return

    print(f"Pipeline running - {len(cameras)} camera(s)")

    try:
        running = True
        while running:
            running = renderer.handle_events()

            all_contacts = []
            for cam in cameras:
                if not cam.grab():
                    continue

                # Show the first camera's feed in camera view
                if cam is cameras[0]:
                    renderer.set_camera_frame(cam.frame_rgb)

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
    # Try live pipeline first, fall back to synthetic
    try:
        from hailo_platform import VDevice
        import cv2
        # Check if any camera is available
        has_cam = False
        for dev in [config.CAM_RIGHT_DEVICE, config.CAM_LEFT_DEVICE]:
            if dev < 0:
                continue
            cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
            if cap.isOpened():
                has_cam = True
                cap.release()
                break
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
