"""YOLOv8 vehicle detection via Hailo-10H."""

import numpy as np
import config

try:
    from hailo_platform import HEF, VDevice, FormatOrder, FormatType
    HAILO_AVAILABLE = True
except ImportError:
    HAILO_AVAILABLE = False


class Detection:
    """A single detected object."""
    __slots__ = ("class_id", "score", "x1", "y1", "x2", "y2")

    def __init__(self, class_id, score, x1, y1, x2, y2):
        self.class_id = class_id
        self.score = score
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

    @property
    def width(self):
        return self.x2 - self.x1

    @property
    def height(self):
        return self.y2 - self.y1

    @property
    def cx(self):
        return (self.x1 + self.x2) / 2

    @property
    def cy(self):
        return (self.y1 + self.y2) / 2

    @property
    def is_vehicle(self):
        return self.class_id in config.VEHICLE_CLASS_IDS


class YoloDetector:
    """Hailo-10H YOLOv8 detector. Returns vehicle detections in frame coords."""

    def __init__(self):
        if not HAILO_AVAILABLE:
            raise RuntimeError("hailo_platform not available")

        self.vdevice = VDevice()
        self.infer_model = self.vdevice.create_infer_model(config.HAILO_MODEL_PATH)
        self.infer_model.input().set_format_type(FormatType.UINT8)

        # Check for NMS output
        self.nms_output = False
        nms_orders = (FormatOrder.HAILO_NMS_WITH_BYTE_MASK,
                      FormatOrder.HAILO_NMS_BY_CLASS,
                      FormatOrder.HAILO_NMS_BY_SCORE,
                      FormatOrder.HAILO_NMS_ON_CHIP)
        for output in self.infer_model.outputs:
            if output.format.order in nms_orders:
                self.nms_output = True

        self.input_shape = self.infer_model.input().shape
        self.model_h = self.input_shape[0]
        self.model_w = self.input_shape[1]

        self.configured_model = self.infer_model.configure().__enter__()

    def detect(self, frame_rgb):
        """Run detection on an RGB frame. Returns list of Detection objects."""
        fh, fw = frame_rgb.shape[:2]
        input_data, scale, x_off, y_off = self._preprocess(frame_rgb)

        # Reuse or create bindings
        output_buffers = {
            out.name: np.empty(out.shape, dtype=np.float32)
            for out in self.infer_model.outputs
        }
        bindings = self.configured_model.create_bindings(output_buffers=output_buffers)
        bindings.input().set_buffer(np.array(input_data))

        self.configured_model.run([bindings], 30000)

        if self.nms_output:
            raw = bindings.output().get_buffer()
            return self._parse_nms(raw, scale, x_off, y_off, fw, fh)
        return []

    def _preprocess(self, frame_rgb):
        """Resize and pad to model input size."""
        import cv2
        h, w = frame_rgb.shape[:2]
        scale = min(self.model_w / w, self.model_h / h)
        new_w, new_h = int(w * scale), int(h * scale)
        resized = cv2.resize(frame_rgb, (new_w, new_h))
        padded = np.full((self.model_h, self.model_w, 3), 114, dtype=np.uint8)
        y_off = (self.model_h - new_h) // 2
        x_off = (self.model_w - new_w) // 2
        padded[y_off:y_off + new_h, x_off:x_off + new_w] = resized
        return padded, scale, x_off, y_off

    def _parse_nms(self, nms_output, scale, x_off, y_off, frame_w, frame_h):
        """Parse NMS output into Detection objects. Only returns vehicles."""
        detections = []
        for class_id, class_dets in enumerate(nms_output):
            if class_dets.shape[0] == 0:
                continue
            if class_id not in config.VEHICLE_CLASS_IDS:
                continue
            for det in class_dets:
                score = det[4]
                if score < config.DETECT_CONFIDENCE:
                    continue
                y1 = (det[0] * self.model_h - y_off) / scale
                x1 = (det[1] * self.model_w - x_off) / scale
                y2 = (det[2] * self.model_h - y_off) / scale
                x2 = (det[3] * self.model_w - x_off) / scale
                x1 = max(0, min(x1, frame_w))
                y1 = max(0, min(y1, frame_h))
                x2 = max(0, min(x2, frame_w))
                y2 = max(0, min(y2, frame_h))
                detections.append(Detection(class_id, float(score), x1, y1, x2, y2))
        return detections

    def close(self):
        if self.configured_model is not None:
            self.configured_model.__exit__(None, None, None)
            self.configured_model = None
        if self.vdevice is not None:
            self.vdevice.release()
            self.vdevice = None
