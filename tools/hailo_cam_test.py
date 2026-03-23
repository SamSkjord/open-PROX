#!/usr/bin/env python3
"""Test script: USB camera feed with YOLOv8 detection boxes on DSI display.

Captures from /dev/video0, runs inference on Hailo-10H using the InferModel API,
draws bounding boxes and class labels, renders to 720x720 display via pygame KMSDRM.
"""

import time
import cv2
import numpy as np
import pygame
from hailo_platform import HEF, VDevice, FormatOrder, FormatType

# COCO class names (80 classes for YOLOv8)
COCO_NAMES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]

MODEL_PATH = "/usr/share/hailo-models/yolov8m_h10.hef"
DISPLAY_SIZE = 720
CONFIDENCE_THRESHOLD = 0.5
CAM_WIDTH = 1280
CAM_HEIGHT = 720
MODEL_INPUT_SIZE = 640


def setup_camera():
    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, 30)
    return cap


def preprocess(frame, model_w, model_h):
    """Resize and pad frame to model input size, preserving aspect ratio."""
    h, w = frame.shape[:2]
    scale = min(model_w / w, model_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(frame, (new_w, new_h))
    padded = np.full((model_h, model_w, 3), 114, dtype=np.uint8)
    y_off = (model_h - new_h) // 2
    x_off = (model_w - new_w) // 2
    padded[y_off:y_off + new_h, x_off:x_off + new_w] = resized
    return padded, scale, x_off, y_off


def postprocess_nms(nms_output, scale, x_off, y_off, frame_w, frame_h):
    """Parse NMS output: list of 80 arrays, each (N, 5) with [y1, x1, y2, x2, score] normalized."""
    detections = []
    for class_id, class_dets in enumerate(nms_output):
        if class_dets.shape[0] == 0:
            continue
        for det in class_dets:
            score = det[4]
            if score < CONFIDENCE_THRESHOLD:
                continue
            # Normalized coords (0-1) to model input pixel coords
            y1 = det[0] * MODEL_INPUT_SIZE
            x1 = det[1] * MODEL_INPUT_SIZE
            y2 = det[2] * MODEL_INPUT_SIZE
            x2 = det[3] * MODEL_INPUT_SIZE
            # Remove padding and rescale to original frame coords
            x1 = (x1 - x_off) / scale
            y1 = (y1 - y_off) / scale
            x2 = (x2 - x_off) / scale
            y2 = (y2 - y_off) / scale
            # Clip
            x1 = max(0, min(x1, frame_w))
            y1 = max(0, min(y1, frame_h))
            x2 = max(0, min(x2, frame_w))
            y2 = max(0, min(y2, frame_h))
            detections.append((class_id, float(score), x1, y1, x2, y2))
    return detections


def draw_detections(surface, detections, frame_w, frame_h, display_size, font):
    """Draw bounding boxes and labels onto pygame surface."""
    scale_x = display_size / frame_w
    scale_y = display_size / frame_h

    for class_id, score, x1, y1, x2, y2 in detections:
        sx1 = int(x1 * scale_x)
        sy1 = int(y1 * scale_y)
        sx2 = int(x2 * scale_x)
        sy2 = int(y2 * scale_y)

        colour = (0, 255, 0)
        if class_id < len(COCO_NAMES) and COCO_NAMES[class_id] in ("car", "truck", "bus", "motorcycle"):
            colour = (255, 100, 0)

        pygame.draw.rect(surface, colour, (sx1, sy1, sx2 - sx1, sy2 - sy1), 2)

        name = COCO_NAMES[class_id] if class_id < len(COCO_NAMES) else str(class_id)
        label = f"{name} {score:.0%}"
        label_surface = font.render(label, True, colour)
        surface.blit(label_surface, (sx1, max(0, sy1 - 18)))


def main():
    # Init pygame on KMSDRM
    pygame.init()
    screen = pygame.display.set_mode((DISPLAY_SIZE, DISPLAY_SIZE))
    pygame.display.set_caption("Hailo Detection Test")
    font = pygame.font.SysFont("monospace", 16)
    clock = pygame.time.Clock()

    # Init camera
    cap = setup_camera()
    if not cap.isOpened():
        print("ERROR: Cannot open camera")
        return

    # Init Hailo using InferModel API (required for H10 with NMS models)
    with VDevice() as vdevice:
        infer_model = vdevice.create_infer_model(MODEL_PATH)
        infer_model.input().set_format_type(FormatType.UINT8)

        # Detect NMS output format
        nms_output = False
        nms_orders = (FormatOrder.HAILO_NMS_WITH_BYTE_MASK,
                      FormatOrder.HAILO_NMS_BY_CLASS,
                      FormatOrder.HAILO_NMS_BY_SCORE,
                      FormatOrder.HAILO_NMS_ON_CHIP)
        for output in infer_model.outputs:
            if output.format.order in nms_orders:
                nms_output = True
                print(f"Output '{output.name}': NMS ({output.format.order})")
            else:
                output.set_format_type(FormatType.FLOAT32)
                print(f"Output '{output.name}': {output.shape}")

        input_shape = infer_model.input().shape
        model_h, model_w = input_shape[0], input_shape[1]
        print(f"Model input: {model_w}x{model_h}")

        with infer_model.configure() as configured_model:
            # Pre-allocate bindings and buffers once (reused every frame)
            output_buffers = {
                out.name: np.empty(out.shape, dtype=np.float32)
                for out in infer_model.outputs
            }
            bindings = configured_model.create_bindings(output_buffers=output_buffers)

            print("Running - press ESC to quit")
            running = True
            fps_avg = 0

            while running:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        running = False

                ret, frame = cap.read()
                if not ret:
                    continue

                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                fh, fw = frame_rgb.shape[:2]

                # Preprocess
                input_data, scale, x_off, y_off = preprocess(frame_rgb, model_w, model_h)

                # Reuse bindings, just update input buffer
                bindings.input().set_buffer(np.array(input_data))

                t0 = time.monotonic()
                try:
                    configured_model.run([bindings], 30000)
                    t_infer = (time.monotonic() - t0) * 1000
                except Exception as e:
                    print(f"Inference error: {e}")
                    t_infer = 0
                    detections = []
                    time.sleep(0.5)
                    continue

                # Parse detections
                if nms_output:
                    raw = bindings.output().get_buffer()
                    detections = postprocess_nms(raw, scale, x_off, y_off, fw, fh)
                else:
                    detections = []

                # Render camera frame to display (crop to square centre)
                cx = fw // 2
                half = min(fw, fh) // 2
                square = frame_rgb[:, cx - half:cx + half]
                display_frame = cv2.resize(square, (DISPLAY_SIZE, DISPLAY_SIZE))

                surf = pygame.surfarray.make_surface(display_frame.swapaxes(0, 1))
                screen.blit(surf, (0, 0))

                # Draw detection boxes (adjust for square crop)
                crop_x1 = cx - half
                crop_dets = [
                    (cid, s, bx1 - crop_x1, by1, bx2 - crop_x1, by2)
                    for cid, s, bx1, by1, bx2, by2 in detections
                ]
                draw_detections(screen, crop_dets, half * 2, fh, DISPLAY_SIZE, font)

                # HUD
                fps_avg = fps_avg * 0.9 + clock.get_fps() * 0.1
                hud = font.render(
                    f"FPS: {fps_avg:.0f}  Infer: {t_infer:.0f}ms  Det: {len(detections)}",
                    True, (255, 255, 255),
                )
                screen.blit(hud, (10, DISPLAY_SIZE - 26))

                pygame.display.flip()
                clock.tick(30)

    cap.release()
    pygame.quit()
    print("Done")


if __name__ == "__main__":
    main()
