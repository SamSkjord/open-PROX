#!/usr/bin/env python3
"""open-PROX - Proximity Awareness System.

On Pi with camera + Hailo: live detection pipeline.
On desktop or without hardware: synthetic targets.

Detection runs in a separate process to isolate Hailo PCIe DMA from
pygame's GPU DMA operations. The two share frame data and results
via shared memory / multiprocessing primitives.
"""

import time
import multiprocessing as mp
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


def _detect_worker(frame_queue, result_queue, stop_event):
    """Detection worker - runs in separate process.

    Completely isolates Hailo PCIe DMA from the main process's GPU DMA.
    """
    from detect.yolo import YoloDetector

    try:
        detector = YoloDetector()
        result_queue.put(("status", "OK"))
        print("Hailo detector ready (worker process)")
    except Exception as e:
        print(f"WARNING: Cannot init Hailo detector: {e}")
        result_queue.put(("status", "ERROR"))
        return

    while not stop_event.is_set():
        try:
            item = frame_queue.get(timeout=0.5)
        except Exception:
            continue

        if item is None:
            break

        side, frame_rgb, fw, ts = item
        try:
            dets = detector.detect(frame_rgb)
            # Convert Detection objects to serialisable dicts
            det_dicts = []
            for d in dets:
                det_dicts.append({
                    "class_id": d.class_id, "score": d.score,
                    "x1": d.x1, "y1": d.y1, "x2": d.x2, "y2": d.y2,
                    "width": d.width, "height": d.height,
                })
            result_queue.put(("dets", side, det_dicts, fw, ts))
        except Exception as e:
            print(f"Detection error ({side}): {e}")
            result_queue.put(("status", "ERROR"))

    detector.close()
    print("Detection worker stopped")


def run_live():
    """Live camera pipeline: ingest -> detect -> range -> fuse -> track -> display."""
    from range.monocular import detections_to_contacts
    from detect.yolo import Detection
    from fusion.passthrough import fuse
    from track.sort import SortTracker

    renderer = Renderer()
    tracker = SortTracker()

    cameras = _open_cameras()
    if not cameras:
        print("ERROR: No cameras available")
        renderer.shutdown()
        return

    if config.CAM_TYPE == "csi":
        time.sleep(0.5)

    # Start detection in a separate process
    frame_queue = mp.Queue(maxsize=2)
    result_queue = mp.Queue(maxsize=10)
    stop_event = mp.Event()

    det_proc = mp.Process(target=_detect_worker,
                          args=(frame_queue, result_queue, stop_event),
                          daemon=True)
    det_proc.start()

    # Wait for detector status
    try:
        status_msg = result_queue.get(timeout=30)
        if status_msg[0] == "status":
            renderer.detect_status = status_msg[1]
    except Exception:
        renderer.detect_status = "ERROR"

    print(f"Pipeline running - {len(cameras)} camera(s)")

    try:
        running = True
        latest_results = {}  # side -> (det_dicts, fw, ts)

        while running:
            running = renderer.handle_events()

            # Grab frames and submit for detection
            for cam in cameras:
                if not cam.grab():
                    continue

                renderer.set_camera_frame(cam.frame_rgb, cam.side)

                # Submit frame if queue has space (non-blocking)
                try:
                    frame_queue.put_nowait((
                        cam.side, cam.frame_rgb,
                        cam.frame_rgb.shape[1], cam.timestamp_ns
                    ))
                except Exception:
                    pass  # Queue full, skip this frame

            # Collect any detection results (non-blocking)
            while True:
                try:
                    msg = result_queue.get_nowait()
                    if msg[0] == "dets":
                        _, side, det_dicts, fw, ts = msg
                        latest_results[side] = (det_dicts, fw, ts)
                    elif msg[0] == "status":
                        renderer.detect_status = msg[1]
                except Exception:
                    break

            # Convert results to contacts
            all_contacts = []
            for side, (det_dicts, fw, ts) in latest_results.items():
                # Reconstruct Detection objects
                dets = [Detection(d["class_id"], d["score"],
                                  d["x1"], d["y1"], d["x2"], d["y2"])
                        for d in det_dicts]
                contacts = detections_to_contacts(dets, fw, ts, side)
                all_contacts.extend(contacts)

            fused = fuse(all_contacts)
            tracked = tracker.update(fused)
            renderer.render(tracked)
    finally:
        stop_event.set()
        try:
            frame_queue.put_nowait(None)
        except Exception:
            pass
        det_proc.join(timeout=5)
        if det_proc.is_alive():
            det_proc.kill()
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
