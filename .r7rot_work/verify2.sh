#!/bin/bash
set +e
PY=/opt/capsy-agent/.venv/bin/python
SRC=/opt/famit-agent
WORK=/tmp/rotverify
cd "$WORK"

# Load .env robustly: only export clean KEY=VALUE lines (skip the line-101 prose).
load_env() {
  while IFS= read -r line; do
    case "$line" in
      \#*|"") continue;;
      *=*) k="${line%%=*}";
           case "$k" in [A-Za-z_]*) export "$line" 2>/dev/null;; esac;;
    esac
  done < "$SRC/.env"
}

echo "===== TEST 3 (clean): GROQ_POOL.available_count() ====="
load_env
PYTHONPATH="$SRC" "$PY" -c "
from llm_router import GROQ_POOL
import os
env_keys = sorted([k for k in os.environ if k=='GROQ_API_KEY' or (k.startswith('GROQ_API_KEY_') and k[len('GROQ_API_KEY_'):].isdigit())])
print('   .env GROQ key VARS present:', len(env_keys), env_keys)
# distinct non-empty secret values
vals = set()
for k in env_keys:
    v=(os.environ.get(k) or '').strip()
    if v: vals.add(v)
print('   distinct non-empty key VALUES:', len(vals))
GROQ_POOL.pick()
ac = GROQ_POOL.available_count()
print('   GROQ_POOL.available_count() =', ac)
# pool total entries
try:
    print('   pool total entries (_keys):', len(GROQ_POOL._keys))
except Exception as e:
    print('   _keys introspection:', e)
ok = ac >= 13
print('T3', 'PASS' if ok else 'FAIL', '(>=13 healthy keys available)')
"

echo
echo "===== TEST 4 (real ChatContext): 429 -> instant re-pick ====="
load_env
EARNER_POOL_LLM=1 PYTHONPATH="$WORK:$SRC" "$PY" - <<'PYEOF'
import asyncio, time, importlib.util, sys
spec = importlib.util.spec_from_file_location('agent','/tmp/rotverify/agent.py')
m = importlib.util.module_from_spec(spec); sys.modules['agent']=m
spec.loader.exec_module(m)
from livekit.agents.llm import ChatContext

pool = m._GROQ_POOL
assert pool is not None

class _FakeChunk: pass
class _FakeStream:
    def __init__(self): self._done=False
    async def __aenter__(self): return self
    async def __aexit__(self,*a): return False
    def __aiter__(self): return self
    async def __anext__(self):
        if not self._done:
            self._done=True; return _FakeChunk()
        raise StopAsyncIteration
class _Fake429(Exception):
    def __init__(self):
        super().__init__("Error code: 429 - rate_limit_exceeded")
        self.status_code=429
        class R: status_code=429; headers={}
        self.response=R()
class _FakeClient:
    def __init__(self): self.api_key=None
class _FakeDelegate:
    def __init__(self):
        self._client=_FakeClient(); self.used=[]; self.first_key=None
    def chat(self,*,chat_ctx,tools,conn_options,**extra):
        key=self._client.api_key; self.used.append(key)
        if self.first_key is None: self.first_key=key
        if key==self.first_key: raise _Fake429()
        return _FakeStream()

assert m._pool_is_429(_Fake429()) is True, "is_429 failed to recognize 429"

delegate=_FakeDelegate()
sticky=m._make_sticky_pool_llm(delegate)
assert sticky is not None
print('   sticky initial key:', (sticky.sticky_key or '')[:10],'...')

ctx=ChatContext.empty()
async def run():
    t0=time.perf_counter()
    stream=sticky.chat(chat_ctx=ctx, tools=None)
    chunks=0
    async with stream:
        async for c in stream: chunks+=1
    return (time.perf_counter()-t0)*1000.0, chunks

dt,chunks=asyncio.new_event_loop().run_until_complete(run())
print('   keys tried this turn:', [ (k or '')[:10]+'..' for k in delegate.used ])
print('   chunks after fallback:', chunks)
print('   elapsed: %.3f ms' % dt)
repicked = len(delegate.used)>=2 and delegate.used[0]!=delegate.used[1]
no_backoff = dt < 250.0
ok = repicked and chunks>0 and no_backoff
print('   re-picked DIFFERENT key:', repicked)
print('   no surfaced 429 (got chunks):', chunks>0)
print('   no backoff sleep (<250ms):', no_backoff)
print('T4', 'PASS' if ok else 'FAIL')
PYEOF
echo
echo "===== DONE ====="
