import math
import time


class SyntheticTargetGenerator:
    """Generates fake track dicts for display development."""

    def __init__(self):
        self._start = time.monotonic()

    def generate(self):
        t = time.monotonic() - self._start
        contacts = []

        contacts.append(self._overtaker_left(t))
        contacts.append(self._overtaker_right(t))
        contacts.append(self._closer_from_behind(t))
        contacts.append(self._stationary_nearby(t))

        intermittent = self._intermittent(t)
        if intermittent is not None:
            contacts.append(intermittent)

        contacts.append(self._swerver_right(t))

        return contacts

    def _overtaker_left(self, t):
        """Car overtaking on the left, 8s loop."""
        progress = (t % 8.0) / 8.0
        x = -2.0
        y = -4.0 + 8.0 * progress  # -4 to +4
        vx = 0.0
        vy = 1.0
        return self._make_track(1, x, y, vx, vy, t)

    def _overtaker_right(self, t):
        """Car overtaking on the right, 10s loop, offset start."""
        progress = ((t + 3.0) % 10.0) / 10.0
        x = 2.2
        y = -4.5 + 9.0 * progress
        vx = 0.0
        vy = 0.9
        return self._make_track(2, x, y, vx, vy, t)

    def _closer_from_behind(self, t):
        """Approaches from behind, holds at ~2m."""
        raw_y = -4.5 + 0.5 * t
        y = min(raw_y, -2.0)
        x = 0.3
        vy = 0.5 if raw_y < -2.0 else 0.0
        vx = 0.0
        return self._make_track(3, x, y, vx, vy, t)

    def _stationary_nearby(self, t):
        """Fixed position, alongside right."""
        return self._make_track(4, 2.5, -0.5, 0.0, 0.0, t)

    def _intermittent(self, t):
        """Appears for 3s, disappears for 2s."""
        cycle = t % 5.0
        if cycle > 3.0:
            return None
        x = -2.5
        y = 1.5
        return self._make_track(5, x, y, 0.0, 0.1, t,
                                state="COASTED" if cycle > 2.5 else "ACTIVE")

    def _swerver_right(self, t):
        """Starts at x=+3m behind, swerves to x=+1m as it comes alongside. 10s loop."""
        progress = (t % 10.0) / 10.0
        y = -4.5 + 9.0 * progress  # -4.5 to +4.5
        # Swerve: x=3 at rear, tightens to x=1 at y=0 (alongside), back to 3 ahead
        closeness = 1.0 - abs(y) / 4.5  # 0 at ends, 1 at alongside
        x = 3.0 - 2.0 * closeness       # 3m → 1m → 3m
        vx = -2.0 * closeness if y < 0 else 2.0 * closeness
        vy = 0.9
        return self._make_track(6, x, y, vx, vy, t)

    def _make_track(self, track_id, x, y, vx, vy, t, state="ACTIVE"):
        """Build a track dict from Cartesian position relative to host.

        x: positive = right, y: positive = ahead
        """
        range_m = math.hypot(x, y)
        angle_deg = math.degrees(math.atan2(x, y)) % 360

        if range_m > 0.1:
            closing_ms = -(x * vx + y * vy) / range_m
        else:
            closing_ms = 0.0
        closing_kph = closing_ms * 3.6

        side = "LEFT" if x < -1.0 else ("RIGHT" if x > 1.0 else "BOTH")

        return {
            "id": track_id,
            "side": side,
            "angle_deg": angle_deg,
            "range_m": range_m,
            "range_method": "synthetic",
            "range_confidence": 1.0,
            "velocity": (vx, vy),
            "closing_kph": closing_kph,
            "confidence": 1.0,
            "age_frames": int(t * 30),
            "last_seen_ns": int(t * 1e9),
            "state": state,
            "occluded": False,
            "sources": {"synthetic"},
            "bbox": (0, 0, 0, 0),
            "orientation": "SIDE" if abs(x) > abs(y) else "HEAD_ON",
        }
