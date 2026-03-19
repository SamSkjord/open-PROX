import pygame


def draw_proximity_glow(surface, contacts_screen, contacts, cx, cy,
                        glow_colour, glow_max_alpha, glow_range_m,
                        glow_radius_px, pixels_per_metre):
    """Draw orange radial glow around close contacts — the ACC signature look.

    contacts_screen: list of (sx, sy) screen positions matching contacts list.
    """
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)

    for (sx, sy), contact in zip(contacts_screen, contacts):
        if contact["state"] == "COASTED":
            continue
        range_m = contact["range_m"]
        if range_m is None or range_m > glow_range_m:
            continue

        # Closer = larger and brighter glow
        proximity = 1.0 - (range_m / glow_range_m)  # 0..1, 1 = touching
        radius = int(glow_radius_px * (0.3 + 0.7 * proximity))
        alpha = int(glow_max_alpha * proximity)

        if alpha < 5 or radius < 10:
            continue

        _draw_radial_glow(overlay, int(sx), int(sy), radius,
                          glow_colour, alpha)

    surface.blit(overlay, (0, 0))


def _draw_radial_glow(surface, cx, cy, radius, colour, peak_alpha):
    """Draw a soft radial gradient circle — bright centre fading to transparent."""
    steps = 8
    for i in range(steps, 0, -1):
        t = i / steps
        r = int(radius * t)
        a = int(peak_alpha * (1.0 - t) * 1.5)  # brighter toward centre
        a = min(a, peak_alpha)
        if r > 0 and a > 0:
            pygame.draw.circle(surface, (*colour, a), (cx, cy), r)
