#!/bin/bash
VENV=/opt/capsy-agent/.venv/bin/python
echo "=== 1) service ==="
systemctl is-active famit-agent
systemctl show famit-agent -p MainPID -p NRestarts -p ActiveState -p SubState

echo "=== 2) md5s ==="
echo -n "agent.py: "; md5sum /opt/famit-agent/agent.py | awk '{print $1}'
echo -n "prompt.py: "; md5sum /opt/famit-agent/prompt.py | awk '{print $1}'
echo "(expect agent bdf89031..., prompt b99c25ea... UNTOUCHED)"

echo "=== 3) VOICE LAW: elevenlabs.TTS span ==="
# extract the elevenlabs.TTS(...) constructor span and md5 it (robust to line-number shift)
$VENV - <<'PY'
import re,hashlib
src=open('/opt/famit-agent/agent.py').read()
i=src.find('elevenlabs.TTS(')
assert i>=0,"no elevenlabs.TTS("
# balance parens from the '('
j=src.index('(',i)
depth=0;k=j
while k<len(src):
    if src[k]=='(':depth+=1
    elif src[k]==')':
        depth-=1
        if depth==0:break
    k+=1
span=src[i:k+1]
print("TTS_SPAN_MD5", hashlib.md5(span.encode()).hexdigest())
print("TTS_SPAN_LEN", len(span))
PY
echo "GOLDEN TTS span content md5 should equal what golden produces (compare below)"

echo "=== 3b) golden backup TTS span (same extractor) for byte-identity ==="
GOLDEN=$(ls -t /opt/famit-agent/agent.py.PREROT.* 2>/dev/null | head -1)
echo "golden backup: $GOLDEN md5=$(md5sum $GOLDEN | awk '{print $1}')"
$VENV - "$GOLDEN" <<'PY'
import sys,hashlib
src=open(sys.argv[1]).read()
i=src.find('elevenlabs.TTS(')
j=src.index('(',i);depth=0;k=j
while k<len(src):
    if src[k]=='(':depth+=1
    elif src[k]==')':
        depth-=1
        if depth==0:break
    k+=1
span=src[i:k+1]
print("GOLDEN_TTS_SPAN_MD5", hashlib.md5(span.encode()).hexdigest())
PY

echo "=== 4) EL_STABILITY / voice_id in .env ==="
grep -E 'EL_STABILITY|VOICE_ID|ELEVEN.*VOICE' /opt/famit-agent/.env | sed 's/=.*VOICE/=<voice>/' 2>/dev/null
grep -E 'EL_STABILITY' /opt/famit-agent/.env

echo "=== 5) forbidden tokens (must be empty except max_completion_tokens once) ==="
grep -nE 'frequency_penalty|presence_penalty|extra_body|FREQ_PENALTY|PRES_PENALTY' /opt/famit-agent/agent.py || echo "NO penalty/extra_body tokens (GOOD)"
echo "--- literal 220 ---"
grep -n '220' /opt/famit-agent/agent.py || echo "no 220 (GOOD)"
echo "--- max_completion_tokens occurrences ---"
grep -cn 'max_completion_tokens' /opt/famit-agent/agent.py

echo "=== 6) recent logs (errors / rotation wiring) ==="
journalctl -u famit-agent --no-pager -n 40 | grep -iE 'error|traceback|exception|EARNER_POOL|GROQ_POOL|pool|rotat|registered|worker' || echo "(no matching lines)"
echo "--- error count last 60 lines ---"
journalctl -u famit-agent --no-pager -n 60 | grep -icE 'error|traceback|exception'
