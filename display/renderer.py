import math
import time
from collections import deque

import pygame

import config
from display.vehicle_icon import draw_vehicle_icon
from display.coverage_cone import draw_coverage_cones
from display.contact_blip import draw_contact, draw_trail
from display.proximity_glow import draw_proximity_glow

VIEW_PROX = 0
VIEW_CAMERA = 1


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

        self.view = VIEW_PROX
        self._camera_frame = None
        self._last_tap_time = 0

    def set_camera_frame(self, frame_rgb):
        """Store the latest camera frame for camera view."""
        self._camera_frame = frame_rgb

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False
            # Touch view switching disabled - touchscreen generates noise
            # TODO: investigate Goodix driver config or use GPIO button instead
        return True

    def polar_to_screen(self, angle_deg, range_m):
        angle_rad = math.radians(angle_deg)
        px = range_m * self.pixels_per_metre
        return (self.cx + px * math.sin(angle_rad),
                self.cy - px * math.cos(angle_rad))

    def render(self, contacts):
        if self.view == VIEW_CAMERA:
            self._render_camera(contacts)
        else:
            self._render_prox(contacts)

        pygame.display.flip()
        self.clock.tick(config.DISPLAY_FPS)

    def _render_prox(self, contacts):
        self.screen.fill(config.DISPLAY_BG_COLOUR)

        self._draw_range_rings()
        self.screen.blit(self._crosshairs, (0, 0))

        if config.COVERAGE_CONES_ENABLED:
            draw_coverage_cones(self.screen, self.cx, self.cy,
                                self.pixels_per_metre, config.LENS_FOV_DEG,
                                config.DISPLAY_RANGE_M)

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

        # Closing speed labels next to blips
        for pos, c in zip(screen_positions, contacts):
            closing = c.get("closing_kph", 0)
            if c["state"] == "ACTIVE" and abs(closing) > 1.0:
                label = f"{closing:+.0f}"
                colour = (255, 160, 0) if closing > 0 else (100, 200, 100)
                txt = self.font_hud.render(label, True, colour)
                sx, sy = int(pos[0]), int(pos[1])
                self.screen.blit(txt, (sx + config.BLIP_WIDTH_PX, sy - 7))

        draw_vehicle_icon(self.screen, self.cx, self.cy)
        self._draw_hud(contacts)

    def _render_camera(self, contacts):
        """Render the camera feed with detection boxes."""
        self.screen.fill((0, 0, 0))

        if self._camera_frame is not None:
            frame = self._camera_frame
            fh, fw = frame.shape[:2]
            # Letterbox into display
            scale = config.DISPLAY_WIDTH / fw
            disp_h = int(fh * scale)
            y_off = (config.DISPLAY_HEIGHT - disp_h) // 2

            import cv2
            resized = cv2.resize(frame, (config.DISPLAY_WIDTH, disp_h))
            surf = pygame.surfarray.make_surface(resized.swapaxes(0, 1))
            self.screen.blit(surf, (0, y_off))

            # Draw detection boxes
            for c in contacts:
                bbox = c.get("bbox", (0, 0, 0, 0))
                if bbox == (0, 0, 0, 0):
                    continue
                x1 = int(bbox[0] * scale)
                y1 = int(bbox[1] * scale) + y_off
                x2 = int(bbox[2] * scale)
                y2 = int(bbox[3] * scale) + y_off
                colour = (255, 100, 0)
                pygame.draw.rect(self.screen, colour,
                                 (x1, y1, x2 - x1, y2 - y1), 2)
                # Range label
                rm = c.get("range_m", 0)
                if rm > 0:
                    label = self.font_hud.render(f"{rm:.1f}m", True, colour)
                    self.screen.blit(label, (x1, max(0, y1 - 16)))

        # HUD overlay
        active = sum(1 for c in contacts if c.get("state") == "ACTIVE")
        hud_colour = (200, 200, 200)
        count = self.font_hud.render(f"{active}", True, hud_colour)
        self.screen.blit(count, (10, 10))
        fps = self.clock.get_fps()
        fps_text = self.font_hud.render(f"{fps:.0f}", True, hud_colour)
        self.screen.blit(fps_text,
                         (config.DISPLAY_WIDTH - fps_text.get_width() - 10, 10))

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

        for i in range(segments):
            t = i / segments
            alpha = int(100 * max(0.0, 1.0 - t * t))
            seg_len = half_w // segments
            x_start = half_w + i * seg_len
            pygame.draw.line(surf, (*colour, alpha),
                             (x_start, half_h), (x_start + seg_len, half_h), 2)
            pygame.draw.line(surf, (*colour, alpha),
                             (half_w - i * seg_len, half_h),
                             (half_w - (i + 1) * seg_len, half_h), 2)

        for i in range(segments):
            t = i / segments
            alpha = int(100 * max(0.0, 1.0 - t * t))
            seg_len = half_h // segments
            y_start = half_h + i * seg_len
            pygame.draw.line(surf, (*colour, alpha),
                             (half_w, y_start), (half_w, y_start + seg_len), 2)
            pygame.draw.line(surf, (*colour, alpha),
                             (half_w, half_h - i * seg_len),
                             (half_w, half_h - (i + 1) * seg_len), 2)

        return surf

    def shutdown(self):
        pygame.quit()
