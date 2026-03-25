"""CSI camera capture via picamera2 with monotonic timestamps."""

import time
import numpy as np
import config

from picamera2 import Picamera2


class CsiCamera:
    def __init__(self, camera_num, side):
        self.camera_num = camera_num
        self.side = side
        self.picam = None
        self.frame_rgb = None
        self.timestamp_ns = 0

    def open(self):
        self.picam = Picamera2(self.camera_num)
        cam_config = self.picam.create_video_configuration(
            main={"size": (config.CAM_WIDTH, config.CAM_HEIGHT),
                  "format": "RGB888"},
            controls={"FrameRate": config.CAM_FPS},
        )
        self.picam.configure(cam_config)
        self.picam.start()
        return True

    def grab(self):
        """Grab a frame. Returns True if successful.

        Timestamp is captured on buffer arrival, before conversion.
        """
        if self.picam is None:
            return False
        array = self.picam.capture_array("main")
        self.timestamp_ns = time.monotonic_ns()
        if array is None:
            return False
        self.frame_rgb = array
        return True

    def close(self):
        if self.picam is not None:
            self.picam.stop()
            self.picam.close()
            self.picam = None
