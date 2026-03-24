"""SORT tracker with Kalman filters for persistent contact tracking.

Assigns stable IDs across frames, estimates velocity, manages coasting
(contacts persist briefly when detection drops), and handles occlusion.

Uses a simple linear Kalman filter in polar-ish coordinates:
  state = [angle_deg, range_m, d_angle, d_range]

Hungarian algorithm (scipy linear_sum_assignment or fallback) for
detection-to-track association.
"""

import math
import time

import numpy as np
import config


# -- Kalman filter for a single track --

class TrackKF:
    """4-state Kalman filter: [angle_deg, range_m, v_angle, v_range]."""

    def __init__(self, angle_deg, range_m, dt=1 / 30):
        self.dt = dt
        # State: [angle, range, d_angle, d_range]
        self.x = np.array([angle_deg, range_m, 0.0, 0.0], dtype=np.float64)
        # State transition
        self.F = np.eye(4)
        self.F[0, 2] = dt
        self.F[1, 3] = dt
        # Measurement matrix (we observe angle and range)
        self.H = np.zeros((2, 4))
        self.H[0, 0] = 1.0
        self.H[1, 1] = 1.0
        # Covariance
        self.P = np.diag([10.0, 1.0, 100.0, 10.0])
        # Process noise
        q_angle = 5.0   # degrees per step variance
        q_range = 0.5   # metres per step variance
        self.Q = np.diag([q_angle, q_range, q_angle * 2, q_range * 2])
        # Measurement noise
        self.R = np.diag([3.0, 0.3])

    def predict(self):
        self.x = self.F @ self.x
        self.x[0] = self.x[0] % 360
        self.P = self.F @ self.P @ self.F.T + self.Q

    def update(self, angle_deg, range_m):
        z = np.array([angle_deg, range_m])
        y = z - self.H @ self.x
        # Handle angle wrapping: shortest path around the circle
        if y[0] > 180:
            y[0] -= 360
        elif y[0] < -180:
            y[0] += 360
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.x[0] = self.x[0] % 360
        self.P = (np.eye(4) - K @ self.H) @ self.P

    @property
    def angle_deg(self):
        return self.x[0] % 360

    @property
    def range_m(self):
        return max(0.1, self.x[1])

    @property
    def v_angle(self):
        return self.x[2]

    @property
    def v_range(self):
        return self.x[3]


# -- Single track --

class Track:
    _next_id = 1

    def __init__(self, contact):
        self.id = Track._next_id
        Track._next_id += 1

        self.kf = TrackKF(contact["angle_deg"], contact["range_m"])
        self.side = contact["side"]
        self.bbox = contact["bbox"]
        self.confidence = contact["confidence"]
        self.range_method = contact["range_method"]
        self.orientation = contact.get("orientation", "SIDE")
        self.sources = contact.get("sources", {"camera"})

        self.age_frames = 0
        self.hits = 0
        self.time_since_update = 0
        self.last_seen_ns = contact["last_seen_ns"]
        self.occluded = False

    def predict(self):
        self.kf.predict()
        self.time_since_update += 1
        self.age_frames += 1

    def update(self, contact):
        self.kf.update(contact["angle_deg"], contact["range_m"])
        self.side = contact["side"]
        self.bbox = contact["bbox"]
        self.confidence = contact["confidence"]
        self.range_method = contact["range_method"]
        self.orientation = contact.get("orientation", self.orientation)
        self.sources = contact.get("sources", self.sources)
        self.last_seen_ns = contact["last_seen_ns"]
        self.time_since_update = 0
        self.hits += 1
        self.occluded = False

    @property
    def state(self):
        if self.time_since_update == 0:
            return "ACTIVE"
        return "COASTED"

    @property
    def coast_limit_ms(self):
        if self.occluded:
            return config.OCCLUDED_COAST_MS
        return config.TRACK_COAST_MS

    @property
    def is_expired(self):
        elapsed_ms = self.time_since_update * (1000 / config.CAM_FPS)
        if elapsed_ms > config.TRACK_DROP_MS:
            return True
        if self.time_since_update > 0 and elapsed_ms > self.coast_limit_ms:
            return True
        return False

    def to_contact(self):
        """Export as a track-compatible contact dict for the renderer."""
        # Velocity in m/s: convert angular rate to approximate cartesian
        angle_rad = math.radians(self.kf.angle_deg)
        r = self.kf.range_m
        # d_range is radial velocity, d_angle is tangential
        vr = self.kf.v_range
        va = math.radians(self.kf.v_angle) * r  # tangential m/s

        # Project to (vx, vy) in host frame
        vx = vr * math.sin(angle_rad) + va * math.cos(angle_rad)
        vy = vr * math.cos(angle_rad) - va * math.sin(angle_rad)

        # Closing speed: v_range is in m/s, negative = approaching
        closing_kph = -self.kf.v_range * 3.6

        return {
            "id": self.id,
            "side": self.side,
            "angle_deg": self.kf.angle_deg,
            "range_m": self.kf.range_m,
            "range_method": self.range_method,
            "range_confidence": self.confidence,
            "velocity": (vx, vy),
            "closing_kph": closing_kph,
            "confidence": self.confidence,
            "age_frames": self.age_frames,
            "last_seen_ns": self.last_seen_ns,
            "state": self.state,
            "occluded": self.occluded,
            "sources": self.sources,
            "bbox": self.bbox,
            "orientation": self.orientation,
        }


