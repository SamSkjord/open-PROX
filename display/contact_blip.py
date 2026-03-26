import pygame


# Closing speed colour thresholds (kph)
_CLOSING_FAST = 10.0    # red
_CLOSING_SLOW = 2.0     # orange
# Below _CLOSING_SLOW or separating = white/green

_COLOUR_COASTED = (70, 70, 70)
_COLOUR_SEPARATING = (100, 200, 100)   # soft green - moving away
_COLOUR_NEUTRAL = (230, 230, 230)      # white - stationary/slow
_COLOUR_CLOSING = (255, 160, 0)        # orange - closing
_COLOUR_CLOSING_FAST = (255, 50, 50)   # red - fast closing


def _blip_colour(contact):
    """Pick blip colour based on closing speed."""
    if contact["state"] == "COASTED":
        return _COLOUR_COASTED
    closing = contact.get("closing_kph", 0)
    if closing >= _CLOSING_FAST:
        return _COLOUR_CLOSING_FAST
    if closing >= _CLOSING_SLOW:
        return _COLOUR_CLOSING
    if closing < -1.0:
        return _COLOUR_SEPARATING
    return _COLOUR_NEUTRAL


def draw_contact(surface, screen_pos, contact, blip_w, blip_h):
    """Draw a solid rectangle blip coloured by closing speed."""
    colour = _blip_colour(contact)
    sx, sy = int(screen_pos[0]), int(screen_pos[1])
    rect = pygame.Rect(sx - blip_w // 2, sy - blip_h // 2, blip_w, blip_h)
    pygame.draw.rect(surface, colour, rect)


def draw_trail(surface, positions, state):
    """Fading small dots from oldest to newest."""
    n = len(positions)
    if n < 2:
        return
    base = _COLOUR_COASTED if state == "COASTED" else (180, 180, 180)
    for i, (x, y) in enumerate(positions):
        fade = 0.15 + 0.55 * (i / n)
        r = 2
        c = (int(base[0] * fade), int(base[1] * fade), int(base[2] * fade))
        pygame.draw.circle(surface, c, (int(x), int(y)), r)
