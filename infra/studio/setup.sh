#!/bin/bash
# Famit Studio provisioner — runs on famit-hatchet (68.183.94.38).
# Idempotent / re-runnable. Outputs env vars on the last line (JSON) so the
# calling workflow can parse and forward them to the panel server.
#
# Required env vars (set by the GH Action):
#   STUDIO_REPO      — git clone URL for the famit-panel source (for workspace)
#   VSCODE_TOKEN     — connection token for OpenVSCode Server (generate once, store as GH secret)
#   COOLIFY_ADMIN_EMAIL    — initial Coolify admin email
#   COOLIFY_ADMIN_PASSWORD — initial Coolify admin password
#
# Outputs (written to /data/studio/studio.env AND printed as JSON):
#   COOLIFY_URL, COOLIFY_API_KEY, NEXT_PUBLIC_OPENVSCODE_URL
set -euo pipefail
HATCHET_IP="68.183.94.38"
COOLIFY_PORT=8000
VSCODE_PORT=8080
DATA_DIR="/data/studio"
COMPOSE_DIR="/opt/famit-studio"
MARKER="$DATA_DIR/.provisioned"

log() { echo "[studio-setup] $*"; }

# ── 1. Prerequisites ──────────────────────────────────────────────────────────
log "ensuring prerequisites..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y -qq
apt-get install -y -qq curl jq git ufw

# Docker (already installed by hatchet-cloud-init, but ensure daemon is up)
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi

# ── 2. Firewall: open Coolify + OpenVSCode ports ──────────────────────────────
log "opening firewall ports $COOLIFY_PORT (Coolify) and $VSCODE_PORT (VSCode)..."
ufw allow "$COOLIFY_PORT"/tcp comment "Coolify"
ufw allow "$VSCODE_PORT"/tcp comment "OpenVSCode Server"
ufw reload || true

# ── 3. Install Coolify (idempotent) ───────────────────────────────────────────
if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^coolify$"; then
  log "installing Coolify..."
  # Coolify install writes its compose to /data/coolify
  curl -fsSL https://cdn.coollabs.io/coolify/install.sh | FORCE=1 bash
  log "waiting for Coolify to initialise (up to 120s)..."
  for i in $(seq 1 24); do
    if curl -sf "http://localhost:$COOLIFY_PORT/api/v1/healthcheck" &>/dev/null; then
      log "Coolify is up"
      break
    fi
    sleep 5
  done
else
  log "Coolify already running, skipping install"
fi

# Give it extra time to finish DB migrations on first boot
sleep 10

# ── 4. Bootstrap Coolify admin account + extract API token ────────────────────
log "setting up Coolify admin and API token..."
COOLIFY_TOKEN=""

# Try to create / retrieve the API token via artisan (inside the coolify container).
# Uses tinker because Coolify doesn't expose a headless token-creation CLI yet.
COOLIFY_TOKEN=$(docker exec coolify php artisan tinker --no-interaction <<'TINKER' 2>/dev/null | tail -1
use App\Models\User;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Str;

$email    = getenv('COOLIFY_ADMIN_EMAIL') ?: 'admin@famit.in';
$password = getenv('COOLIFY_ADMIN_PASSWORD') ?: Str::random(24);

$user = User::firstOrCreate(
    ['email' => $email],
    ['name' => 'Famit Admin', 'password' => Hash::make($password), 'email_verified_at' => now()]
);

// Revoke old famit-studio tokens and issue fresh one
$user->tokens()->where('name', 'famit-studio')->delete();
$token = $user->createToken('famit-studio');
echo $token->plainTextToken;
TINKER
) || true

if [[ -z "$COOLIFY_TOKEN" ]]; then
  log "WARNING: could not extract Coolify token via artisan — Coolify may still be migrating. Retrying in 30s..."
  sleep 30
  COOLIFY_TOKEN=$(docker exec coolify php artisan tinker --no-interaction <<'TINKER2' 2>/dev/null | tail -1
use App\Models\User;
$user = User::where('name', 'Famit Admin')->orWhere('email', 'admin@famit.in')->first();
if ($user) {
  $user->tokens()->where('name', 'famit-studio')->delete();
  echo $user->createToken('famit-studio')->plainTextToken;
}
TINKER2
  ) || true
fi

if [[ -z "$COOLIFY_TOKEN" ]]; then
  log "ERROR: still no token — check Coolify startup logs: docker logs coolify"
  exit 1
fi
log "Coolify API token obtained (${#COOLIFY_TOKEN} chars)"

# ── 5. Deploy OpenVSCode Server ───────────────────────────────────────────────
log "deploying OpenVSCode Server..."
mkdir -p "$DATA_DIR/workspace" "$COMPOSE_DIR"

# Clone workspace on first provision
if [[ ! -d "$DATA_DIR/workspace/.git" && -n "${STUDIO_REPO:-}" ]]; then
  log "cloning repo into workspace..."
  git clone "$STUDIO_REPO" "$DATA_DIR/workspace" || true
fi

# Write compose file from this repo's infra/studio/docker-compose.yml
cp "$(dirname "$0")/docker-compose.yml" "$COMPOSE_DIR/docker-compose.yml"

# Write env file for compose
cat > "$COMPOSE_DIR/.env" <<ENVFILE
VSCODE_TOKEN=${VSCODE_TOKEN:-changeme-set-VSCODE_TOKEN-secret}
ENVFILE

docker compose -f "$COMPOSE_DIR/docker-compose.yml" --env-file "$COMPOSE_DIR/.env" up -d --pull always
log "OpenVSCode Server started on port $VSCODE_PORT"

# ── 6. Write output env file ──────────────────────────────────────────────────
mkdir -p "$DATA_DIR"
cat > "$DATA_DIR/studio.env" <<STUDIO
COOLIFY_URL=http://${HATCHET_IP}:${COOLIFY_PORT}
COOLIFY_API_KEY=${COOLIFY_TOKEN}
NEXT_PUBLIC_OPENVSCODE_URL=http://${HATCHET_IP}:${VSCODE_PORT}?tkn=${VSCODE_TOKEN:-changeme}
STUDIO

log "provisioning complete"
touch "$MARKER"

# Print as JSON for the GH Action to capture
echo "STUDIO_ENV_JSON=$(jq -n \
  --arg cu "http://${HATCHET_IP}:${COOLIFY_PORT}" \
  --arg ck "${COOLIFY_TOKEN}" \
  --arg vu "http://${HATCHET_IP}:${VSCODE_PORT}?tkn=${VSCODE_TOKEN:-changeme}" \
  '{COOLIFY_URL:$cu,COOLIFY_API_KEY:$ck,NEXT_PUBLIC_OPENVSCODE_URL:$vu}')"
