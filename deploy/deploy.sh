#!/usr/bin/env bash
# One-command deploy for Haptica AI (panel + backend) via Docker Compose.
# Run ON the target box, from the repo root:   ./deploy/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."                        # -> repo root
COMPOSE="docker compose -f deploy/docker-compose.yml --env-file deploy/.env.deploy"

if [ ! -f deploy/.env.deploy ]; then
  echo "deploy/.env.deploy is missing."
  echo "  cp deploy/env.deploy.example deploy/.env.deploy   then fill it"
  echo "  (easiest: cp droplet_work/.env deploy/.env.deploy  and add PANEL_PORT)."
  exit 1
fi
set -a; . deploy/.env.deploy; set +a           # expose PANEL_PORT for the healthcheck
PORT="${PANEL_PORT:-3100}"

echo "==> Building images (first build takes a few minutes)…"
$COMPOSE build
echo "==> Starting containers…"
$COMPOSE up -d
echo "==> Status:"; $COMPOSE ps
echo "==> Waiting for the panel to boot…"; sleep 10
if curl -fsS "http://127.0.0.1:${PORT}/login" -o /dev/null; then
  echo "Panel is UP -> http://<box-ip>:${PORT}/login"
else
  echo "Panel not answering yet. Check logs:  $COMPOSE logs -f frontend backend"
fi
echo
echo "The live site on :80/:443 was NOT touched. Roll back any time:"
echo "  $COMPOSE down            # stops Haptica AI, keeps the data volume"
