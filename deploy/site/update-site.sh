#!/usr/bin/env bash
# Fetch the latest landing site from GitHub and publish it to $DEST (default /var/www/finvault-site).
# Only the site/ folder is downloaded. Safe to run as often as you like.
#   ./update-site.sh            (uses the main branch)
#   BRANCH=some-branch ./update-site.sh
set -euo pipefail

REPO="${REPO:-https://github.com/henilsarang/finvault.git}"
BRANCH="${BRANCH:-main}"
if [ "$(id -u)" -eq 0 ]; then DEFAULT_SRC=/var/cache/finvault-site-src; else DEFAULT_SRC="$HOME/.cache/finvault-site-src"; fi
SRC="${SRC:-$DEFAULT_SRC}"
if [ "$(uname -s)" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
  DEFAULT_DEST="$(brew --prefix)/var/www/finvault-site"
else
  DEFAULT_DEST=/var/www/finvault-site
fi
DEST="${DEST:-$DEFAULT_DEST}"

if [ ! -d "$SRC/.git" ]; then
  mkdir -p "$(dirname "$SRC")"
  git clone --quiet --depth 1 --filter=blob:none --sparse --branch "$BRANCH" "$REPO" "$SRC"
  git -C "$SRC" sparse-checkout set site
else
  git -C "$SRC" fetch --quiet --depth 1 origin "$BRANCH"
  git -C "$SRC" reset --quiet --hard FETCH_HEAD
fi

if [ ! -f "$SRC/site/index.html" ]; then
  echo "site/index.html not found in $REPO ($BRANCH); nothing published." >&2
  exit 1
fi

# Use sudo only when the destination isn't ours to write (on a Mac with Homebrew it usually is).
SUDO=""
parent="$DEST"; while [ ! -e "$parent" ]; do parent="$(dirname "$parent")"; done
if [ "$(id -u)" -ne 0 ] && [ ! -w "$parent" ]; then SUDO="sudo"; fi
$SUDO mkdir -p "$DEST"
$SUDO rsync -a --delete "$SRC/site/" "$DEST/"
$SUDO chmod -R a+rX "$DEST"
echo "Published $(git -C "$SRC" log -1 --format='%h %s') to $DEST"
