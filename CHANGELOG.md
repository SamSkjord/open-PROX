# Changelog

## Phase 0 — Display Mock (2026-03-19)

Initial implementation of the ACC-style proximity radar display with synthetic targets. Runs on desktop, no hardware required.

### Added

- **Display renderer** (`display/renderer.py`) — Pygame 720x720 at 60fps, layer compositing, pre-rendered fading crosshairs, trail history per track ID
- **Car-shaped blips** (`display/contact_blip.py`) — White rotated polygons oriented by velocity direction, grey when coasted
- **Proximity glow** (`display/proximity_glow.py`) — Orange radial glow around contacts within 2m, intensity scales with proximity
- **Coverage cones** (`display/coverage_cone.py`) — Semi-transparent FOV arcs for left/right cameras (off by default)
- **Host vehicle icon** (`display/vehicle_icon.py`) — Light-outlined top-down car silhouette at centre
- **Synthetic targets** (`tools/synthetic_targets.py`) — Five contact patterns: left overtaker, right overtaker, closer from behind, stationary alongside, intermittent
- **Configuration** (`config.py`) — Display, blip geometry, proximity glow, range rings, coverage cones, tracking thresholds
- **Entry point** (`main.py`) — Main loop with event handling

### Display Design

- ACC proximity radar aesthetic: 5m range, white blips, orange danger glow, fading crosshairs, subtle 1m range rings
- Coordinate system: polar (angle_deg, range_m) with 0° ahead, centre = host vehicle
- Track data structure established: id, side, angle, range, velocity, closing speed, state, occluded flag, orientation
