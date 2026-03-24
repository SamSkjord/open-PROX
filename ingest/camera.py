"""USB camera capture with monotonic timestamps."""

import time
import cv2
import config


class Camera:
    def __init__(self, device, side):
        self.device = device
        self.side = side
        self.cap = None
        self.frame_rgb = None
        self.timestamp_ns = 0

    def open(self):
        self.cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAM_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAM_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, config.CAM_FPS)
        return self.cap.isOpened()

    def grab(self):
        """Grab a frame. Returns True if successful.

        Timestamp is captured on buffer arrival, before decode.
        """
        if self.cap is None:
            return False
        ret = self.cap.grab()
        self.timestamp_ns = time.monotonic_ns()
        if not ret:
            return False
        ret, frame = self.cap.retrieve()
        if not ret:
            return False
        self.frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return True

    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None
