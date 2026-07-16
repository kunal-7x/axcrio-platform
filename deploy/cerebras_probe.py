#!/usr/bin/env python3
"""Cerebras gpt-oss-120b probe — runs INSIDE the worker container (has CEREBRAS_API_KEY + the brain + libs).
Isolates WHY the agent times out on Cerebras while the playground (0.10s) flies. Measures TTFT (time to
first CONTENT token = the real voice latency) for 5 variants:
  A) tiny prompt + reasoning=low      (should match the playground ~0.1s)
  B) FULL brain  + reasoning=low      (agent CONTENT, raw API)   -> if fast, raw API is fine
  C) FULL brain  + NO reasoning param (default effort)            -> if slow, default reasoning is the killer
  D) FULL brain  + reasoning=medium
  E) via the livekit OpenAI plugin + extra_body reasoning=low (the EXACT agent path)
Diagnosis: A&B fast but E slow => plugin isn't sending reasoning_effort -> code fix.
           B slow but A fast    => big brain prompt + reasoning is the cost.
           all slow             => free-tier throttle / network.
"""
import os, json, time, asyncio
import httpx

KEY  = os.environ.get("CEREBRAS_API_KEY", "")
BASE = os.environ.get("CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1").rstrip("/")
MODEL = os.environ.get("CEREBRAS_LLM_MODEL", "gpt-oss-120b")
try:
    BRAIN = json.load(open("/data/campaigns/df58b5341f.json"))["fields"].get("brain_override", "") or ""
except Exception:
    BRAIN = "You are Riya, a warm real-estate sales agent. Reply in 1-2 short Hinglish lines + a follow-up question."
USERQ = "85 लाख का 2 BHK, 20% down payment, baaki 8.5% pe 20 saal loan — monthly EMI approx kitni aayegi?"

if not KEY:
    print("!! CEREBRAS_API_KEY missing in container env"); raise SystemExit(1)
print(f"=== Cerebras probe ===  model={MODEL}  base={BASE}  brain_chars={len(BRAIN)}\n")

def raw(system, reasoning, label):
    body = {"model": MODEL, "stream": True, "max_completion_tokens": 190, "temperature": 0.3,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": USERQ}]}
    if reasoning is not None:
        body["reasoning_effort"] = reasoning
    t0 = time.time(); ttft = None; n = 0
    try:
        with httpx.stream("POST", BASE + "/chat/completions",
                          headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
                          json=body, timeout=30) as r:
            if r.status_code != 200:
                print(f"[{label}] HTTP {r.status_code}: {r.read()[:160].decode('utf-8','ignore')}"); return
            for line in r.iter_lines():
                if not line or not line.startswith("data:"): continue
                d = line[5:].strip()
                if d == "[DONE]": break
                try: j = json.loads(d)
                except Exception: continue
                c = (j.get("choices") or [{}])[0].get("delta", {}).get("content")
                if c:
                    if ttft is None: ttft = time.time() - t0
                    n += 1
        total = time.time() - t0
        print(f"[{label}] TTFT={ttft*1000:.0f}ms total={total*1000:.0f}ms content_chunks={n}" if ttft
              else f"[{label}] NO CONTENT in {total*1000:.0f}ms")
    except Exception as e:
        print(f"[{label}] ERR {type(e).__name__}: {str(e)[:140]}")

raw("You are a helpful assistant. Reply in 1-2 short lines.", "low", "A tiny+low (playground-like)")
raw(BRAIN, "low", "B FULLbrain+low")
raw(BRAIN, None, "C FULLbrain+default")
raw(BRAIN, "medium", "D FULLbrain+medium")

async def plugin():
    try:
        from livekit.plugins import openai as lko
        from livekit.agents import llm as L
        llm = lko.LLM(model=MODEL, api_key=KEY, base_url=BASE, temperature=0.3,
                      max_completion_tokens=190, extra_body={"reasoning_effort": "low"})
        cc = L.ChatContext.empty(); cc.add_message(role="system", content=BRAIN); cc.add_message(role="user", content=USERQ)
        t0 = time.time(); ttft = None; n = 0
        st = llm.chat(chat_ctx=cc)
        async for ev in st:
            c = None
            try:
                dl = getattr(ev, "delta", None); c = getattr(dl, "content", None) if dl else None
            except Exception: pass
            if c:
                if ttft is None: ttft = time.time() - t0
                n += 1
        try: await st.aclose()
        except Exception: pass
        print(f"[E livekit-plugin+low (EXACT agent path)] TTFT={ttft*1000:.0f}ms chunks={n}" if ttft else "[E livekit-plugin] NO CONTENT")
    except Exception as e:
        print(f"[E livekit-plugin] ERR {type(e).__name__}: {str(e)[:200]}")
asyncio.run(plugin())
