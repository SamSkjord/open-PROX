import pygame


_COLOUR_BLIP = (230, 230, 230)
_COLOUR_COASTED = (70, 70, 70)


def draw_contact(surface, screen_pos, contact, blip_w, blip_h):
    """Draw a solid rectangle blip, always upright."""
    coasted = contact["state"] == "COASTED"
    colour = _COLOUR_COASTED if coasted else _COLOUR_BLIP
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
        alpha = int(15 + 40 * i / n)
        r = 2
        dot = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(dot, (*base, alpha), (r + 1, r + 1), r)
        surface.blit(dot, (int(x) - r - 1, int(y) - r - 1))
