"""Runtime proof that FallbackAdapter fails over from a BAD (401/429-like) primary
key to a HEALTHY fallback key with NO surfaced error and a real completion.

Primary = a deliberately invalid Groq key -> Groq returns 401 invalid_api_key
(an APIStatusError, same failover class the adapter uses for 429). The adapter
must transparently move to the healthy real key (order[1]) and return text.
"""
import asyncio, os, sys
import livekit.agents as agents
from livekit.plugins import groq
from livekit.agents.llm import ChatContext

REAL = (os.getenv("GROQ_API_KEY") or "").strip()
assert REAL.startswith("gsk_"), "need a real key in env"
MODEL = os.getenv("GROQ_LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

def mk(k):
    return groq.LLM(model=MODEL, api_key=k, temperature=0.3, max_completion_tokens=90)

async def collect(llm):
    ctx = ChatContext.empty()
    ctx.add_message(role="user", content="Say the single word OK.")
    out = ""
    async with llm.chat(chat_ctx=ctx) as stream:
        async for ev in stream:
            d = getattr(ev, "delta", None)
            if d is not None and getattr(d, "content", None):
                out += d.content
    return out.strip()

async def main():
    # BAD primary, REAL fallback -> adapter must fail over to REAL and succeed.
    bad = "gsk_INVALID000000000000000000000000000000000000000000"
    adapter = agents.llm.FallbackAdapter([mk(bad), mk(REAL)])
    try:
        txt = await collect(adapter)
        print("FALLBACK_OK got=%r" % txt[:60])
        assert txt, "fallback returned empty"
        print("G4_RUNTIME_FALLBACK: PASS (bad primary -> healthy fallback, no surfaced error)")
    except Exception as e:
        print("G4_RUNTIME_FALLBACK: FAIL %r" % e)
        sys.exit(1)

    # Sanity: a healthy primary alone returns text (sticky path works).
    try:
        txt2 = await collect(agents.llm.FallbackAdapter([mk(REAL), mk(REAL)]))
        assert txt2
        print("STICKY_PRIMARY: PASS (healthy primary returns; no failover needed)")
    except Exception as e:
        print("STICKY_PRIMARY: FAIL %r" % e); sys.exit(1)
    print("ALL_FB_RUNTIME_PASS")

asyncio.run(main())
