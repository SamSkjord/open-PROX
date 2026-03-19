import math
import pygame


_COLOUR = (255, 140, 0, 25)  # orange, low alpha
_ARC_STEPS = 60


def draw_coverage_cones(surface, cx, cy, pixels_per_metre, fov_deg, range_m):
    """Draw semi-transparent orange coverage arcs for left and right cameras."""
    radius = range_m * pixels_per_metre
    half_fov = fov_deg / 2.0

    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)

    # Left camera centred at 270°, right at 90°
    for centre_angle in (270.0, 90.0):
        start = centre_angle - half_fov
        end = centre_angle + half_fov
        _draw_cone(overlay, cx, cy, radius, start, end)

    surface.blit(overlay, (0, 0))


def _draw_cone(surface, cx, cy, radius, start_deg, end_deg):
    """Draw a filled pie slice on an SRCALPHA surface."""
    points = [(cx, cy)]
    for i in range(_ARC_STEPS + 1):
        angle_deg = start_deg + (end_deg - start_deg) * i / _ARC_STEPS
        angle_rad = math.radians(angle_deg)
        x = cx + radius * math.sin(angle_rad)
        y = cy - radius * math.cos(angle_rad)
        points.append((x, y))
    pygame.draw.polygon(surface, _COLOUR, points)
