#!/bin/bash
VENV=/opt/capsy-agent/.venv/bin/python
cd /opt/famit-agent
set -a; . /opt/famit-agent/.env 2>/dev/null; set +a
export EARNER_POOL_LLM=1
$VENV - <<'PY'
import sys, time, json
sys.path.insert(0,'/opt/famit-agent')
from llm_router import GROQ_POOL
print("POOL_AVAILABLE_COUNT", GROQ_POOL.available_count())
picked = GROQ_POOL.pick()
print("PICK_TYPE", type(picked).__name__, "REPR", str(picked)[:120])

# Extract the actual secret key value from whatever pick() returns
def extract_key(p):
    if isinstance(p, str): return p
    if isinstance(p, dict):
        for f in ("key","api_key","secret","value","apiKey"):
            if p.get(f): return p[f]
    for f in ("key","api_key","secret","value"):
        v=getattr(p,f,None)
        if v: return v
    return None
kval = extract_key(picked)
print("KEY_PREFIX", (str(kval)[:8]+"...") if kval else "NONE")

# Use the groq SDK (same client lib the agent uses) -> real 200, no Cloudflare UA block
from groq import Groq
c = Groq(api_key=kval)
t=time.time()
try:
    r = c.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{"role":"user","content":"say OK"}],
        max_completion_tokens=5, temperature=0.3)
    print("GROQ_SDK_OK status=200 elapsed_ms", round((time.time()-t)*1000,1),
          "content=", repr(r.choices[0].message.content))
except Exception as e:
    print("GROQ_SDK_ERR", type(e).__name__, str(e)[:200])
PY