# -- Association --

def _angle_distance(a1, a2):
    """Angular distance in degrees, handling wrap."""
    d = abs(a1 - a2) % 360
    return min(d, 360 - d)


def _cost_matrix(tracks, detections):
    """Build cost matrix for Hungarian assignment. Cost = weighted distance."""
    n_tracks = len(tracks)
    n_dets = len(detections)
    cost = np.full((n_tracks, n_dets), 1e6)

    for i, trk in enumerate(tracks):
        for j, det in enumerate(detections):
            angle_dist = _angle_distance(trk.kf.angle_deg, det["angle_deg"])
            range_dist = abs(trk.kf.range_m - det["range_m"])
            # Weighted sum
            cost[i, j] = angle_dist + range_dist * 20.0
    return cost


def _hungarian(cost):
    """Solve assignment. Returns list of (track_idx, det_idx) pairs."""
    try:
        from scipy.optimize import linear_sum_assignment
        row_ind, col_ind = linear_sum_assignment(cost)
        return list(zip(row_ind.tolist(), col_ind.tolist()))
    except ImportError:
        # Greedy fallback
        assignments = []
        used_rows = set()
        used_cols = set()
        flat = []
        for i in range(cost.shape[0]):
            for j in range(cost.shape[1]):
                flat.append((cost[i, j], i, j))
        flat.sort()
        for c, i, j in flat:
            if i not in used_rows and j not in used_cols:
                assignments.append((i, j))
                used_rows.add(i)
                used_cols.add(j)
        return assignments


# -- SORT tracker --

class SortTracker:
    """Simple Online and Realtime Tracking (SORT) for proximity contacts."""

    GATE_THRESHOLD = 60.0  # max cost for valid association

    def __init__(self):
        self.tracks = []

    def update(self, detections):
        """Process a frame's detections. Returns list of contact dicts.

        Args:
            detections: list of contact dicts from range/monocular.py
        """
        # Predict all existing tracks
        for trk in self.tracks:
            trk.predict()

        if not detections and not self.tracks:
            return []

        # Associate detections to tracks
        matched, unmatched_dets, unmatched_trks = self._associate(detections)

        # Update matched tracks
        for trk_idx, det_idx in matched:
            self.tracks[trk_idx].update(detections[det_idx])

        # Create new tracks for unmatched detections
        for det_idx in unmatched_dets:
            self.tracks.append(Track(detections[det_idx]))

        # Mark occlusion: if a track drops out but has an adjacent active track
        self._check_occlusion()

        # Remove expired tracks
        self.tracks = [t for t in self.tracks if not t.is_expired]

        # Export active + coasted tracks
        return [t.to_contact() for t in self.tracks if t.state in ("ACTIVE", "COASTED")]

    def _associate(self, detections):
        if not self.tracks or not detections:
            unmatched_dets = list(range(len(detections)))
            unmatched_trks = list(range(len(self.tracks)))
            return [], unmatched_dets, unmatched_trks

        cost = _cost_matrix(self.tracks, detections)
        assignments = _hungarian(cost)

        matched = []
        unmatched_dets = set(range(len(detections)))
        unmatched_trks = set(range(len(self.tracks)))

        for trk_idx, det_idx in assignments:
            if cost[trk_idx, det_idx] < self.GATE_THRESHOLD:
                matched.append((trk_idx, det_idx))
                unmatched_dets.discard(det_idx)
                unmatched_trks.discard(trk_idx)

        return matched, list(unmatched_dets), list(unmatched_trks)

    def _check_occlusion(self):
        """Mark tracks as occluded if they drop out near an active track."""
        active_angles = []
        for t in self.tracks:
            if t.state == "ACTIVE":
                active_angles.append(t.kf.angle_deg)

        for t in self.tracks:
            if t.state == "COASTED" and not t.occluded:
                for aa in active_angles:
                    if _angle_distance(t.kf.angle_deg, aa) < 15.0:
                        t.occluded = True
                        break
