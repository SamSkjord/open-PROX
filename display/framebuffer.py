"""Direct framebuffer output - bypasses DRM/GPU entirely.

Writes raw pixels to /dev/fb0 via mmap. No GPU DMA, no page flips,
no conflict with Hailo PCIe VDMA.

Usage: call fb_init() once, then fb_update(surface) each frame.
"""

import os
import mmap
import numpy as np

_fb_map = None
_fb_fd = None
_fb_w = 720
_fb_h = 720


def fb_init():
    """Open and mmap the framebuffer. Disable DRM console."""
    global _fb_map, _fb_fd

    # Disable DRM console so it doesn't overwrite our pixels
    try:
        with open("/sys/class/vtconsole/vtcon1/bind", "w") as f:
            f.write("0")
    except Exception:
        pass

    _fb_fd = os.open("/dev/fb0", os.O_RDWR)
    fb_size = _fb_w * _fb_h * 4  # 32bpp BGRA
    _fb_map = mmap.mmap(_fb_fd, fb_size, mmap.MAP_SHARED,
                        mmap.PROT_WRITE | mmap.PROT_READ)


def fb_update(surface):
    """Write a pygame surface to the framebuffer.

    Converts the surface's RGB pixel data to BGRA and writes to fb0.
    """
    if _fb_map is None:
        return

    # Get raw pixel data from pygame surface as RGB array
    import pygame
    arr = pygame.surfarray.pixels3d(surface)  # (w, h, 3) RGB
    # Transpose from pygame's (w,h) to numpy's (h,w)
    arr = arr.transpose(1, 0, 2)

    # Convert RGB to BGRA for framebuffer
    bgra = np.empty((_fb_h, _fb_w, 4), dtype=np.uint8)
    bgra[:, :, 0] = arr[:, :, 2]  # B
    bgra[:, :, 1] = arr[:, :, 1]  # G
    bgra[:, :, 2] = arr[:, :, 0]  # R
    bgra[:, :, 3] = 255            # A

    _fb_map.seek(0)
    _fb_map.write(bgra.tobytes())


def fb_close():
    """Clean up framebuffer resources."""
    global _fb_map, _fb_fd
    if _fb_map is not None:
        _fb_map.close()
        _fb_map = None
    if _fb_fd is not None:
        os.close(_fb_fd)
        _fb_fd = None
