#!/bin/bash
VENV=/opt/capsy-agent/.venv/bin/python

echo "=== settle re-check (10s) ==="
P1=$(systemctl show famit-agent -p MainPID --value); sleep 10
P2=$(systemctl show famit-agent -p MainPID --value)
echo "pid1=$P1 pid2=$P2 active=$(systemctl is-active famit-agent) nrestarts=$(systemctl show famit-agent -p NRestarts --value)"

echo "=== any 255/error from the NEW pid since deploy? ==="
NEWPID=$(systemctl show famit-agent -p MainPID --value)
journalctl -u famit-agent --no-pager --since "-3min" | grep -iE 'error|traceback|exception' | grep -v "pid\": 582" | grep -vE 'python\[582' || echo "(no NEW-pid errors since deploy)"

echo "=== live Groq 200 via a pool key (uses agent.py's own GROQ_POOL) ==="
cd /opt/famit-agent
set -a; . /opt/famit-agent/.env 2>/dev/null; set +a
export EARNER_POOL_LLM=1
$VENV - <<'PY'
import os, sys, time
sys.path.insert(0,'/opt/famit-agent')
# Use the pool the agent uses
try:
    from llm_router import GROQ_POOL
    n = GROQ_POOL.available_count()
    print("POOL_AVAILABLE_COUNT", n)
    key = GROQ_POOL.pick()
    # pick() may return a key string or an obj; normalize
    kval = getattr(key,'key',key)
    print("POOL_PICKED_KEY", str(kval)[:10]+"...")
except Exception as e:
    print("POOL_IMPORT_OR_PICK_FAIL", repr(e)); kval=None

import urllib.request, json
if kval:
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps({
            "model":"meta-llama/llama-4-scout-17b-16e-instruct",
            "messages":[{"role":"user","content":"say OK"}],
            "max_completion_tokens":5,"temperature":0.3
        }).encode(),
        headers={"Authorization":f"Bearer {kval}","Content-Type":"application/json"})
    t=time.time()
    try:
        r=urllib.request.urlopen(req,timeout=30)
        print("GROQ_HTTP_STATUS", r.status, "elapsed_ms", round((time.time()-t)*1000,1))
    except urllib.error.HTTPError as e:
        print("GROQ_HTTP_STATUS", e.code, "body", e.read()[:200])
PY
