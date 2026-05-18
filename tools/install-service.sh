#!/bin/bash
# Install open-PROX as a systemd service so it starts at boot.
# Run as: sudo ./tools/install-service.sh

set -e

UNIT=/etc/systemd/system/open-prox.service
SRC="$(cd "$(dirname "$0")" && pwd)/open-prox.service"

if [ "$EUID" -ne 0 ]; then
    echo "Run as root: sudo $0"
    exit 1
fi

cp "$SRC" "$UNIT"
chmod 644 "$UNIT"
mkdir -p /home/pi/prox-logs
chown pi:pi /home/pi/prox-logs
touch /var/log/open-prox.log
chmod 644 /var/log/open-prox.log

systemctl daemon-reload
systemctl enable open-prox.service

echo "Installed. Start now with: sudo systemctl start open-prox"
echo "Watch logs: journalctl -u open-prox -f"
echo "Disable at boot: sudo systemctl disable open-prox"
