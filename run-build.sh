#!/usr/bin/env bash
set -o pipefail
cd /opt/haptica
C="docker compose -f deploy/docker-compose.yml --env-file deploy/.env.deploy"
echo "=== BUILD START $(date -u) ==="
$C build && echo "=== BUILD OK ===" || { echo "=== BUILD FAILED rc=$? ==="; exit 1; }
echo "=== UP START $(date -u) ==="
$C up -d && echo "=== UP OK ===" || { echo "=== UP FAILED rc=$? ==="; exit 1; }
echo "=== DEPLOY_DONE $(date -u) ==="
