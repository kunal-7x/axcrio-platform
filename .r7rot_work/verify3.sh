#!/bin/bash
set +e
PY=/opt/capsy-agent/.venv/bin/python
SRC=/opt/famit-agent
WORK=/tmp/rotverify
cd "$WORK"
load_env() {
  while IFS= read -r line; do
    case "$line" in
      \#*|"") continue;;
      *=*) k="${line%%=*}"; case "$k" in [A-Za-z_]*) export "$line" 2>/dev/null;; esac;;
    esac
  done < "$SRC/.env"
}
echo "===== TEST 4 (real ChatChunk): 429 -> instant re-pick of a DIFFERENT healthy key ====="
load_env
EARNER_POOL_LLM=1 PYTHONPATH="$WORK:$SRC" "$PY" - <<'PYEOF'
import asyncio, time, importlib.util, sys
spec = importlib.util.spec_from_file_location('agent','/tmp/rotverify/agent.py')
m = importlib.util.module_from_spec(spec); sys.modules['agent']=m
spec.loader.exec_module(m)
from livekit.agents.llm import ChatContext, ChatChunk

pool=m._GROQ_POOL; assert pool is not None
_seq=[0]
class _FakeStream:
    def __init__(self): self._done=False
    async def __aenter__(self): return self
    async def __aexit__(self,*a): return False
    def __aiter__(self): return self
    async def __anext__(self):
        if not self._done:
            self._done=True
            _seq[0]+=1
            return ChatChunk(id="c%d"%_seq[0])
        raise StopAsyncIteration
class _Fake429(Exception):
    def __init__(self):
        super().__init__("Error code: 429 - rate_limit_exceeded: tokens per day")
        self.status_code=429
        class R: status_code=429; headers={}
        self.response=R()
class _FakeClient:
    def __init__(self): self.api_key=None
class _FakeDelegate:
    def __init__(self): self._client=_FakeClient(); self.used=[]; self.first_key=None
    def chat(self,*,chat_ctx,tools,conn_options,**extra):
        key=self._client.api_key; self.used.append(key)
        if self.first_key is None: self.first_key=key
        if key==self.first_key: raise _Fake429()   # sticky key is exhausted
        return _FakeStream()                        # fresh key works

assert m._pool_is_429(_Fake429()) is True

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
u=[ (k or '')[:10]+'..' for k in delegate.used ]
print('   keys tried this turn:', u)
print('   chunks delivered after fallback:', chunks)
print('   elapsed: %.3f ms' % dt)
repicked = len(delegate.used)>=2 and delegate.used[0]!=delegate.used[1]
no_backoff = dt < 250.0
print('   re-picked a DIFFERENT key:', repicked)
print('   no surfaced 429 (got chunks):', chunks>0)
print('   no backoff sleep (<250ms):', no_backoff)
print('T4', 'PASS' if (repicked and chunks>0 and no_backoff) else 'FAIL')
PYEOF
echo "===== DONE ====="
