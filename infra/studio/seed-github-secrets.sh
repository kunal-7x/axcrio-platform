#!/bin/bash
# One-shot: generates strong tokens and registers them as GitHub secrets so the
# studio-deploy workflow has everything it needs. Run once from this machine.
# Requires: gh CLI authenticated, SSH key at ~/.ssh/id_ed25519 (or $SSH_KEY_PATH).
set -euo pipefail

REPO="kunal-7x/axcrio-platform"
SSH_KEY_PATH="${SSH_KEY_PATH:-$HOME/.ssh/id_ed25519}"

if ! command -v gh &>/dev/null; then
  echo "ERROR: install the GitHub CLI first (brew install gh)"
  exit 1
fi

if [[ ! -f "$SSH_KEY_PATH" ]]; then
  echo "ERROR: SSH private key not found at $SSH_KEY_PATH — set SSH_KEY_PATH to override"
  exit 1
fi

echo "seeding GitHub secrets for $REPO..."

# VSCODE_TOKEN — random 32-char hex, persisted to infra/studio/.vscode-token
VSCODE_TOKEN_FILE="$(dirname "$0")/.vscode-token"
if [[ -f "$VSCODE_TOKEN_FILE" ]]; then
  VSCODE_TOKEN=$(cat "$VSCODE_TOKEN_FILE")
  echo "  reusing existing VSCODE_TOKEN from .vscode-token"
else
  VSCODE_TOKEN=$(openssl rand -hex 32)
  echo "$VSCODE_TOKEN" > "$VSCODE_TOKEN_FILE"
  chmod 600 "$VSCODE_TOKEN_FILE"
  echo "  generated new VSCODE_TOKEN (saved to .vscode-token)"
fi

# SSH private key
SSH_KEY_CONTENT=$(cat "$SSH_KEY_PATH")

# Coolify admin — read from env or prompt
COOLIFY_ADMIN_EMAIL="${COOLIFY_ADMIN_EMAIL:-admin@famit.in}"
if [[ -z "${COOLIFY_ADMIN_PASSWORD:-}" ]]; then
  COOLIFY_ADMIN_PASSWORD=$(openssl rand -base64 20)
  echo "  generated COOLIFY_ADMIN_PASSWORD: $COOLIFY_ADMIN_PASSWORD"
  echo "  (save this — you'll need it for the Coolify web UI)"
fi

# Repo URL — derive from git remote
STUDIO_REPO=$(git -C "$(dirname "$0")/../.." remote get-url origin 2>/dev/null || echo "")
# Convert SSH remote to HTTPS so Coolify's git clone works without an SSH key
STUDIO_REPO=$(echo "$STUDIO_REPO" | sed 's|git@github.com:|https://github.com/|;s|\.git$||')

gh secret set SSH_PRIVATE_KEY          --repo "$REPO" --body "$SSH_KEY_CONTENT"
gh secret set VSCODE_TOKEN             --repo "$REPO" --body "$VSCODE_TOKEN"
gh secret set COOLIFY_ADMIN_EMAIL      --repo "$REPO" --body "$COOLIFY_ADMIN_EMAIL"
gh secret set COOLIFY_ADMIN_PASSWORD   --repo "$REPO" --body "$COOLIFY_ADMIN_PASSWORD"
gh secret set STUDIO_REPO              --repo "$REPO" --body "$STUDIO_REPO"

echo ""
echo "All secrets set. Now trigger the deploy:"
echo "  gh workflow run studio-deploy.yml --repo $REPO"
echo ""
echo "Or via the GitHub UI: Actions → studio-deploy → Run workflow"
