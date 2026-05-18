"""Trip logger: per-frame contacts as JSONL plus periodic JPEG snapshots.

Each session writes to /home/pi/prox-logs/<timestamp>/.

  contacts.jsonl - one JSON line per frame
  frames/<n>.jpg - JPEG snapshots at FRAME_HZ

Writes are flushed line-by-line and fsynced every SYNC_EVERY frames so
an unannounced power loss loses at most ~1 second of data.
"""

import json
import os
import time
from datetime import datetime

LOG_ROOT = "/home/pi/prox-logs"
FRAME_HZ = 5
SYNC_EVERY = 30


class TripLogger:
    def __init__(self):
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.dir = os.path.join(LOG_ROOT, stamp)
        self.frames_dir = os.path.join(self.dir, "frames")
        os.makedirs(self.frames_dir, exist_ok=True)

        self.jsonl_path = os.path.join(self.dir, "contacts.jsonl")
        self.jsonl = open(self.jsonl_path, "w", buffering=1)
        self.jsonl_fd = self.jsonl.fileno()

        self.start_mono = time.monotonic()
        self.start_epoch = time.time()
        self.frame_idx = 0
        self.last_frame_save = 0.0
        self.frame_interval = 1.0 / FRAME_HZ
        self.frame_save_idx = 0

        meta = {
            "type": "session_start",
            "start_epoch": self.start_epoch,
            "start_mono": self.start_mono,
        }
        self._write(meta)
        print(f"Trip log: {self.dir}")

    def _write(self, obj):
        self.jsonl.write(json.dumps(obj, separators=(",", ":")) + "\n")
        self.frame_idx += 1
        if self.frame_idx % SYNC_EVERY == 0:
            self.jsonl.flush()
            os.fsync(self.jsonl_fd)

    def log_frame(self, contacts, camera_frame_rgb=None, side="RIGHT"):
        """Record one frame's tracked contacts. Save JPEG at rate-limit cadence."""
        now_mono = time.monotonic()
        entry = {
            "t": round(now_mono - self.start_mono, 3),
            "frame": self.frame_idx,
            "contacts": [
                {
                    "id": c.get("id"),
                    "side": c.get("side"),
                    "ang": round(c.get("angle_deg", 0), 1),
                    "rng": round(c.get("range_m", 0), 2),
                    "kph": round(c.get("closing_kph", 0), 1),
                    "state": c.get("state"),
                    "bbox": c.get("bbox"),
                }
                for c in contacts
            ],
        }
        self._write(entry)

        if camera_frame_rgb is not None and (now_mono - self.last_frame_save) >= self.frame_interval:
            self.last_frame_save = now_mono
            self.frame_save_idx += 1
            try:
                import cv2
                bgr = cv2.cvtColor(camera_frame_rgb, cv2.COLOR_RGB2BGR)
                path = os.path.join(self.frames_dir, f"{self.frame_save_idx:06d}_{side}.jpg")
                cv2.imwrite(path, bgr, [cv2.IMWRITE_JPEG_QUALITY, 75])
            except Exception as e:
                print(f"Frame save failed: {e}")

    def close(self):
        if self.jsonl is None:
            return
        self._write({"type": "session_end", "end_mono": time.monotonic() - self.start_mono})
        self.jsonl.flush()
        try:
            os.fsync(self.jsonl_fd)
        except Exception:
            pass
        self.jsonl.close()
        self.jsonl = None
