#!/bin/bash
cd /opt/famit-agent || exit 9
echo "=== 1) service state ==="
systemctl is-active famit-agent
PID=$(systemctl show -p MainPID --value famit-agent)
echo "MainPID=$PID"
echo "NRestarts=$(systemctl show -p NRestarts --value famit-agent)"
echo "=== 2) md5 (agent ee3e4b5e=patched-R6 ; prompt 759b6f5c=R6) ==="
md5sum agent.py prompt.py
echo "=== 3) running-process env (from /proc/PID/environ) ==="
tr '\0' '\n' < /proc/$PID/environ 2>/dev/null | grep -E '^GROQ_MAX_TOKENS=|^GROQ_FREQ_PENALTY=|^GROQ_PRES_PENALTY=|^KERNEL_OUTBOUND=|^EL_STABILITY=|^ELEVENLABS_VOICE_ID=' | sort
echo "=== 4) worker re-registered as capsy (since restart) ==="
journalctl -u famit-agent --since "-3 min" --no-pager 2>/dev/null | grep -iE 'registered worker|agent_name.*capsy|capsy' | tail -3
echo "=== 5) FINAL-FIX penalty log line (fires per call, may be empty until a call) ==="
journalctl -u famit-agent --since "-3 min" --no-pager 2>/dev/null | grep -iE 'FINAL-FIX|repetition penalty' | tail -3
echo "(note: this line is INSIDE the per-call entrypoint -> appears on the first real call, not at boot)"
echo "=== 6) ERROR/garbage scan on new PID window (expect NONE) ==="
journalctl -u famit-agent --since "-3 min" --no-pager 2>/dev/null | grep -iE 'Traceback|ValueError|TypeError|unexpected keyword|## Step|kwargs|dealloc|CRITICAL|ERROR' | grep -v 'shutdown\|teardown\|ack-kill\|exit 255' | tail -20
echo "(empty above = clean)"
echo "=== 7) last 12 journal lines (level sanity) ==="
journalctl -u famit-agent --since "-3 min" --no-pager 2>/dev/null | tail -12
