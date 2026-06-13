#!/usr/bin/env python3
"""MLV integrated mirror smoke — drives the REAL deployed _build_sales_instructions through the
REAL Groq LLM (same model the live inbound turn-loop uses). Asserts the reply language MIRRORS the
caller, including a mid-call Hindi->English switch (the exact bug). NO LiveKit room, NO real call,
NO STT/TTS — pure LLM-chain assertion. Run in /opt/capsy-agent/.venv on the box."""
import os, sys, re, importlib.util, json, time
import urllib.request, urllib.error

ENV = "/opt/famit-agent/.env"
SRC = "/opt/famit-agent/aim_voice_agent.py"

# --- load .env (GROQ key + model) ---
env = {}
for line in open(ENV, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
MODEL = env.get("GROQ_LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
# gather every GROQ key the live round-robin uses (GROQ_API_KEY + _2.._N)
KEYS = [env[k] for k in env if re.match(r"GROQ_API_KEY(_\d+)?$", k) and env[k]]
assert KEYS, "no GROQ keys"

# --- import the REAL deployed module to get the REAL instruction builder ---
spec = importlib.util.spec_from_file_location("aim_live", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
build = mod._build_sales_instructions

fields = {"company_name": "Famit", "agent_name": "Riya",
          "project_name": "Skyline Residency", "offer": "2BHK flats"}
SYS = build(fields, recap="", caller_name="", is_returning=False,
            pending_disambig=False, campaign_options=None, grounding="")
print("SYSTEM PROMPT len:", len(SYS))

def groq(messages):
    body = json.dumps({"model": MODEL, "messages": messages, "temperature": 0.5,
                       "max_tokens": 120}).encode()
    last = None
    for key in KEYS:                       # rotate keys exactly like the live round-robin
        req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions",
            data=body, headers={"Authorization": f"Bearer {key}",
                                "Content-Type": "application/json",
                                "User-Agent": "famit-mlv-smoke/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (401, 403, 429):  # exhausted/forbidden key -> try next
                continue
            raise
    raise SystemExit(f"all GROQ keys failed; last={last}")

DEV = re.compile(r"[ऀ-ॿ]")          # Devanagari
# romanized-Hindi markers (a reply in roman script that is actually Hindi, not English)
HINDI_ROMAN = re.compile(r"\b(haan|nahi|ji|aap|aapka|aapke|aapko|hai|hain|kya|kaise|"
    r"karoon|karen|karenge|baare|mein|ke|ki|ka|se|hum|hamare|hamari|mujhe|bataiye|"
    r"boliye|swagat|shuru|hoti|hota|abhi|theek|achha|lakh|rupaye|kar|raha|rahi|"
    r"sakti|sakte|chahiye|namaste|shukriya|dhanyavaad)\b", re.I)
def lang_of(t):
    dev = len(DEV.findall(t))
    latin = len(re.findall(r"[A-Za-z]", t))
    if dev >= 3 and dev >= latin * 0.10:
        return "hi"                       # real Devanagari Hindi
    roman_hi = len(HINDI_ROMAN.findall(t))
    words = max(1, len(re.findall(r"[A-Za-z]+", t)))
    if roman_hi >= 2 and roman_hi / words >= 0.12:
        return "hi"                       # romanized Hindi / Hinglish
    return "en"

def announces_lang(t):
    return bool(re.search(r"\b(language|English|Hindi|Hinglish|switch(ing)? to|भाषा|अंग्रेज़ी|हिंदी)\b",
                          t, re.I))

N = 2  # samples per scenario (LLM is stochastic; majority must mirror)

def scenario(name, messages, want):
    samples = [groq(messages) for _ in range(N)]
    langs = [lang_of(s) for s in samples]
    ok = sum(1 for l in langs if l == want) >= (N + 1) // 2  # majority mirrors
    return name, ok, samples, langs

SC = [
  ("1 Hindi turn -> Hindi reply", [{"role":"system","content":SYS},
     {"role":"user","content":"Haan ji, mujhe aapke 2BHK flat ke baare mein jaanna hai. Price kya hai?"}], "hi"),
  ("2 English turn -> English reply", [{"role":"system","content":SYS},
     {"role":"user","content":"Hi, can you tell me about the 2BHK flats and the current price?"}], "en"),
  ("3 mid-call Hindi->English switch -> English reply (the bug)", [{"role":"system","content":SYS},
     {"role":"user","content":"Haan ji namaste, 2BHK ke baare mein bataiye."},
     {"role":"assistant","content":"Namaste! Bilkul, hamare 2BHK flats Skyline Residency mein hain. Aap kis area mein dekh rahe hain?"},
     {"role":"user","content":"Actually let's continue in English. What is the price and is financing available?"}], "en"),
  # 2b: the REAL live shape — the NEUTRAL greeting is the assistant's first turn, then the caller
  # opens in English. This is exactly what the founder experiences on a real inbound call.
  ("2b LIVE shape: neutral greeting said, caller opens ENGLISH -> English reply",
     [{"role":"system","content":SYS},
      {"role":"assistant","content":"Namaste, this is Riya from Famit. Thanks for calling — how can I help you today?"},
      {"role":"user","content":"Hi, can you tell me about the 2BHK flats and the current price?"}], "en"),
  # 2c: same neutral greeting, but caller opens in HINDI -> reply must be Hindi (no English regression)
  ("2c LIVE shape: neutral greeting said, caller opens HINDI -> Hindi reply",
     [{"role":"system","content":SYS},
      {"role":"assistant","content":"Namaste, this is Riya from Famit. Thanks for calling — how can I help you today?"},
      {"role":"user","content":"Haan ji, 2BHK flat ki price aur location ke baare mein bataiye na."}], "hi"),
]

results = []
all_replies = []
for name, msgs, want in SC:
    nm, ok, samples, langs = scenario(name, msgs, want)
    all_replies += samples
    results.append((nm, ok, samples[0], langs))

# (4) no language announcement in any reply
no_announce = not any(announces_lang(r) for r in all_replies)
results.append(("4 no language lecturing/announcing in any reply", no_announce, "—", []))

print("\n=== MLV INTEGRATED MIRROR SMOKE (real builder + real Groq " + MODEL + ", N=" + str(N) + "/case) ===")
allok = True
for name, ok, sample, langs in results:
    allok = allok and ok
    tag = (" detected=" + ",".join(langs)) if langs else ""
    print(("PASS" if ok else "FAIL") + "  " + name + tag)
    if sample != "—":
        print("       reply: " + sample.replace(chr(10), " ")[:160])
print("\nRESULT:", "ALL PASS" if allok else "SOME FAIL")
sys.exit(0 if allok else 1)
