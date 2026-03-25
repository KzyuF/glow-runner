#!/bin/bash
# =============================================================
# VPN Server Setup Script
# Run this on a fresh Ubuntu 22.04/24.04 VPS
# Usage: chmod +x setup_server.sh && sudo ./setup_server.sh
# =============================================================

set -e

echo "=== 1. System update ==="
apt update && apt upgrade -y

echo "=== 2. Install Docker ==="
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker

echo "=== 3. Install Marzban ==="
sudo bash -c "$(curl -sL https://github.com/Gozargah/Marzban-scripts/raw/master/marzban.sh)" @ install

echo "=== 4. Marzban is installed ==="
echo ""
echo "Next steps:"
echo "1. Edit /opt/marzban/.env to set SUDO_USERNAME and SUDO_PASSWORD"
echo "2. Run: marzban restart"
echo "3. Set up SSH tunnel to access panel: ssh -L 8000:localhost:8000 user@your-server-ip"
echo "4. Open http://localhost:8000/dashboard in your browser"
echo "5. In the panel: add an inbound with VLESS + TCP + Reality"
echo "6. Copy your panel URL and admin credentials to config/.env"
echo ""
echo "=== Done! ==="
