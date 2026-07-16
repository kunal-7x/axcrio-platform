#!/usr/bin/env bash
# =============================================================================
#  bootstrap.sh — bare Ubuntu box  ->  running Haptica voice product
#  ANY cloud: AWS, GCP, Azure, Hetzner, Vultr, Linode, Oracle, DigitalOcean, bare metal.
#
#  USAGE (from the repo root, as root on a fresh Ubuntu 22.04/24.04 box):
#      ./deploy/bootstrap.sh                      # full install + deploy
#      ./deploy/bootstrap.sh --skip-harden        # skip ufw/fail2ban (if cloud does it)
#      ./deploy/bootstrap.sh --data ./bundle.tgz  # also restore a data bundle
#      ./deploy/bootstrap.sh --no-deploy          # prepare host only
#
#  PREREQUISITE — the one thing this script cannot do for you:
#      cp deploy/.env.deploy.example deploy/.env.deploy   # then fill in the 66 secrets
#
#  Idempotent: safe to re-run. Every step checks before it acts.
# =============================================================================
set -euo pipefail

# ---- config ----------------------------------------------------------------
# VOBIZ SIP edge — the only sources allowed to reach our SIP port.
# This is OUR inbound firewall, not VOBIZ's allowlist: VOBIZ authenticates us by
# credentials, so a new cloud IP needs no ticket on their side. Verify with a
# real test call after cutover (deploy/verify.sh --call).
VOBIZ_SIP_IPS="${VOBIZ_SIP_IPS:-13.203.7.132 65.2.100.211}"
RTP_PORTS="10000:10100"
COMPOSE_FILES="-f deploy/docker-compose.yml -f deploy/docker-compose.tls.yml -f deploy/docker-compose.voice.yml -f deploy/docker-compose.twenty.yml -f deploy/docker-compose.pin.yml"
ENV_FILE="deploy/.env.deploy"

SKIP_HARDEN=0; NO_DEPLOY=0; DATA_BUNDLE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --skip-harden) SKIP_HARDEN=1 ;;
    --no-deploy)   NO_DEPLOY=1 ;;
    --data)        DATA_BUNDLE="${2:-}"; shift ;;
    -h|--help)     sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '    \033[1;33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ---- 0. preflight ----------------------------------------------------------
log "Preflight"
[ "$(id -u)" -eq 0 ] || die "run as root (sudo ./deploy/bootstrap.sh)"
[ -f deploy/docker-compose.yml ] || die "run from the REPO ROOT, not from deploy/"
. /etc/os-release 2>/dev/null || die "cannot read /etc/os-release"
case "${VERSION_ID:-}" in
  22.04|24.04) ok "Ubuntu $VERSION_ID" ;;
  *) warn "untested on ${PRETTY_NAME:-unknown} — built for Ubuntu 22.04/24.04" ;;
esac

MEM_MB=$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo)
DISK_GB=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
[ "$MEM_MB" -ge 7000 ] || warn "RAM ${MEM_MB}MB — production ran on 8GB and used ~4GB. Under 8GB is risky."
[ "$DISK_GB" -ge 40 ]  || die  "only ${DISK_GB}GB free — need ≥40GB (images ~14GB + build cache)"
ok "RAM ${MEM_MB}MB, disk ${DISK_GB}GB free"

[ -f "$ENV_FILE" ] || die "$ENV_FILE missing.
    cp deploy/.env.deploy.example $ENV_FILE  and fill in the 66 secret values.
    That file is the ONLY thing not reconstructible from this repo — by design."

MISSING=$(grep -cE '^[A-Z0-9_]+=$' "$ENV_FILE" 2>/dev/null || echo 0)
[ "$MISSING" -eq 0 ] || warn "$MISSING keys in $ENV_FILE are still empty — the stack may start but misbehave"
ok "$ENV_FILE present"

# ---- 1. docker -------------------------------------------------------------
log "Docker"
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  ok "already installed ($(docker --version | cut -d, -f1))"
else
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg >/dev/null
  install -m 0755 -d /etc/apt/keyrings
  [ -f /etc/apt/keyrings/docker.asc ] || \
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
  systemctl enable --now docker >/dev/null 2>&1 || true
  ok "installed $(docker --version | cut -d, -f1)"
fi

# ---- 2. swap ---------------------------------------------------------------
# Production ran with a 4GB swapfile; the frontend build (node) OOMs on 8GB without it.
log "Swap"
if swapon --show 2>/dev/null | grep -q .; then
  ok "already active ($(swapon --show=SIZE --noheadings | head -1 | tr -d ' '))"
