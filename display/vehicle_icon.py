import pygame


# ACC-style host car — clean top-down silhouette, pointing up.
_BODY = [
    (-8, 15),    # rear left
    (-9, 6),     # mid left (widest)
    (-8, -4),    # shoulder left
    (-6, -12),   # nose taper left
    (-3, -16),   # nose tip left
    (3, -16),    # nose tip right
    (6, -12),    # nose taper right
    (8, -4),     # shoulder right
    (9, 6),      # mid right (widest)
    (8, 15),     # rear right
]

_COLOUR_FILL = (45, 50, 55)
_COLOUR_OUTLINE = (180, 185, 190)


def draw_vehicle_icon(surface, cx, cy):
    """Draw the host vehicle at centre — light outline on dark fill."""
    body_pts = [(cx + x, cy + y) for x, y in _BODY]
    pygame.draw.polygon(surface, _COLOUR_FILL, body_pts)
    pygame.draw.aalines(surface, _COLOUR_OUTLINE, True, body_pts)
