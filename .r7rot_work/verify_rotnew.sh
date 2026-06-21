#!/bin/bash
# Offline verification of agent.py.ROTNEW — NO deploy, NO restart.
set +e
PY=/opt/capsy-agent/.venv/bin/python
SRC=/opt/famit-agent
ROT=/tmp/agent.py.ROTNEW
WORK=/tmp/rotverify
rm -rf "$WORK"; mkdir -p "$WORK"
# Stage ROTNEW as agent.py in an isolated dir that symlinks the box's real modules,
# so imports (prompt, memory, llm_router, .env) resolve exactly like the live box.
cp "$ROT" "$WORK/agent.py"
for m in prompt.py memory.py memory llm_router .env; do
  [ -e "$SRC/$m" ] && ln -s "$SRC/$m" "$WORK/$m" 2>/dev/null
done
cd "$WORK"

echo "===== TEST 1: py_compile ====="
"$PY" -m py_compile "$WORK/agent.py" && echo "T1 PASS py_compile OK" || echo "T1 FAIL py_compile"

echo
echo "===== TEST 2: python -c import agent (EARNER_POOL_LLM=1) ====="
# Load .env so all GROQ keys + PROVIDER_KEYSTORE_SECRET are present for the import-time pool wiring.
set -a; [ -f "$SRC/.env" ] && . "$SRC/.env"; set +a
EARNER_POOL_LLM=1 PYTHONPATH="$WORK:$SRC" "$PY" -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('agent', '$WORK/agent.py')
m = importlib.util.module_from_spec(spec)
sys.modules['agent'] = m
spec.loader.exec_module(m)
print('T2 PASS import OK; EARNER_POOL_LLM =', m.EARNER_POOL_LLM)
print('   _GROQ_POOL is', 'WIRED' if m._GROQ_POOL is not None else 'None')
print('   _make_sticky_pool_llm present:', hasattr(m, '_make_sticky_pool_llm'))
" || echo "T2 FAIL import"

echo
echo "===== TEST 3: GROQ_POOL.available_count() sees all keys ====="
set -a; [ -f "$SRC/.env" ] && . "$SRC/.env"; set +a
PYTHONPATH="$SRC" "$PY" -c "
from llm_router import GROQ_POOL
import os
env_keys = [k for k in os.environ if k=='GROQ_API_KEY' or (k.startswith('GROQ_API_KEY_') and k[len('GROQ_API_KEY_'):].isdigit())]
print('   .env GROQ key vars present:', len(env_keys))
# force a refresh by picking once (pool re-reads env+store on pick)
try:
    GROQ_POOL.pick()
except Exception as e:
    print('   pick warn:', e)
print('   GROQ_POOL.available_count() =', GROQ_POOL.available_count())
ok = GROQ_POOL.available_count() >= len(env_keys) and len(env_keys) >= 13
print('T3', 'PASS' if ok else 'FAIL', 'pool sees env(+store) keys')
" || echo "T3 FAIL pool count"

echo
echo "===== TEST 4: simulate 429 -> INSTANT re-pick of a DIFFERENT healthy key (<20ms, no backoff) ====="
set -a; [ -f "$SRC/.env" ] && . "$SRC/.env"; set +a
EARNER_POOL_LLM=1 PYTHONPATH="$WORK:$SRC" "$PY" - <<'PYEOF'
import asyncio, time, importlib.util, sys, os
spec = importlib.util.spec_from_file_location('agent','/tmp/rotverify/agent.py')
m = importlib.util.module_from_spec(spec); sys.modules['agent']=m
spec.loader.exec_module(m)

pool = m._GROQ_POOL
assert pool is not None, "pool not wired"
n0 = pool.available_count()
print('   available before:', n0)

# Build a FAKE delegate whose .chat() raises a 429 on the first key it's asked to use,
# then succeeds on any OTHER key. We capture which keys were used + timing.
import llm_router.provider_pool as pp

class _FakeChunk:
    pass

class _FakeStream:
    def __init__(self, parent): self.parent=parent
    async def __aenter__(self): return self
    async def __aexit__(self,*a): return False
    def __aiter__(self): return self
    async def __anext__(self):
        # one chunk then stop
        if not getattr(self,'_done',False):
            self._done=True
            return _FakeChunk()
        raise StopAsyncIteration

class _Fake429(Exception):
    def __init__(self):
        super().__init__("429 Too Many Requests")
        self.status_code = 429
        # mimic an openai/groq APIStatusError enough for is_429
        class R: status_code=429; headers={}
        self.response = R()

class _FakeClient:
    def __init__(self): self.api_key=None

class _FakeDelegate:
    def __init__(self):
        self._client=_FakeClient()
        self.used=[]
        self.first_key=None
    def chat(self, *, chat_ctx, tools, conn_options, **extra):
        key = self._client.api_key
        self.used.append(key)
        if self.first_key is None:
            self.first_key = key
        if key == self.first_key:
            raise _Fake429()        # the originally-picked sticky key is rate-limited
        return _FakeStream(self)    # any other key works

# monkeypatch is_429 path is already real (m._pool_is_429). Confirm it flags our fake.
assert m._pool_is_429(_Fake429()) is True, "is_429 did not recognize fake 429"

delegate=_FakeDelegate()
sticky = m._make_sticky_pool_llm(delegate)
assert sticky is not None, "sticky wrap returned None"
print('   sticky initial key:', (sticky.sticky_key or '')[:8], '...')

# Drive ONE chat turn through the sticky stream and time it.
class _Ctx: pass
async def run():
    t0=time.perf_counter()
    stream = sticky.chat(chat_ctx=_Ctx(), tools=None)
    chunks=0
    async with stream:
        async for c in stream:
            chunks+=1
    dt=(time.perf_counter()-t0)*1000.0
    return dt, chunks

dt, chunks = asyncio.get_event_loop().run_until_complete(run())
print('   keys tried this turn:', [ (k or '')[:8]+'..' for k in delegate.used ])
print('   chunks delivered after fallback:', chunks)
print('   elapsed: %.2f ms' % dt)

repicked_different = (len(delegate.used) >= 2 and delegate.used[0] != delegate.used[1])
no_backoff_sleep = dt < 250.0   # a real backoff sleep would be >=1s; instant re-pick is sub-ms
surfaced_429 = False  # we got chunks, so no 429 surfaced
ok = repicked_different and chunks>0 and no_backoff_sleep
print('   re-picked a DIFFERENT key:', repicked_different)
print('   no surfaced 429 (got chunks):', chunks>0)
print('   no backoff sleep (<250ms):', no_backoff_sleep)
print('T4', 'PASS' if ok else 'FAIL', 'instant 429 fallback to a healthy key')
PYEOF
[ $? -ne 0 ] && echo "T4 FAIL (exception)"

echo
echo "===== DONE ====="
