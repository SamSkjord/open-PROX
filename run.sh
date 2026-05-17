#!/bin/bash
# Launch open-PROX under cage Wayland kiosk compositor.
# cage runs one fullscreen app, no decorations, no persistent cursor.

DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p /tmp/prox-runtime
export XDG_RUNTIME_DIR=/tmp/prox-runtime
export WLR_BACKENDS=drm
export SDL_VIDEODRIVER=wayland
export PYTHONUNBUFFERED=1

exec sudo -E cage -s -- "$DIR/../prox-env-312/bin/python3" -u -B "$DIR/main.py"
