#!/usr/bin/env bash
# Fetch the latest landing site from GitHub and publish it to /var/www/finvault-site.
# Only the site/ folder is downloaded. Safe to run as often as you like.
#   ./update-site.sh            (uses the main branch)
#   BRANCH=some-branch ./update-site.sh
set -euo pipefail

REPO="${REPO:-https://github.com/henilsarang/finvault.git}"
BRANCH="${BRANCH:-main}"
if [ "$(id -u)" -eq 0 ]; then DEFAULT_SRC=/var/cache/finvault-site-src; else DEFAULT_SRC="$HOME/.cache/finvault-site-src"; fi
SRC="${SRC:-$DEFAULT_SRC}"
DEST="${DEST:-/var/www/finvault-site}"

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

sudo mkdir -p "$DEST"
sudo rsync -a --delete "$SRC/site/" "$DEST/"
sudo chmod -R a+rX "$DEST"
echo "Published $(git -C "$SRC" log -1 --format='%h %s') to $DEST"
