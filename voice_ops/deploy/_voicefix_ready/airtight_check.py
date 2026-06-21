# -*- coding: utf-8 -*-
"""AIRTIGHT PRE-CHECK for the W-VOICE legacy fix (Unit A).

Runs on the BOX python with PYTHONPATH=/opt/famit-agent so it uses the REAL
voice_kernel.brain_packs.disclosure.contains_banned_phrase block-list as the oracle.

For each campaign it:
  1. renders build_system_prompt(fields)  (the system prompt)
  2. renders _llm_opener(...) FALLBACK (Groq is NOT called — we force the fallback
     path by monkeypatching httpx.post to raise, so we test the deterministic
     spoken opener the code emits without a network call / paid API).
  3. asserts contains_banned_phrase() is False on BOTH, plus a raw Devanagari/roman
     self-label sweep.

It also feeds an ADVERSARIAL hallucinated Groq opener (containing the banned phrase)
through the scrub to PROVE the output-boundary scrub discards it.

Exit 0 = PASS (zero AI self-label across all renders). Exit 1 = FAIL (prints offenders).
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

PATCH_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
CAMP_DIR = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/opt/famit-agent/var/campaigns")

# --- load the PATCHED prompt.py + agent.py as modules (named prompt/agent so
#     agent.py's `from prompt import ...` resolves to OUR patched prompt). ---
import types


def _load(modname, path):
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader(modname, str(path))
    spec = importlib.util.spec_from_loader(modname, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    loader.exec_module(mod)
    return mod


prompt = _load("prompt", PATCH_DIR / "prompt.py.patched")

# agent.py imports heavy livekit plugins at module load. We only need _llm_opener,
# so stub the heavy imports before loading. We exec the source with a guarded env.
import builtins

# Stub modules agent.py imports that aren't needed for _llm_opener.
for stub in ("livekit", "livekit.agents", "livekit.plugins",
             "livekit.plugins.elevenlabs", "dotenv", "memory", "langdetect"):
    if stub not in sys.modules:
        m = types.ModuleType(stub)
        sys.modules[stub] = m
# give the stubs the attributes agent.py pulls at import time
sys.modules["livekit"].agents = types.ModuleType("livekit.agents")
la = sys.modules["livekit.agents"]
for name in ("Agent", "AgentSession", "WorkerOptions", "cli"):
    setattr(la, name, object)
sys.modules["livekit.agents"].__dict__.setdefault("Agent", object)
lp = sys.modules["livekit.plugins"]
for name in ("elevenlabs", "groq", "sarvam", "silero"):
    setattr(lp, name, types.ModuleType("livekit.plugins." + name))
sys.modules["livekit.plugins.elevenlabs"].VoiceSettings = object
sys.modules["dotenv"].load_dotenv = lambda *a, **k: None


# real httpx is fine to import, but we will monkeypatch .post to force the fallback.
import httpx  # noqa: E402

agent = _load("agent", PATCH_DIR / "agent.py.patched")

from voice_kernel.brain_packs.disclosure import contains_banned_phrase  # noqa: E402

# Extra raw self-label regex sweep (belt-and-suspenders; the negative guards like
# "कभी 'AI'/'assistant' मत कहना" must NOT trip this — they are slash/quote-broken).
RAW_SELF_LABEL = re.compile(
    r"(की\s+एक\s+ai\s+assistant)|(\bai\s+assistant\b)|(मैं\s+एक\s+ai\b)|(ai\s+असिस्टेंट)|"
    r"(\bai\s+hoon\b)|(assistant\s+हूँ)|(एआई)|(की\s+एक\s+एआई)|(मैं\s+.{0,4}\s*ai\s+हूँ)",
    re.IGNORECASE,
)


def sweep(label, text):
    bad = []
    if contains_banned_phrase(text):
        bad.append("contains_banned_phrase=True")
    m = RAW_SELF_LABEL.search(text or "")
    if m:
        bad.append("raw-regex hit: %r" % (m.group(0),))
    return bad


def count_greetings(opener):
    # the spoken opener should contain exactly ONE greeting token.
    toks = re.findall(r"नमस्ते|namaste|good morning|good afternoon|good evening|hello|हेलो", opener, re.IGNORECASE)
    return len(toks)


failures = []
renders = []

# Force the fallback path: make httpx.post raise so _llm_opener returns its
# deterministic fallback line (NO network, NO paid Groq call).
class _Boom(Exception):
    pass


def _no_post(*a, **k):
    raise _Boom("forced-fallback (no paid Groq call in airtight check)")


httpx.post = _no_post

# Gather campaigns: AGARO/vacuum, a real-estate, the explicit-banned one, + extras.
wanted = [
    "1fd3218528.json",   # AGARO / vacuum (founder's actual)
    "18a29b5cec.json",   # AGARO / vacuum variant
    "b690f78cab.json",   # Shapoorji real-estate
    "80a939941d.json",   # Shapoorji Codename Joy
    "1983b6ff9d.json",   # DreamSpace SmartWatch
    "c17e55e9f3.json",   # *** explicit ai_disclosure = banned phrase (adversarial) ***
]
cases = []
for name in wanted:
    p = CAMP_DIR / name
    if not p.exists():
        continue
    d = json.load(open(p, encoding="utf-8"))
    fl = d.get("fields") or {}
    cases.append((name, fl))

# Also the in-code default GODREJ_FIELDS (patched -> ai_disclosure="")
cases.append(("GODREJ_FIELDS(default)", prompt.GODREJ_FIELDS))

for name, fl in cases:
    company = (fl.get("company_name") or "Famit").strip()
    product = (fl.get("product_name") or fl.get("product") or "हमारा product").strip()
    agent_name = (fl.get("agent_name") or "Riya").strip()
    lead = "Kunal Kumar"
    gender = prompt._gender_of(fl) if hasattr(prompt, "_gender_of") else "female"
    disclose = bool(fl.get("disclose_ai", True))
    disc = str(fl.get("ai_disclosure") or "").strip()

    # 1) system prompt
    try:
        sysp = prompt.build_system_prompt(fl)
    except Exception as e:
        failures.append("%s: build_system_prompt RAISED %r" % (name, e))
        sysp = ""
    # 2) opener fallback (deterministic, no network)
    opener = agent._llm_opener(agent_name, company, product, lead,
                               gender=gender, disclose=disclose, disclosure_phrase=disc)

    renders.append((name, opener, sysp))

    for lbl, txt in (("opener", opener), ("system_prompt", sysp)):
        bad = sweep(lbl, txt)
        if bad:
            failures.append("%s [%s]: %s :: %r" % (name, lbl, "; ".join(bad), txt[:300]))

    g = count_greetings(opener)
    if g != 1:
        failures.append("%s [opener]: expected exactly 1 greeting, got %d :: %r" % (name, g, opener))

# 3) ADVERSARIAL: prove the output-boundary scrub discards a hallucinated banned opener.
# Monkeypatch httpx.post to RETURN a banned opener, then assert _llm_opener returns the clean fallback.
class _Resp:
    def __init__(self, content):
        self._c = content
    def json(self):
        return {"choices": [{"message": {"content": self._c}}]}


BANNED_HALLUCINATION = "नमस्ते Kunal Kumar जी, मैं Riya बोल रही हूँ, AGARO की AI assistant हूँ, अभी दो minute हैं?"


def _post_banned(*a, **k):
    return _Resp(BANNED_HALLUCINATION)


httpx.post = _post_banned
scrubbed = agent._llm_opener("Riya", "AGARO", "Vacuum", "Kunal Kumar",
                             gender="female", disclose=True, disclosure_phrase="")
if contains_banned_phrase(scrubbed):
    failures.append("SCRUB FAILED: banned opener survived the output-boundary scrub :: %r" % scrubbed)
else:
    renders.append(("SCRUB(adversarial banned->clean)", scrubbed, "(n/a)"))

# Also prove the scrub itself recognizes the banned input (sanity on the oracle).
if not contains_banned_phrase(BANNED_HALLUCINATION):
    failures.append("ORACLE BROKEN: contains_banned_phrase did NOT flag the known-banned line")

print("=" * 70)
print("RENDERED OPENERS (one greeting each, no AI self-label):")
for name, opener, _ in renders:
    print("  [%s] %s" % (name, opener))
print("=" * 70)
if failures:
    print("AIRTIGHT RESULT: FAIL (%d offender(s))" % len(failures))
    for f in failures:
        print("  FAIL:", f)
    sys.exit(1)
else:
    print("AIRTIGHT RESULT: PASS — zero AI self-label across %d render-pairs + scrub proven." % len(renders))
    sys.exit(0)
