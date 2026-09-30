#!/usr/bin/env bash
# One-time setup of the FinVault landing site on a Raspberry Pi (Raspberry Pi OS / Debian).
# Installs Caddy, publishes the site on port 8080 and refreshes it from GitHub every night.
#   curl -fsSL https://raw.githubusercontent.com/henilsarang/finvault/main/deploy/site/install-pi.sh | bash
set -euo pipefail

RAW="https://raw.githubusercontent.com/henilsarang/finvault/main/deploy/site"
BIN="/usr/local/bin/finvault-update-site"

echo "==> Installing Caddy, git and rsync"
sudo apt-get update -qq
sudo apt-get install -y -qq caddy git rsync curl

echo "==> Installing the update command at $BIN"
sudo curl -fsSL "$RAW/update-site.sh" -o "$BIN"
sudo chmod 755 "$BIN"

echo "==> Publishing the site"
sudo "$BIN"

echo "==> Configuring Caddy on port 8080"
sudo curl -fsSL "$RAW/Caddyfile" -o /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
sudo systemctl enable --now caddy >/dev/null
sudo systemctl reload caddy

echo "==> Refreshing from GitHub every night at 03:30"
sudo tee /etc/systemd/system/finvault-site-update.service >/dev/null <<EOF
[Unit]
Description=Update the FinVault landing site from GitHub
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=$BIN
EOF
sudo tee /etc/systemd/system/finvault-site-update.timer >/dev/null <<'EOF'
[Unit]
Description=Nightly update of the FinVault landing site

[Timer]
OnCalendar=*-*-* 03:30:00
RandomizedDelaySec=15m
Persistent=true

[Install]
WantedBy=timers.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now finvault-site-update.timer >/dev/null

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "Done. The site is at http://${IP:-this-pi}:8080 on your home network."
echo "Update it now any time with: sudo finvault-update-site"
echo "To put it on the internet, add a Cloudflare Tunnel pointing to http://localhost:8080 (see deploy/site/README.md)."
