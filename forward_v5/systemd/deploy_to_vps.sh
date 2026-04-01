#!/bin/bash
# Deploy Block 5.1 to Hostinger VPS
# Run this script on the VPS as root or with sudo

set -e

echo "=== Block 5.1 Deploy Script ==="
echo "Target: Hostinger VPS"
echo "Time: $(date)"
echo ""

# 1. Git pull latest
echo "[1/5] Pulling latest code..."
cd /data/.openclaw/workspace/forward_v5/forward_v5 || {
    echo "ERROR: Workspace not found at expected path"
    exit 1
}
git pull origin main

# 2. Install service file
echo "[2/5] Installing systemd service..."
cp systemd/forward_v5.service /etc/systemd/system/
chmod 644 /etc/systemd/system/forward_v5.service

# 3. Set permissions
echo "[3/5] Setting permissions..."
chown -R node:node /data/.openclaw/workspace/forward_v5/

# 4. Reload systemd
echo "[4/5] Reloading systemd..."
systemctl daemon-reload

# 5. Status check
echo "[5/5] Verification..."
systemd-analyze verify /etc/systemd/system/forward_v5.service
if [ $? -eq 0 ]; then
    echo "✅ Service file valid"
else
    echo "❌ Service file has errors"
    exit 1
fi

echo ""
echo "=== Deploy Complete ==="
echo "Next steps:"
echo "  sudo systemctl start forward_v5.service"
echo "  sudo systemctl status forward_v5.service"
echo "  sudo journalctl -u forward_v5 -f"
