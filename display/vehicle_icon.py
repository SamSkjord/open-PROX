import pygame


_COLOUR = (0, 180, 0)
_HALF_W = 9
_HALF_H = 16


def draw_vehicle_icon(surface, cx, cy):
    """Solid green rectangle at centre, pointing up."""
    rect = pygame.Rect(cx - _HALF_W, cy - _HALF_H, _HALF_W * 2, _HALF_H * 2)
    pygame.draw.rect(surface, _COLOUR, rect)
