#!/usr/bin/env bash
set -eu
TS=$(date +%Y%m%d-%H%M%S)
cd /opt/famit-agent
echo "=== PRE: live md5s ==="
md5sum agent.py prompt.py
echo "=== BACKUP agent.py + .env ==="
cp -a agent.py "agent.py.GROQFIXbak.${TS}"
cp -a .env ".env.GROQFIXbak.${TS}"
echo "BACKUP_AGENT agent.py.GROQFIXbak.${TS}"
echo "BACKUP_ENV .env.GROQFIXbak.${TS}"
# capture TTS span md5 of the CURRENT live file (before)
PY=/opt/capsy-agent/.venv/bin/python
"$PY" - <<'PYEOF'
import hashlib
s=open('/opt/famit-agent/agent.py',encoding='utf-8').read()
a=s.index('tts = elevenlabs.TTS('); b=s.index('ctl["tts"] = tts')
print("TTS_SPAN_MD5_BEFORE", hashlib.md5(s[a:b].encode()).hexdigest())
PYEOF
echo "=== DEPLOY candidate -> agent.py ==="
cp /tmp/agent_candidate.py /opt/famit-agent/agent.py
echo "=== POST: new md5 ==="
md5sum agent.py
"$PY" - <<'PYEOF'
import hashlib
s=open('/opt/famit-agent/agent.py',encoding='utf-8').read()
a=s.index('tts = elevenlabs.TTS('); b=s.index('ctl["tts"] = tts')
print("TTS_SPAN_MD5_AFTER", hashlib.md5(s[a:b].encode()).hexdigest())
PYEOF
echo "=== py_compile deployed ==="
"$PY" -m py_compile /opt/famit-agent/agent.py && echo DEPLOYED_COMPILE_OK
echo "=== restart famit-agent ==="
sudo systemctl restart famit-agent
sleep 3
echo "=== status ==="
systemctl is-active famit-agent
echo "NRestarts=$(systemctl show famit-agent -p NRestarts --value)"
echo "=== recent journal (errors?) ==="
journalctl -u famit-agent --since '30 seconds ago' --no-pager | tail -25