else
  fallocate -l 4G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=4096 status=none
  chmod 600 /swapfile; mkswap -q /swapfile; swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  ok "created 4GB swapfile"
fi

# ---- 3. harden -------------------------------------------------------------
if [ "$SKIP_HARDEN" -eq 0 ]; then
  log "Firewall + fail2ban"
  apt-get install -y -qq ufw fail2ban >/dev/null 2>&1 || true

  ufw --force reset >/dev/null 2>&1
  ufw default deny incoming  >/dev/null
  ufw default allow outgoing >/dev/null
  ufw allow 22/tcp comment 'ssh' >/dev/null

  # 80/443 only from Cloudflare — the origin must not be reachable directly.
  # Fetched live rather than hardcoded, so this stays correct as CF changes ranges.
  CF_OK=0
  for u in https://www.cloudflare.com/ips-v4 https://www.cloudflare.com/ips-v6; do
    if RANGES=$(curl -fsS --max-time 15 "$u" 2>/dev/null) && [ -n "$RANGES" ]; then
      for r in $RANGES; do
        ufw allow proto tcp from "$r" to any port 80,443 comment 'cloudflare' >/dev/null 2>&1 || true
      done
      CF_OK=1
    fi
  done
  if [ "$CF_OK" -eq 1 ]; then ok "80/443 restricted to Cloudflare ranges (fetched live)"
  else
    warn "could not fetch Cloudflare ranges — opening 80/443 to the world as a fallback"
    ufw allow 80,443/tcp comment 'http(s) fallback' >/dev/null
  fi

  # SIP signalling: only the VOBIZ edge may reach us.
  for ip in $VOBIZ_SIP_IPS; do
    ufw allow proto tcp from "$ip" to any port 5060 comment 'vobiz sip' >/dev/null
    ufw allow proto udp from "$ip" to any port 5060 comment 'vobiz sip' >/dev/null
  done
  ok "5060 restricted to VOBIZ: $VOBIZ_SIP_IPS"

  # RTP media must stay open: media can arrive from any relay/carrier IP, not just
  # the signalling edge. Locking this to VOBIZ's IPs is the classic way to get a
  # connected call with no audio.
  ufw allow "${RTP_PORTS}/udp" comment 'rtp media' >/dev/null
  ok "RTP ${RTP_PORTS}/udp open (required — media does not come from the SIP IP)"

  ufw --force enable >/dev/null
  systemctl enable --now fail2ban >/dev/null 2>&1 || true
  ok "ufw active, fail2ban running"

  # Docker publishes ports by writing DOCKER-USER iptables rules that BYPASS ufw.
  # Without this, every port above is effectively open to the internet regardless
  # of what ufw says. This is the single most-missed step in docker+ufw setups.
  if ! iptables -C DOCKER-USER -i "$(ip route show default | awk '{print $5; exit}')" -j ufw-user-input 2>/dev/null; then
    IFACE=$(ip route show default | awk '{print $5; exit}')
    iptables -I DOCKER-USER -i "$IFACE" -j ufw-user-input 2>/dev/null && \
      ok "DOCKER-USER chained to ufw (docker was bypassing the firewall)" || \
      warn "could not chain DOCKER-USER to ufw — verify published ports manually"
  else
    ok "DOCKER-USER already chained to ufw"
  fi
else
  warn "hardening skipped (--skip-harden)"
fi

# ---- 4. deploy -------------------------------------------------------------
if [ "$NO_DEPLOY" -eq 1 ]; then log "Host ready (--no-deploy)"; exit 0; fi

log "Build + start (first run pulls ~14GB and builds 4 images — 10-20 min)"
docker compose $COMPOSE_FILES --env-file "$ENV_FILE" up -d --build
ok "compose up complete"

# ---- 5. restore data -------------------------------------------------------
if [ -n "$DATA_BUNDLE" ]; then
  log "Restore data bundle"
  [ -f "$DATA_BUNDLE" ] || die "data bundle not found: $DATA_BUNDLE"
  ./deploy/restore-data.sh "$DATA_BUNDLE"
fi

# ---- 6. verify -------------------------------------------------------------
log "Verify"
./deploy/verify.sh || die "verification FAILED — the stack is up but not healthy. Do NOT cut DNS over."

cat <<EOF

  ✅ Stack is up and verified on this host.

  Remaining steps that need a human decision:
    1. Point DNS (haptica.famit.in) at this box's IP  →  Cloudflare A record
       Caddy will issue TLS automatically via the CF DNS-01 challenge (needs CF_API_TOKEN).
    2. Place a REAL test call before trusting it:  ./deploy/verify.sh --call
       A green container check is NOT proof that telephony works.
    3. Keep the old host alive until step 2 passes.

EOF
