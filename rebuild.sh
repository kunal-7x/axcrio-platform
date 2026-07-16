#!/usr/bin/env bash
cd /opt/haptica
C="docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.tls.yml -f deploy/docker-compose.voice.yml --env-file deploy/.env.deploy"
echo "=== CONFIG CHECK ==="; $C config -q && echo CONFIG_OK || { echo CONFIG_FAIL; exit 1; }
echo "=== BUILD START $(date -u) ==="
$C build backend worker frontend && echo "=== BUILD OK ===" || { echo "=== BUILD FAILED rc=$? ==="; exit 1; }
echo "=== UP $(date -u) ==="
$C up -d backend worker frontend && echo "=== UP OK ==="
echo "=== DONE $(date -u) ==="
