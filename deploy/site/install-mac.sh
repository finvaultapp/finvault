#!/usr/bin/env bash
# One-time setup of the FinVault landing site on a Mac (Apple silicon or Intel) with Homebrew.
# Installs Caddy and cloudflared, publishes the site on port 8080, starts Caddy at login,
# and refreshes the site from GitHub every night.
#   curl -fsSL https://raw.githubusercontent.com/finvaultapp/finvault/main/deploy/site/install-mac.sh | bash
set -euo pipefail

RAW="https://raw.githubusercontent.com/finvaultapp/finvault/main/deploy/site"

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is needed first. Install it from https://brew.sh, then run this again." >&2
  exit 1
fi
PREFIX="$(brew --prefix)"
DEST="$PREFIX/var/www/finvault-site"
BIN="$PREFIX/bin/finvault-update-site"
CADDYFILE="$PREFIX/etc/Caddyfile"
PLIST="$HOME/Library/LaunchAgents/io.finvault.site-update.plist"

echo "==> Installing Caddy and cloudflared"
brew install --quiet caddy cloudflared

echo "==> Installing the update command at $BIN"
curl -fsSL "$RAW/update-site.sh" -o "$BIN"
chmod 755 "$BIN"

echo "==> Publishing the site to $DEST"
DEST="$DEST" "$BIN"

echo "==> Configuring Caddy on port 8080"
if [ -f "$CADDYFILE" ] && ! grep -q "finvault-site" "$CADDYFILE"; then
  cp "$CADDYFILE" "$CADDYFILE.before-finvault"
  echo "    (your old Caddyfile is saved as $CADDYFILE.before-finvault)"
fi
curl -fsSL "$RAW/Caddyfile" | sed "s#/var/www/finvault-site#$DEST#" > "$CADDYFILE"
caddy validate --config "$CADDYFILE" --adapter caddyfile >/dev/null
brew services restart caddy >/dev/null

echo "==> Refreshing from GitHub every night at 03:30"
mkdir -p "$(dirname "$PLIST")"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>io.finvault.site-update</string>
  <key>ProgramArguments</key><array><string>$BIN</string></array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>DEST</key><string>$DEST</string>
    <key>PATH</key><string>$PREFIX/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/finvault-site-update.log</string>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/finvault-site-update.log</string>
</dict>
</plist>
EOF
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

sleep 1
if curl -fsS -o /dev/null http://localhost:8080/; then STATUS="is up"; else STATUS="did not answer yet (check: brew services list)"; fi
IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)
echo
echo "Done. The site $STATUS at http://localhost:8080 (on your network: http://${IP:-this-mac}:8080)."
echo "Update it now any time with: finvault-update-site"
echo
echo "Two things to set once on the Mac mini:"
echo "  - System Settings > Energy: turn on 'Prevent automatic sleeping when the display is off'"
echo "    and 'Start up automatically after a power failure'."
echo "  - To put the site on the internet, add a Cloudflare Tunnel pointing to http://localhost:8080"
echo "    (see deploy/site/README.md)."
