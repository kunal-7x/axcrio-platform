#!/usr/bin/env bash
# =============================================================================
#  verify.sh — prove the stack is actually working on THIS host.
#
#    ./deploy/verify.sh          # infrastructure proof (fast, safe, no calls)
#    ./deploy/verify.sh --call   # ALSO place a real outbound test call (costs money)
#
#  Deliberately does NOT trust the backend's own /health endpoint: on production
#  it returns 503 permanently because it probes for a SQLAlchemy `engine` that
#  this architecture does not have (state is JSON files; DATABASE_URL is empty).
#  See deploy/KNOWN_ISSUES.md. We probe what is actually true instead.
#
#  Exit 0 = every check passed. Non-zero = do NOT cut DNS over to this host.
# =============================================================================
set -uo pipefail

PASS=0; FAIL=0
ok()   { printf '  \033[1;32m✓\033[0m %s\n' "$*"; PASS=$((PASS+1)); }
bad()  { printf '  \033[1;31m✗\033[0m %s\n' "$*"; FAIL=$((FAIL+1)); }
info() { printf '  \033[1;34mi\033[0m %s\n' "$*"; }
hdr()  { printf '\n\033[1;36m%s\033[0m\n' "$*"; }

DC="docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.tls.yml -f deploy/docker-compose.voice.yml -f deploy/docker-compose.twenty.yml -f deploy/docker-compose.pin.yml --env-file deploy/.env.deploy"

# --- 1. containers ----------------------------------------------------------
hdr "1. Containers"
EXPECTED="backend frontend worker livekit sip egress redis clickhouse caddy twenty twenty-worker twenty-db twenty-redis"
for svc in $EXPECTED; do
  cid=$($DC ps -q "$svc" 2>/dev/null | head -1)
  if [ -z "$cid" ]; then bad "$svc — not created"; continue; fi
  state=$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null)
  restarts=$(docker inspect -f '{{.RestartCount}}' "$cid" 2>/dev/null)
  if [ "$state" = "running" ]; then
    if [ "${restarts:-0}" -gt 3 ]; then bad "$svc running but restarted ${restarts}x — crash-looping"
    else ok "$svc running"; fi
  else bad "$svc — state=$state"; fi
done

# --- 2. the voice path ------------------------------------------------------
hdr "2. Voice path (the part that earns)"
BE=$($DC ps -q backend 2>/dev/null | head -1)
if [ -n "$BE" ]; then
  docker exec "$BE" python -c "
import socket,sys
s=socket.socket(); s.settimeout(5)
try: s.connect(('livekit',7880)); print('OK')
except Exception as e: print('ERR',e); sys.exit(1)" >/dev/null 2>&1 \
    && ok "backend → livekit:7880 reachable" || bad "backend cannot reach livekit:7880"
else bad "backend container missing — cannot test livekit reachability"; fi

# SIP must be LISTENING on 5060/udp. use_external_ip:true means it self-detects
# the public IP, so this works on any cloud without config changes.
if ss -lnup 2>/dev/null | grep -q ':5060'; then ok "SIP listening on 5060/udp"
else bad "nothing listening on 5060/udp — inbound/outbound calls will fail"; fi
if ss -lntp 2>/dev/null | grep -q ':5060'; then ok "SIP listening on 5060/tcp"
else info "5060/tcp not listening (VOBIZ_SIP_TRANSPORT=tcp expects it — check if calls fail)"; fi

# RTP media range must be published, or calls connect with silence.
RTP=$(docker ps --format '{{.Ports}}' 2>/dev/null | grep -c '10000-10100' || true)
[ "${RTP:-0}" -ge 1 ] && ok "RTP 10000-10100/udp published" || bad "RTP range NOT published — calls will connect with NO AUDIO"

# --- 3. data plane ----------------------------------------------------------
hdr "3. Data plane"
if docker run --rm -v haptica-ai_haptica-data:/d alpine test -f /d/calls.json 2>/dev/null; then
  n=$(docker run --rm -v haptica-ai_haptica-data:/d alpine sh -c "wc -c < /d/calls.json" 2>/dev/null | tr -d ' ')
  ok "haptica-data volume mounted, calls.json present (${n} bytes)"
else bad "calls.json missing — the JSON store IS the database; the app will start empty"; fi

