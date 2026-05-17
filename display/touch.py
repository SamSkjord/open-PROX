"""Direct evdev touch input for framebuffer rendering.

Reads from /dev/input/event1 (Goodix capacitive touchscreen) without
requiring SDL/pygame input handling.
"""

import os
import struct
import time

# evdev event format: time_sec, time_usec, type, code, value
_EVENT_FORMAT = "llHHi"
_EVENT_SIZE = struct.calcsize(_EVENT_FORMAT)

# Event types
_EV_ABS = 3
_EV_KEY = 1

# ABS codes
_ABS_MT_TRACKING_ID = 0x39
_ABS_MT_POSITION_X = 0x35
_ABS_MT_POSITION_Y = 0x36

# Key codes
_BTN_TOUCH = 0x14a

_fd = None


def touch_init(device="/dev/input/event1"):
    """Open the touchscreen input device."""
    global _fd
    try:
        _fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
    except Exception as e:
        print(f"Touch init failed: {e}")
        _fd = None


def touch_poll():
    """Poll for touch events. Returns (is_touching, x, y) or None if no events."""
    if _fd is None:
        return None

    touching = None
    x = None
    y = None

    try:
        while True:
            data = os.read(_fd, _EVENT_SIZE)
            if len(data) < _EVENT_SIZE:
                break
            _, _, ev_type, code, value = struct.unpack(_EVENT_FORMAT, data)

            if ev_type == _EV_KEY and code == _BTN_TOUCH:
                touching = value == 1
            elif ev_type == _EV_ABS:
                if code == _ABS_MT_POSITION_X:
                    x = value
                elif code == _ABS_MT_POSITION_Y:
                    y = value
    except BlockingIOError:
        pass
    except Exception:
        pass

    if touching is not None:
        return (touching, x, y)
    return None


def touch_close():
    """Close the touch device."""
    global _fd
    if _fd is not None:
        os.close(_fd)
        _fd = None
