import pygame
import config

# Pre-rendered glow sprites at different sizes, built once at import time.
# Each sprite is a single opaque surface with colorkey transparency.
# Blitting one pre-rendered sprite per contact is fast (single DMA op),
# unlike drawing concentric circles per frame which hammers the GPU DMA bus
# and causes Hailo PCIe VDMA conflicts.

_GLOW_SPRITES = {}  # radius -> Surface
_BG = config.DISPLAY_BG_COLOUR


def _build_glow_sprite(radius, colour):
    """Pre-render a radial glow sprite as an opaque surface with colorkey."""
    size = radius * 2 + 2
    surf = pygame.Surface((size, size))
    surf.fill(_BG)
    surf.set_colorkey(_BG)
    cx, cy = size // 2, size // 2

    steps = 8
    for i in range(steps, 0, -1):
        t = i / steps
        r = int(radius * t)
        fade = (1.0 - t) * 1.5
        fade = min(fade, 1.0)
        c = (int(colour[0] * fade), int(colour[1] * fade), int(colour[2] * fade))
        if r > 0 and max(c) > 5:
            pygame.draw.circle(surf, c, (cx, cy), r)

    return surf


def _get_glow_sprite(radius, colour):
    """Get or create a cached glow sprite for this radius."""
    # Quantise radius to nearest 5px to limit cache size
    key = (radius // 5) * 5
    if key < 10:
        return None
    if key not in _GLOW_SPRITES:
        _GLOW_SPRITES[key] = _build_glow_sprite(key, colour)
    return _GLOW_SPRITES[key]


def draw_proximity_glow(surface, contacts_screen, contacts, cx, cy,
                        glow_colour, glow_max_alpha, glow_range_m,
                        glow_radius_px, pixels_per_metre):
    """Draw orange radial glow around close contacts using pre-rendered sprites."""
    for (sx, sy), contact in zip(contacts_screen, contacts):
        if contact["state"] == "COASTED":
            continue
        range_m = contact["range_m"]
        if range_m is None or range_m > glow_range_m:
            continue

        proximity = 1.0 - (range_m / glow_range_m)
        radius = int(glow_radius_px * (0.3 + 0.7 * proximity))

        if proximity < 0.1 or radius < 10:
            continue

        sprite = _get_glow_sprite(radius, glow_colour)
        if sprite is None:
            continue

        # Centre the sprite on the contact position
        sw, sh = sprite.get_size()
        surface.blit(sprite, (int(sx) - sw // 2, int(sy) - sh // 2))
