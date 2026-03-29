"""Detection worker process - runs Hailo inference in isolation.

This module must NOT import pygame or any display code. It runs in a
separate process to isolate Hailo PCIe DMA from the GPU.
"""

import config


def detect_worker(frame_queue, result_queue, stop_event):
    """Detection worker entry point for multiprocessing."""
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
