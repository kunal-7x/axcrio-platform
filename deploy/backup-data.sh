#!/usr/bin/env bash
# =============================================================================
#  backup-data.sh — capture ALL production state into one portable bundle.
#
#      ./deploy/backup-data.sh [outdir]      # default: ./_backup
#
#  Run this on the CURRENT host before migrating, and on a schedule afterwards.
#  Output is a single .tar.gz (~3 MB) that restore-data.sh consumes on any host.
#
#  Why this exists: this product's state is NOT in a managed database. It is
#  JSON files on a docker volume (DATABASE_URL is empty). Nothing else backs it up.
# =============================================================================
set -euo pipefail
OUT="${1:-./_backup}"
STAMP=$(date -u +%Y%m%d-%H%M%S)
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
mkdir -p "$OUT"

ok() { printf '    \033[1;32m✓\033[0m %s\n' "$*"; }
printf '\n\033[1;36m==> Backing up production state\033[0m\n'

# 1. The JSON store — the actual database.
docker run --rm -v haptica-ai_haptica-data:/d alpine tar czf - -C /d . > "$WORK/haptica-data.tar.gz" 2>/dev/null
ok "haptica-data ($(du -h "$WORK/haptica-data.tar.gz" | cut -f1))"

# 2. Twenty CRM postgres.
if CID=$(docker ps -qf name=twenty-db | head -1) && [ -n "$CID" ]; then
  docker exec "$CID" pg_dumpall -U postgres 2>/dev/null | gzip > "$WORK/twenty-db.sql.gz"
  ok "twenty-db ($(du -h "$WORK/twenty-db.sql.gz" | cut -f1))"
fi

# 3. ClickHouse — schema + data per table, portable across versions.
if CID=$(docker ps -qf name=clickhouse | head -1) && [ -n "$CID" ]; then
  for t in $(docker exec "$CID" clickhouse-client --query 'SHOW TABLES FROM default' 2>/dev/null); do
    docker exec "$CID" clickhouse-client --query "SHOW CREATE TABLE default.$t" > "$WORK/ch_${t}.schema.sql" 2>/dev/null
    docker exec "$CID" clickhouse-client --query "SELECT * FROM default.$t FORMAT Native" 2>/dev/null | gzip > "$WORK/ch_${t}.native.gz"
    ok "clickhouse $t ($(docker exec "$CID" clickhouse-client --query "SELECT count() FROM default.$t" 2>/dev/null) rows)"
  done
fi

BUNDLE="$OUT/haptica-data-bundle-${STAMP}.tar.gz"
tar czf "$BUNDLE" -C "$WORK" .
printf '\n\033[1;32m✓ %s (%s)\033[0m\n' "$BUNDLE" "$(du -h "$BUNDLE" | cut -f1)"
echo "  Restore on any host:  ./deploy/restore-data.sh $BUNDLE"
echo
echo "  NOTE: secrets are NOT in this bundle. deploy/.env.deploy must be carried separately."
