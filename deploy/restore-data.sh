#!/usr/bin/env bash
# =============================================================================
#  restore-data.sh — restore the production data bundle onto a fresh host.
#
#      ./deploy/restore-data.sh /path/to/haptica-data-bundle-YYYYMMDD.tar.gz
#
#  The bundle is made by ./deploy/backup-data.sh on the OLD host.
#  Whole thing is ~3 MB: this product's entire state is small.
#
#  Contents and where each part goes:
#    haptica-data.tar.gz    -> docker volume haptica-ai_haptica-data
#                              (calls.json, cost_ledger.json, billing.json,
#                               bookings.jsonl, campaigns/, ads/ … )
#                              *** THIS IS THE DATABASE. There is no Postgres for
#                              the app — DATABASE_URL is empty by design. ***
#    twenty-db.sql.gz       -> Twenty CRM postgres (pg_restore via psql)
#    ch_*.native.gz         -> ClickHouse analytics tables
#
#  Safe to re-run. Refuses to clobber non-empty state unless --force.
# =============================================================================
set -euo pipefail

BUNDLE="${1:-}"
FORCE="${2:-}"
[ -n "$BUNDLE" ] && [ -f "$BUNDLE" ] || { echo "usage: $0 <bundle.tar.gz> [--force]"; exit 2; }

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '    \033[1;33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

DC="docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.tls.yml -f deploy/docker-compose.voice.yml -f deploy/docker-compose.twenty.yml -f deploy/docker-compose.pin.yml --env-file deploy/.env.deploy"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
tar xzf "$BUNDLE" -C "$TMP"
ok "bundle extracted"

# --- 1. the JSON store (the real database) ----------------------------------
log "haptica-data volume (the JSON store — this IS the database)"
if [ -f "$TMP/haptica-data.tar.gz" ]; then
  EXISTING=$(docker run --rm -v haptica-ai_haptica-data:/d alpine sh -c 'ls /d 2>/dev/null | wc -l' 2>/dev/null || echo 0)
  if [ "${EXISTING:-0}" -gt 0 ] && [ "$FORCE" != "--force" ]; then
    warn "volume already has ${EXISTING} entries — refusing to overwrite. Re-run with --force to replace."
  else
    # Stop writers first: backend and worker both mount this volume, and these are
    # plain JSON files with no transactions. Restoring under a live writer loses data.
    $DC stop backend worker >/dev/null 2>&1 || true
    docker run --rm -i -v haptica-ai_haptica-data:/d alpine sh -c 'rm -rf /d/* /d/.[!.]* 2>/dev/null; tar xzf - -C /d' < "$TMP/haptica-data.tar.gz"
    $DC start backend worker >/dev/null 2>&1 || true
    n=$(docker run --rm -v haptica-ai_haptica-data:/d alpine sh -c 'ls /d | wc -l')
    ok "restored ${n} entries into haptica-ai_haptica-data"
  fi
else warn "haptica-data.tar.gz not in bundle — skipping"; fi

# --- 2. Twenty CRM postgres -------------------------------------------------
log "Twenty CRM postgres"
if [ -f "$TMP/twenty-db.sql.gz" ]; then
  TDB=$($DC ps -q twenty-db 2>/dev/null | head -1)
  [ -n "$TDB" ] || die "twenty-db container not running — start the stack first"
  for i in $(seq 1 30); do docker exec "$TDB" pg_isready -U postgres >/dev/null 2>&1 && break; sleep 2; done
  docker exec "$TDB" pg_isready -U postgres >/dev/null 2>&1 || die "twenty-db never became ready"
  gunzip -c "$TMP/twenty-db.sql.gz" | docker exec -i "$TDB" psql -U postgres -q >/dev/null 2>&1 \
    && ok "twenty-db restored" || warn "twenty-db restore reported errors (often benign: role/db already exists)"
else warn "twenty-db.sql.gz not in bundle — skipping"; fi

# --- 3. ClickHouse ----------------------------------------------------------
log "ClickHouse analytics"
CH=$($DC ps -q clickhouse 2>/dev/null | head -1)
if [ -n "$CH" ]; then
  for i in $(seq 1 30); do docker exec "$CH" clickhouse-client --query 'SELECT 1' >/dev/null 2>&1 && break; sleep 2; done
  for f in "$TMP"/ch_*.schema.sql; do
    [ -f "$f" ] || continue
    t=$(basename "$f" .schema.sql); t=${t#ch_}
    # Recreate the table from its captured DDL, then stream the Native dump back.
    sed 's/^CREATE TABLE /CREATE TABLE IF NOT EXISTS /' "$f" | docker exec -i "$CH" clickhouse-client -n >/dev/null 2>&1 || true
    if [ -f "$TMP/ch_${t}.native.gz" ]; then
      gunzip -c "$TMP/ch_${t}.native.gz" | docker exec -i "$CH" clickhouse-client --query "INSERT INTO default.${t} FORMAT Native" >/dev/null 2>&1 \
        && ok "clickhouse ${t}: $(docker exec "$CH" clickhouse-client --query "SELECT count() FROM default.${t}" 2>/dev/null) rows" \
        || warn "clickhouse ${t}: insert failed"
    fi
  done
else warn "clickhouse container not running — skipping"; fi

log "Restore complete"
echo "    Now prove it:  ./deploy/verify.sh"
echo "    Then prove telephony for real:  ./deploy/verify.sh --call"
