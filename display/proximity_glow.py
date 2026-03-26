import pygame


def draw_proximity_glow(surface, contacts_screen, contacts, cx, cy,
                        glow_colour, glow_max_alpha, glow_range_m,
                        glow_radius_px, pixels_per_metre):
    """Draw orange radial glow around close contacts.

    Uses colorkey transparency instead of SRCALPHA to avoid GPU DMA
    conflicts with Hailo PCIe on Pi 5 KMSDRM.
    """
    for (sx, sy), contact in zip(contacts_screen, contacts):
        if contact["state"] == "COASTED":
            continue
        range_m = contact["range_m"]
        if range_m is None or range_m > glow_range_m:
            continue

        proximity = 1.0 - (range_m / glow_range_m)
        radius = int(glow_radius_px * (0.3 + 0.7 * proximity))
        intensity = proximity

        if intensity < 0.1 or radius < 10:
            continue

        _draw_radial_glow(surface, int(sx), int(sy), radius,
                          glow_colour, intensity)


def _draw_radial_glow(surface, cx, cy, radius, colour, intensity):
    """Draw a soft radial gradient circle using concentric opaque circles."""
    steps = 6
    for i in range(steps, 0, -1):
        t = i / steps
        r = int(radius * t)
        fade = (1.0 - t) * 1.5 * intensity
        fade = min(fade, intensity)
        # Blend colour toward background
        c = (int(colour[0] * fade), int(colour[1] * fade), int(colour[2] * fade))
        if r > 0 and max(c) > 5:
            pygame.draw.circle(surface, c, (cx, cy), r)
