#!/usr/bin/env bash
# One-time setup on an Ubuntu server. Run from the repo folder:
#   bash deploy/install.sh
# Safe to run again. It installs packages, creates the Python environment,
# installs a systemd service so the bot starts on boot and restarts if it
# crashes, and schedules a daily database backup.
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_USER="$(whoami)"
SERVICE=/etc/systemd/system/mtgbot.service

echo "==> Installing system packages"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git sqlite3

if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
  echo "This server has $(python3 --version), but the bot needs Python 3.10 or newer."
  echo "Use an Ubuntu 24.04 image (see docs/oracle-cloud.md, step 2)."
  exit 1
fi

echo "==> Creating Python environment in $APP_DIR/.venv"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  echo "==> Created .env from the example. You still need to paste your token into it."
fi
chmod 600 "$APP_DIR/.env"   # only your user can read the token

echo "==> Installing systemd service (runs as $APP_USER)"
sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__APP_USER__|$APP_USER|g" \
  "$APP_DIR/deploy/mtgbot.service" | sudo tee "$SERVICE" > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable mtgbot

echo "==> Scheduling a daily backup at 04:15 (server time)"
chmod +x "$APP_DIR/deploy/"*.sh
CRON_LINE="15 4 * * * $APP_DIR/deploy/backup.sh >> $APP_DIR/backups/backup.log 2>&1"
mkdir -p "$APP_DIR/backups"
( crontab -l 2>/dev/null | grep -v 'deploy/backup.sh' ; echo "$CRON_LINE" ) | crontab -

if grep -q '^DISCORD_TOKEN=paste-your-bot-token-here' "$APP_DIR/.env"; then
  echo
  echo "Almost done. Put your bot token in .env, then start the bot:"
  echo "  nano $APP_DIR/.env"
  echo "  sudo systemctl start mtgbot"
else
  sudo systemctl restart mtgbot
  echo
  echo "The bot is running. Check it with: sudo systemctl status mtgbot"
fi
