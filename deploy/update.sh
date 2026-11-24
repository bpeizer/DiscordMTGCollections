#!/usr/bin/env bash
# Pull the latest code from GitHub and restart the bot:
#   bash deploy/update.sh
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"
"$APP_DIR/deploy/backup.sh"          # safety copy before changing anything
git pull --ff-only
"$APP_DIR/.venv/bin/pip" install -r requirements.txt
sudo systemctl restart mtgbot
sleep 3
sudo systemctl --no-pager status mtgbot | head -5
