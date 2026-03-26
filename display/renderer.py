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
VIEW_CAM_RIGHT = 1
VIEW_CAM_LEFT = 2


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
        self._touch_down_time = 0
        self._touch_switched = False
        self._TOUCH_HOLD_S = 2.0
        self._camera_frames = {}  # side -> frame_rgb
        self.detect_status = "INIT"  # INIT, OK, ERROR, RECOVERING

    def set_camera_frame(self, frame_rgb, side="RIGHT"):
        """Store the latest camera frame for camera view."""
        self._camera_frames[side] = frame_rgb
        # Keep legacy single-frame for _render_camera
        self._camera_frame = frame_rgb

    def handle_events(self):
        now = time.monotonic()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False
            if event.type in (pygame.FINGERDOWN, pygame.MOUSEBUTTONDOWN):
                self._touch_down_time = now
                self._touch_switched = False
            if event.type in (pygame.FINGERUP, pygame.MOUSEBUTTONUP):
                # Quick tap (released before hold threshold) = back to prox
                if not self._touch_switched and self.view != VIEW_PROX:
                    self.view = VIEW_PROX
                self._touch_down_time = 0
                self._touch_switched = False

        # Hold for 2s cycles through camera views
        if self._touch_down_time > 0 and not self._touch_switched:
            if (now - self._touch_down_time) >= self._TOUCH_HOLD_S:
                self._touch_switched = True
                if self.view == VIEW_PROX:
                    self.view = VIEW_CAM_RIGHT
                elif self.view == VIEW_CAM_RIGHT:
                    self.view = VIEW_CAM_LEFT
                else:
                    self.view = VIEW_CAM_RIGHT

        return True

    def polar_to_screen(self, angle_deg, range_m):
        angle_rad = math.radians(angle_deg)
        px = range_m * self.pixels_per_metre
        return (self.cx + px * math.sin(angle_rad),
                self.cy - px * math.cos(angle_rad))

    def render(self, contacts):
        if self.view in (VIEW_CAM_RIGHT, VIEW_CAM_LEFT):
            side = "RIGHT" if self.view == VIEW_CAM_RIGHT else "LEFT"
            self._render_camera(contacts, side)
        else:
            self._render_prox(contacts)

        pygame.display.flip()
        self.clock.tick(config.DISPLAY_FPS)

    def _render_prox(self, contacts):
        self.screen.fill(config.DISPLAY_BG_COLOUR)
        self._draw_range_rings()
        self.screen.blit(self._crosshairs, (0, 0))

        screen_positions = [
            self.polar_to_screen(c["angle_deg"], c["range_m"])
            for c in contacts
        ]

        self._update_trails(contacts)
        self._draw_trails(contacts)

        for pos, c in zip(screen_positions, contacts):
            draw_contact(self.screen, pos, c,
                         config.BLIP_WIDTH_PX, config.BLIP_LENGTH_PX)

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

    def _render_camera(self, contacts, side="RIGHT"):
        """Render the camera feed with detection boxes."""
        self.screen.fill((0, 0, 0))

        frame = self._camera_frames.get(side)
        if frame is not None:
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
        side_text = self.font_hud.render(side, True, hud_colour)
        self.screen.blit(side_text, (10, 10))
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

        # Detection status indicator
        if self.detect_status != "OK":
            status_colours = {
                "INIT": (100, 100, 100),
                "ERROR": (200, 50, 50),
                "RECOVERING": (200, 150, 0),
            }
            colour = status_colours.get(self.detect_status, (200, 50, 50))
            label = {"INIT": "HAILO INIT", "ERROR": "HAILO DOWN",
                     "RECOVERING": "HAILO RESET"}.get(self.detect_status, "HAILO ?")
            txt = self.font_hud.render(label, True, colour)
            self.screen.blit(txt, (config.DISPLAY_WIDTH // 2 - txt.get_width() // 2,
                                   config.DISPLAY_HEIGHT - 24))

    def _build_crosshairs(self):
        """Pre-render crosshairs as opaque lines on the background colour.

        Avoids SRCALPHA surfaces which cause GPU DMA conflicts with the
        Hailo PCIe VDMA on Pi 5 KMSDRM.
        """
        w, h = config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT
        surf = pygame.Surface((w, h))
        surf.fill(config.DISPLAY_BG_COLOUR)
        surf.set_colorkey(config.DISPLAY_BG_COLOUR)
        half_w, half_h = w // 2, h // 2

        # Draw crosshair lines with varying brightness (no alpha)
        segments = 40
        for i in range(segments):
            t = i / segments
            brightness = int(70 * max(0.0, 1.0 - t * t))
            colour = (brightness, brightness, brightness)
            if brightness < 10:
                continue
            seg_len = half_w // segments
            x_start = half_w + i * seg_len
            pygame.draw.line(surf, colour,
                             (x_start, half_h), (x_start + seg_len, half_h), 2)
            pygame.draw.line(surf, colour,
                             (half_w - i * seg_len, half_h),
                             (half_w - (i + 1) * seg_len, half_h), 2)

        for i in range(segments):
            t = i / segments
            brightness = int(70 * max(0.0, 1.0 - t * t))
            colour = (brightness, brightness, brightness)
            if brightness < 10:
                continue
            seg_len = half_h // segments
            y_start = half_h + i * seg_len
            pygame.draw.line(surf, colour,
                             (half_w, y_start), (half_w, y_start + seg_len), 2)
            pygame.draw.line(surf, colour,
                             (half_w, half_h - i * seg_len),
                             (half_w, half_h - (i + 1) * seg_len), 2)

        return surf

    def shutdown(self):
        pygame.quit()
