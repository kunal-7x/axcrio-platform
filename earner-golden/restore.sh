#!/usr/bin/env bash
# /opt/famit-agent/_GOLDEN_R9_20260621/restore.sh
# ONE-COMMAND restore of the GOLDEN working voice brain (R9, 2026-06-21).
# The founder test-confirmed this brain: dead-air fixed, no 'haan' loop, key-spread
# architecture, EL_STABILITY=0.55. agent.py + prompt.py are byte-LOCKED (voice law).
#
#   Run:  sudo /opt/famit-agent/_GOLDEN_R9_20260621/restore.sh
#
# It ASSERTS the md5s + the TTS voice-span + EL_STABILITY BEFORE restarting.
# ANY mismatch => ABORT (never restarts a non-golden brain).
set -euo pipefail

G="/opt/famit-agent/_GOLDEN_R9_20260621"
A="/opt/famit-agent"
DROPIN="/etc/systemd/system/famit-agent.service.d/kernel-outbound.conf"

AGENT_MD5="11a865feb758b25a20cc3e0c291b4ad2"
PROMPT_MD5="4ae81ac64d2faf5da225b4b5965978e5"
TTS_SPAN_MD5="4ada9f1e0cb8304ea69194ef38f0ae25"   # md5 of agent.py lines 596-616 (the elevenlabs.TTS(...) block)

echo "[restore] backing up current live files (pre-restore) ..."
ts=$(date +%Y%m%d-%H%M%S)
cp "$A/agent.py"  "$A/agent.py.preR9restore.$ts"  || true
cp "$A/prompt.py" "$A/prompt.py.preR9restore.$ts" || true
cp "$DROPIN" "$DROPIN.preR9restore.$ts" 2>/dev/null || true

echo "[restore] copying golden agent.py / prompt.py / llm_router + systemd drop-in ..."
install -o famit -g famit -m 644 "$G/agent.py"  "$A/agent.py"
install -o famit -g famit -m 644 "$G/prompt.py" "$A/prompt.py"
mkdir -p "$A/llm_router"
install -o famit -g famit -m 644 "$G"/llm_router/*.py "$A/llm_router/"
cp "$G/kernel-outbound.conf" "$DROPIN"

echo "[restore] asserting md5s + VOICE LAW (TTS span) ..."
got_agent=$(md5sum "$A/agent.py"  | cut -d' ' -f1)
got_prompt=$(md5sum "$A/prompt.py" | cut -d' ' -f1)
got_span=$(sed -n '596,616p' "$A/agent.py" | md5sum | cut -d' ' -f1)
test "$got_agent"  = "$AGENT_MD5"  || { echo "!! AGENT MD5 MISMATCH ($got_agent != $AGENT_MD5) ???????? ABORT"; exit 1; }
test "$got_prompt" = "$PROMPT_MD5" || { echo "!! PROMPT MD5 MISMATCH ($got_prompt != $PROMPT_MD5) ???????? ABORT"; exit 1; }
test "$got_span"   = "$TTS_SPAN_MD5" || { echo "!! TTS SPAN CHANGED ???????? VOICE LAW VIOLATION ???????? ABORT"; exit 1; }

echo "[restore] asserting EL_STABILITY=0.55 in live .env ..."
grep -qE '^EL_STABILITY=0\.55$' "$A/.env" || {
  echo "   EL_STABILITY not 0.55 ???????? forcing it ..."
  if grep -qE '^EL_STABILITY=' "$A/.env"; then
    sed -i -E 's/^EL_STABILITY=.*/EL_STABILITY=0.55/' "$A/.env"
  else
    echo "EL_STABILITY=0.55" >> "$A/.env"
  fi
}
grep -qE '^EL_STABILITY=0\.55$' "$A/.env" || { echo "!! EL_STABILITY still not 0.55 ???????? ABORT"; exit 1; }

echo "[restore] py_compile ..."
/opt/capsy-agent/.venv/bin/python -m py_compile "$A/agent.py" "$A/prompt.py"

echo "[restore] daemon-reload + restart famit-agent ..."
systemctl daemon-reload
systemctl reset-failed famit-agent || true
systemctl restart famit-agent
sleep 2
echo "[restore] service=$(systemctl is-active famit-agent)  NRestarts=$(systemctl show famit-agent -p NRestarts --value)"
echo "[restore] DONE ???????? GOLDEN R9 brain restored + asserted. Founder: make ONE real call to confirm."

