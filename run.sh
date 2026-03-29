#!/bin/bash
# Launch open-PROX under labwc Wayland compositor.
# Wayland avoids the DRM/Hailo PCIe DMA conflict that KMSDRM causes.

DIR="$(cd "$(dirname "$0")" && pwd)"

cat > /tmp/prox_launch.sh << INNER
#!/bin/bash
export SDL_VIDEODRIVER=wayland
export PYTHONUNBUFFERED=1
sleep 1
exec $DIR/../prox-env-312/bin/python3 -u -B $DIR/main.py
INNER
chmod +x /tmp/prox_launch.sh

mkdir -p /tmp/prox-runtime
exec sudo XDG_RUNTIME_DIR=/tmp/prox-runtime WLR_BACKENDS=drm labwc -s /tmp/prox_launch.sh
