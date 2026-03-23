"""Monocular range estimation from bounding box width."""

import math
import config


def estimate_range(detection, frame_width):
    """Estimate range to a detected vehicle using known-width method.

    Returns (range_m, angle_deg, side) or None if invalid.

    range = (known_width * focal_length_px) / bbox_width_px

    Bearing is derived from the detection's horizontal position in the frame.
    Camera is mounted sideways: frame centre = perpendicular to car side (90 or 270 deg).
    """
    bbox_w = detection.width
    if bbox_w < 5:
        return None

    range_m = (config.VEHICLE_WIDTH_M * config.FOCAL_LENGTH_PX) / bbox_w

    # Clamp to reasonable range
    if range_m > config.DISPLAY_RANGE_M * 2 or range_m < 0.3:
        return None

    # Bearing: pixel position maps to angle from perpendicular
    # Frame centre = 90 deg (right side) or 270 deg (left side)
    # Pixels ahead of centre = lower angle, behind = higher angle
    frame_centre_x = frame_width / 2.0
    # Fraction of frame from centre (-1 to +1)
    x_frac = (detection.cx - frame_centre_x) / frame_centre_x

    # For a fisheye, the mapping is roughly linear: pixel offset ~ angle
    # Half the FOV maps to the edge of the frame
    half_fov = config.LENS_FOV_DEG / 2.0
    bearing_offset = x_frac * half_fov

    if config.CAM_SIDE == "RIGHT":
        angle_deg = (90.0 + bearing_offset) % 360
        side = "RIGHT"
    else:
        angle_deg = (270.0 - bearing_offset) % 360
        side = "LEFT"

    return range_m, angle_deg, side


def detections_to_contacts(detections, frame_width, timestamp_ns):
    """Convert a list of Detection objects into track-compatible contact dicts."""
    contacts = []
    for i, det in enumerate(detections):
        result = estimate_range(det, frame_width)
        if result is None:
            continue
        range_m, angle_deg, side = result

        contacts.append({
            "id": 1000 + i,
            "side": side,
            "angle_deg": angle_deg,
            "range_m": range_m,
            "range_method": "mono",
            "range_confidence": det.score,
            "velocity": (0.0, 0.0),
            "closing_kph": 0.0,
            "confidence": det.score,
            "age_frames": 1,
            "last_seen_ns": timestamp_ns,
            "state": "ACTIVE",
            "occluded": False,
            "sources": {"camera"},
            "bbox": (det.x1, det.y1, det.x2, det.y2),
            "orientation": "SIDE",
        })

    return contacts
