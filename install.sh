#!/bin/bash
# open-PROX installer for Raspberry Pi 5 + Hailo AI HAT+ 2
#
# Run as: sudo bash install.sh
#
# Prerequisites: Raspbian Lite (Trixie), Waveshare 4" DSI LCD (C) connected,
#                Hailo AI HAT+ 2 seated in M.2 slot.

set -e

if [ "$EUID" -ne 0 ]; then
    echo "Run as root: sudo bash install.sh"
    exit 1
fi

PROX_USER="${SUDO_USER:-pi}"
PROX_HOME=$(eval echo "~$PROX_USER")
VENV="$PROX_HOME/prox-env"

echo "=== open-PROX installer ==="
echo "User: $PROX_USER"
echo "Home: $PROX_HOME"
echo "Venv: $VENV"
echo

# ── Pin kernel ──────────────────────────────────────────────────────
# Hailo driver is kernel-version specific. Prevent apt from upgrading.
echo ">> Pinning kernel..."
apt-mark hold linux-image-rpi-2712 2>/dev/null || true
CURRENT_KERNEL=$(dpkg -l | grep linux-image.*rpi-2712 | grep "^ii" | head -1 | awk '{print $2}')
if [ -n "$CURRENT_KERNEL" ]; then
    apt-mark hold "$CURRENT_KERNEL" 2>/dev/null || true
    echo "   Held: $CURRENT_KERNEL"
fi

# ── System packages ─────────────────────────────────────────────────
echo ">> Installing system packages..."
apt-get update -qq
apt-get install -y -qq \
    python3-dev python3-venv build-essential \
    libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
    v4l-utils

# ── Hailo AI HAT+ 2 ────────────────────────────────────────────────
echo ">> Installing Hailo packages..."
apt-get install -y -qq hailo-h10-all

# Blacklist the Hailo-8 driver (conflicts with Hailo-10H)
echo "blacklist hailo_pci" > /etc/modprobe.d/hailo-blacklist.conf

# Auto-load Hailo-10H driver on boot
echo "hailo1x_pci" > /etc/modules-load.d/hailo.conf

# ── Python venv ─────────────────────────────────────────────────────
echo ">> Setting up Python venv..."
if [ ! -d "$VENV" ]; then
    sudo -u "$PROX_USER" python3 -m venv "$VENV"
fi

# Build pygame from source for KMSDRM support
echo ">> Building pygame from source (KMSDRM)..."
sudo -u "$PROX_USER" "$VENV/bin/pip" install --no-binary pygame pygame

# numpy for hailo_platform
sudo -u "$PROX_USER" "$VENV/bin/pip" install numpy

# ── Symlink system packages into venv ───────────────────────────────
echo ">> Linking system packages into venv..."
SITE=$("$VENV/bin/python3" -c 'import site; print(site.getsitepackages()[0])')

# hailo_platform
ln -sf /usr/lib/python3/dist-packages/hailo_platform "$SITE/hailo_platform" 2>/dev/null || true

# OpenCV
CV2_SO=$(python3 -c 'import cv2; print(cv2.__file__)' 2>/dev/null || true)
if [ -n "$CV2_SO" ]; then
    ln -sf "$CV2_SO" "$SITE/" 2>/dev/null || true
fi

# ── USB camera udev rule ────────────────────────────────────────────
echo ">> Setting up udev rules..."
cat > /etc/udev/rules.d/99-open-prox-cameras.rules << 'UDEV'
# Allow video group access to USB cameras
SUBSYSTEM=="video4linux", ATTR{name}=="USB Camera*", GROUP="video", MODE="0660"
UDEV
usermod -aG video "$PROX_USER" 2>/dev/null || true

# ── Verify ──────────────────────────────────────────────────────────
echo
echo "=== Verification ==="

# Kernel
echo -n "Kernel: "
uname -r

# Hailo
echo -n "Hailo: "
if [ -e /dev/hailo0 ]; then
    hailortcli fw-control identify 2>/dev/null | grep "Firmware Version" || echo "/dev/hailo0 present (driver loaded)"
else
    modprobe hailo1x_pci 2>/dev/null
    sleep 3
    if [ -e /dev/hailo0 ]; then
        hailortcli fw-control identify 2>/dev/null | grep "Firmware Version" || echo "loaded on demand"
    else
        echo "NOT DETECTED - check M.2 seating, reboot may be required"
    fi
fi

# Pygame KMSDRM
echo -n "Pygame KMSDRM: "
sudo -u "$PROX_USER" "$VENV/bin/python3" -c "
import os; os.environ['SDL_VIDEODRIVER']='kmsdrm'
import pygame; pygame.display.init(); print(pygame.display.get_driver()); pygame.quit()
" 2>/dev/null || echo "FAILED"

# HailoRT Python
echo -n "HailoRT Python: "
sudo -u "$PROX_USER" "$VENV/bin/python3" -c "
from hailo_platform import VDevice; print('OK')
" 2>/dev/null || echo "FAILED"

echo
echo "=== Done ==="
echo "Deploy code: scp -r display/ detect/ ingest/ range/ track/ fusion/ tools/ *.py pi@\$(hostname -I | awk '{print \$1}'):~/open-PROX/"
echo "Run: cd ~/open-PROX && SDL_VIDEODRIVER=kmsdrm ~/prox-env/bin/python3 main.py"
