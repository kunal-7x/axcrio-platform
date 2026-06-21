#!/bin/bash
VENV=/opt/capsy-agent/.venv/bin/python
cd /opt/famit-agent
set -a; . /opt/famit-agent/.env 2>/dev/null; set +a
export EARNER_POOL_LLM=1
$VENV - <<'PY'
import sys, time
sys.path.insert(0,'/opt/famit-agent')
from llm_router import GROQ_POOL
picked = GROQ_POOL.pick()
kval = picked['key'] if isinstance(picked,dict) else getattr(picked,'key',picked)
print("POOL_AVAILABLE_COUNT", GROQ_POOL.available_count(), "KEY_PREFIX", str(kval)[:8]+"...")

# openai SDK is installed (livekit.plugins.openai) -> point it at Groq, real 200
from openai import OpenAI
c = OpenAI(api_key=kval, base_url="https://api.groq.com/openai/v1")
t=time.time()
try:
    r = c.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{"role":"user","content":"say OK"}],
        max_completion_tokens=5, temperature=0.3)
    print("GROQ_LIVE_STATUS=200 elapsed_ms", round((time.time()-t)*1000,1),
          "content=", repr(r.choices[0].message.content))
except Exception as e:
    print("GROQ_LIVE_ERR", type(e).__name__, str(e)[:250])
PY
