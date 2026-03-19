import math
import pygame


_COLOUR_BLIP = (230, 230, 230)       # white car blips
_COLOUR_BLIP_OUTLINE = (255, 255, 255)
_COLOUR_COASTED = (70, 70, 70)
_COLOUR_COASTED_OUTLINE = (100, 100, 100)

# Car-shaped blip template (pointing up, normalised -0.5..+0.5)
_CAR_TEMPLATE = [
    (-0.5, 0.45),   # rear left
    (-0.5, -0.3),   # front-mid left
    (-0.35, -0.5),  # nose left
    (0.35, -0.5),   # nose right
    (0.5, -0.3),    # front-mid right
    (0.5, 0.45),    # rear right
]


def draw_contact(surface, screen_pos, contact, blip_w, blip_h):
    """Draw a white rotated car-shaped blip."""
    coasted = contact["state"] == "COASTED"
    fill = _COLOUR_COASTED if coasted else _COLOUR_BLIP
    outline = _COLOUR_COASTED_OUTLINE if coasted else _COLOUR_BLIP_OUTLINE

    vx, vy = contact["velocity"]
    if math.hypot(vx, vy) > 0.2:
        heading_deg = math.degrees(math.atan2(vx, vy))
    else:
        heading_deg = 0.0

    pts = _rotated_car(screen_pos[0], screen_pos[1],
                       blip_w, blip_h, heading_deg)
    pygame.draw.polygon(surface, fill, pts)
    pygame.draw.aalines(surface, outline, True, pts)


def draw_trail(surface, positions, state):
    """Fading small dots from oldest to newest."""
    n = len(positions)
    if n < 2:
        return
    base = _COLOUR_COASTED if state == "COASTED" else (180, 180, 180)
    for i, (x, y) in enumerate(positions):
        alpha = int(15 + 40 * i / n)
        r = 2
        dot = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(dot, (*base, alpha), (r + 1, r + 1), r)
        surface.blit(dot, (int(x) - r - 1, int(y) - r - 1))


def _rotated_car(cx, cy, w, h, heading_deg):
    rad = math.radians(heading_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    pts = []
    for tx, ty in _CAR_TEMPLATE:
        lx = tx * w
        ly = ty * h
        rx = lx * cos_a - ly * sin_a
        ry = lx * sin_a + ly * cos_a
        pts.append((cx + rx, cy + ry))
    return pts
