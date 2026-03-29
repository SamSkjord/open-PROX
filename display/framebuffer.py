"""Direct framebuffer output - bypasses DRM/GPU entirely.

Writes raw pixels to /dev/fb0 via mmap. No GPU DMA, no page flips,
no conflict with Hailo PCIe VDMA.

Usage: call fb_init() once, then fb_update(surface) each frame.
"""

import os
import mmap
import ctypes

_fb_map = None
_fb_fd = None
_fb_size = 720 * 720 * 4


def fb_init():
    """Open and mmap the framebuffer. Disable console cursor."""
    global _fb_map, _fb_fd

    # Disable all VT consoles to prevent cursor bleedthrough
    for vt in range(8):
        try:
            with open(f"/sys/class/vtconsole/vtcon{vt}/bind", "w") as f:
                f.write("0")
        except Exception:
            pass

    # Hide cursor on tty1
    try:
        with open("/dev/tty1", "w") as f:
            f.write("\033[?25l")
    except Exception:
        pass

    _fb_fd = os.open("/dev/fb0", os.O_RDWR)
    _fb_map = mmap.mmap(_fb_fd, _fb_size, mmap.MAP_SHARED,
                        mmap.PROT_WRITE | mmap.PROT_READ)


def fb_update(surface):
    """Write a pygame surface to the framebuffer.

    Uses pygame.image.tobytes for fast conversion, then swaps R/B
    channels in-place via the mmap buffer.
    """
    if _fb_map is None:
        return

    # Get raw bytes from pygame - format "RGBX" gives us 32bpp with padding
    raw = surface.get_buffer().raw

    # raw is in pygame's native format (likely ARGB or XRGB on this platform)
    # Write directly - the byte order may need swapping
    _fb_map.seek(0)
    _fb_map.write(raw)


def fb_close():
    """Clean up framebuffer resources."""
    global _fb_map, _fb_fd
    if _fb_map is not None:
        _fb_map.close()
        _fb_map = None
    if _fb_fd is not None:
        os.close(_fb_fd)
        _fb_fd = None
