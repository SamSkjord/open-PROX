import math
from collections import deque

import pygame

import config
from display.vehicle_icon import draw_vehicle_icon
from display.coverage_cone import draw_coverage_cones
from display.contact_blip import draw_contact, draw_trail
from display.proximity_glow import draw_proximity_glow


class Renderer:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(
            (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT)
        )
        pygame.display.set_caption("open-PROX")
        self.clock = pygame.time.Clock()
        self.font_hud = pygame.font.SysFont("consolas", 14)

        self.cx = config.DISPLAY_WIDTH // 2
        self.cy = config.DISPLAY_HEIGHT // 2
        self.pixels_per_metre = self.cx / config.DISPLAY_RANGE_M

        self.trails = {}
        self._crosshairs = self._build_crosshairs()

    def polar_to_screen(self, angle_deg, range_m):
        angle_rad = math.radians(angle_deg)
        px = range_m * self.pixels_per_metre
        return (self.cx + px * math.sin(angle_rad),
                self.cy - px * math.cos(angle_rad))

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False
        return True

    def render(self, contacts):
        self.screen.fill(config.DISPLAY_BG_COLOUR)

        self._draw_range_rings()
        self.screen.blit(self._crosshairs, (0, 0))

        if config.COVERAGE_CONES_ENABLED:
            draw_coverage_cones(self.screen, self.cx, self.cy,
                                self.pixels_per_metre, config.LENS_FOV_DEG,
                                config.DISPLAY_RANGE_M)

        # Compute screen positions once
        screen_positions = [
            self.polar_to_screen(c["angle_deg"], c["range_m"])
            for c in contacts
        ]

        draw_proximity_glow(self.screen, screen_positions, contacts,
                            self.cx, self.cy,
                            config.GLOW_COLOUR, config.GLOW_MAX_ALPHA,
                            config.GLOW_RANGE_M, config.GLOW_RADIUS_PX,
                            self.pixels_per_metre)

        self._update_trails(contacts)
        self._draw_trails(contacts)

        for pos, c in zip(screen_positions, contacts):
            draw_contact(self.screen, pos, c,
                         config.BLIP_WIDTH_PX, config.BLIP_LENGTH_PX)

        draw_vehicle_icon(self.screen, self.cx, self.cy)
        self._draw_hud(contacts)

        pygame.display.flip()
        self.clock.tick(config.DISPLAY_FPS)

    def _draw_range_rings(self):
        interval = config.RANGE_RING_INTERVAL_M
        distance = interval
        while distance <= config.DISPLAY_RANGE_M:
            radius = int(distance * self.pixels_per_metre)
            pygame.draw.circle(self.screen, config.RANGE_RING_COLOUR,
                               (self.cx, self.cy), radius, 1)
            distance += interval

    def _update_trails(self, contacts):
        seen_ids = set()
        for c in contacts:
            tid = c["id"]
            seen_ids.add(tid)
            pos = self.polar_to_screen(c["angle_deg"], c["range_m"])
            if tid not in self.trails:
                self.trails[tid] = deque(maxlen=config.TRAIL_FRAMES)
            self.trails[tid].append(pos)

        for tid in list(self.trails):
            if tid not in seen_ids:
                if self.trails[tid]:
                    self.trails[tid].popleft()
                if not self.trails[tid]:
                    del self.trails[tid]

    def _draw_trails(self, contacts):
        contact_map = {c["id"]: c for c in contacts}
        for tid, positions in self.trails.items():
            c = contact_map.get(tid)
            state = c["state"] if c else "COASTED"
            trail_pts = list(positions)[:-1] if len(positions) > 1 else []
            draw_trail(self.screen, trail_pts, state)

    def _draw_hud(self, contacts):
        active = sum(1 for c in contacts if c["state"] == "ACTIVE")
        hud_colour = (90, 90, 90)

        count = self.font_hud.render(f"{active}", True, hud_colour)
        self.screen.blit(count, (10, 10))

        fps = self.clock.get_fps()
        fps_text = self.font_hud.render(f"{fps:.0f}", True, hud_colour)
        self.screen.blit(fps_text,
                         (config.DISPLAY_WIDTH - fps_text.get_width() - 10, 10))

    def _build_crosshairs(self):
        """Pre-render crosshairs that are bright at centre and fade to transparent."""
        w, h = config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        colour = (70, 70, 70)
        half_w, half_h = w // 2, h // 2
        segments = 80

        # Horizontal line (left half then right half)
        for i in range(segments):
            t = i / segments  # 0 at centre, 1 at edge
            alpha = int(100 * max(0.0, 1.0 - t * t))
            seg_len = half_w // segments
            x_start = half_w + i * seg_len
            # Right half
            pygame.draw.line(surf, (*colour, alpha),
                             (x_start, half_h), (x_start + seg_len, half_h), 2)
            # Left half (mirror)
            pygame.draw.line(surf, (*colour, alpha),
                             (half_w - i * seg_len, half_h),
                             (half_w - (i + 1) * seg_len, half_h), 2)

        # Vertical line (top half then bottom half)
        for i in range(segments):
            t = i / segments
            alpha = int(100 * max(0.0, 1.0 - t * t))
            seg_len = half_h // segments
            y_start = half_h + i * seg_len
            # Bottom half
            pygame.draw.line(surf, (*colour, alpha),
                             (half_w, y_start), (half_w, y_start + seg_len), 2)
            # Top half (mirror)
            pygame.draw.line(surf, (*colour, alpha),
                             (half_w, half_h - i * seg_len),
                             (half_w, half_h - (i + 1) * seg_len), 2)

        return surf

    def shutdown(self):
        pygame.quit()