CH=$($DC ps -q clickhouse 2>/dev/null | head -1)
if [ -n "$CH" ]; then
  if docker exec "$CH" clickhouse-client --query 'SELECT 1' >/dev/null 2>&1; then
    rows=$(docker exec "$CH" clickhouse-client --query 'SELECT count() FROM default.haptica_voice_calls' 2>/dev/null || echo '?')
    ok "clickhouse queryable (haptica_voice_calls: ${rows} rows)"
  else bad "clickhouse not answering queries"; fi
fi

TDB=$($DC ps -q twenty-db 2>/dev/null | head -1)
if [ -n "$TDB" ]; then
  docker exec "$TDB" pg_isready -U postgres >/dev/null 2>&1 \
    && ok "twenty-db postgres accepting connections" || bad "twenty-db not ready"
fi

# --- 4. web ----------------------------------------------------------------
hdr "4. Web"
PANEL_PORT_V="${PANEL_PORT:-3100}"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://localhost:${PANEL_PORT_V}/" 2>/dev/null)
[ "$code" = "200" ] && ok "frontend HTTP 200 on :${PANEL_PORT_V}" || bad "frontend returned ${code:-no-response} on :${PANEL_PORT_V}"

# Liveness only. /health?deep=1 is knowingly broken (see KNOWN_ISSUES.md).
if [ -n "$BE" ]; then
  st=$(docker exec "$BE" python -c "
import urllib.request
try:
    r=urllib.request.urlopen('http://localhost:8091/health?deep=0',timeout=8); print(r.status)
except Exception as e: print('ERR')" 2>/dev/null)
  [ "$st" = "200" ] && ok "backend liveness (/health?deep=0) 200" || bad "backend not answering on :8091 (got ${st})"
  info "deep health (/health) returns 503 by design-bug, not by fault — see KNOWN_ISSUES.md"
fi

# --- 5. firewall ------------------------------------------------------------
hdr "5. Firewall"
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q 'Status: active'; then
  ok "ufw active"
  iptables -C DOCKER-USER -i "$(ip route show default | awk '{print $5; exit}')" -j ufw-user-input 2>/dev/null \
    && ok "DOCKER-USER chained to ufw (docker not bypassing firewall)" \
    || bad "docker is BYPASSING ufw — published ports are open to the internet"
else info "ufw inactive (fine if the cloud's own firewall/security-group covers it)"; fi

# --- 6. real call -----------------------------------------------------------
if [ "${1:-}" = "--call" ]; then
  hdr "6. REAL outbound test call"
  TEST_NUM=$(grep -E '^test_phone_number_1=' deploy/.env.deploy 2>/dev/null | cut -d= -f2- | tr -d '"'"'"' \r')
  if [ -z "$TEST_NUM" ]; then bad "test_phone_number_1 not set in .env.deploy — cannot place a test call"
  else
    info "dialling ${TEST_NUM} — this costs real money and rings a real phone"
    if [ -n "$BE" ] && docker exec "$BE" python -c "
import urllib.request,json,sys
req=urllib.request.Request('http://localhost:8091/call',
    data=json.dumps({'to':'${TEST_NUM}'}).encode(),
    headers={'Content-Type':'application/json'})
try:
    r=urllib.request.urlopen(req,timeout=30); print(r.status, r.read()[:200].decode()); sys.exit(0)
except Exception as e: print('ERR',e); sys.exit(1)" 2>&1; then
      ok "call API accepted the request — NOW CONFIRM THE PHONE ACTUALLY RANG AND AUDIO WORKED"
      info "an accepted API call is NOT proof of working telephony. Listen to it."
    else bad "call request failed — telephony is NOT working on this host"; fi
  fi
else
  hdr "6. Real call — SKIPPED"
  info "infrastructure checks cannot prove telephony. Run './deploy/verify.sh --call' before trusting this host."
fi

# --- verdict ----------------------------------------------------------------
printf '\n\033[1m── %d passed, %d failed ──\033[0m\n' "$PASS" "$FAIL"
if [ "$FAIL" -gt 0 ]; then
  printf '\033[1;31mVERIFY FAILED — do not cut DNS over to this host.\033[0m\n\n'; exit 1
fi
printf '\033[1;32mInfrastructure verified.\033[0m Telephony is only proven by --call + a human listening.\n\n'
