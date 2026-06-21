#!/usr/bin/env bash
# /opt/famit-agent/_GOLDEN_ROUND7/restore.sh
# ONE-COMMAND restore of the golden working voice brain (ROUND-7 FINAL, 2026-06-20).
# Run: sudo /opt/famit-agent/_GOLDEN_ROUND7/restore.sh
set -euo pipefail
G="/opt/famit-agent/_GOLDEN_ROUND7"
A="/opt/famit-agent"
AGENT_MD5="10662d32fc857d88c62c7cc2549134cb"
PROMPT_MD5="b99c25eaa9dc80edffb9ce615d5892c7"
TTS_SPAN_MD5="7b36c4f9d57cd76d5116d93156560dcb"

echo "[restore] copying golden agent.py / prompt.py / llm_router + drop-in ..."
install -o famit -g famit -m 644 "$G/agent.py"  "$A/agent.py"
install -o famit -g famit -m 644 "$G/prompt.py" "$A/prompt.py"
mkdir -p "$A/llm_router"
install -o famit -g famit -m 644 "$G"/llm_router/*.py "$A/llm_router/"
cp "$G/kernel-outbound.conf" /etc/systemd/system/famit-agent.service.d/kernel-outbound.conf

echo "[restore] asserting md5s + VOICE LAW (TTS span) ..."
test "$(md5sum "$A/agent.py"  | cut -d' ' -f1)" = "$AGENT_MD5"  || { echo "AGENT MD5 MISMATCH — ABORT"; exit 1; }
test "$(md5sum "$A/prompt.py" | cut -d' ' -f1)" = "$PROMPT_MD5" || { echo "PROMPT MD5 MISMATCH — ABORT"; exit 1; }
test "$(sed -n '1161,1185p' "$A/agent.py" | md5sum | cut -d' ' -f1)" = "$TTS_SPAN_MD5" || { echo "TTS SPAN CHANGED — VOICE LAW VIOLATION — ABORT"; exit 1; }

echo "[restore] py_compile ..."
/opt/capsy-agent/.venv/bin/python -m py_compile "$A/agent.py" "$A/prompt.py"

echo "[restore] daemon-reload + restart ..."
systemctl daemon-reload
systemctl reset-failed famit-agent || true
systemctl restart famit-agent
sleep 2
echo "[restore] service state: $(systemctl is-active famit-agent)  NRestarts=$(systemctl show famit-agent -p NRestarts --value)"
echo "[restore] DONE — golden brain restored. Founder: make one real call to confirm."
