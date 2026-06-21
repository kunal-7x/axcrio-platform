#!/usr/bin/env python3
"""Offline eval suite for voice-agent-v2 (ROUND-11).

Runs on the BOX venv. Loads the CLEAN prompt, replays the scenarios that BREAK or that the
founder wants fixed, against the configured model, and runs automated checks + prints each reply
for eyeballing. This is the GATE: improve the prompt, run this, see it pass BEFORE any live call —
no more change-and-pray on a real call. NEVER prints API keys.

  /opt/capsy-agent/.venv/bin/python /opt/famit-agent-v2/tests/replay.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv("/opt/famit-agent-v2/.env")
except Exception:  # noqa: BLE001
    pass
import httpx  # noqa: E402
from prompt import build_system_prompt, GODREJ_FIELDS  # noqa: E402

MODEL = os.getenv("GROQ_LLM_MODEL", "llama-3.3-70b-versatile")
SYS = build_system_prompt(GODREJ_FIELDS)


def _keys():
    keys = []
    for path in ("/opt/famit-agent-v2/.env", "/opt/famit-agent/.env", ".env"):
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    s = line.strip()
                    if s.startswith("#") or "=" not in s:
                        continue
                    n, v = s.split("=", 1)
                    if "GROQ" in n and "KEY" in n:
                        for p in v.strip().strip('"').strip("'").split(","):
                            p = p.strip()
                            if p.startswith("gsk_") and p not in keys:
                                keys.append(p)
        except FileNotFoundError:
            pass
    return keys


def chat(turns):
    msgs = [{"role": "system", "content": SYS}] + [{"role": r, "content": c} for r, c in turns]
    body = {"model": MODEL, "messages": msgs,
            "temperature": float(os.getenv("GROQ_LLM_TEMPERATURE", "0.3")),
            "max_tokens": int(os.getenv("GROQ_MAX_TOKENS", "120"))}
    last = "no keys"
    for k in _keys():
        try:
            r = httpx.post("https://api.groq.com/openai/v1/chat/completions",
                           headers={"Authorization": "Bearer " + k, "Content-Type": "application/json",
                                    "User-Agent": "Mozilla/5.0"},
                           json=body, timeout=30.0)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
            last = "HTTP %d %s" % (r.status_code, r.text[:100])
        except Exception as e:  # noqa: BLE001
            last = repr(e)
    return "[ERROR: %s]" % last


# ── heuristics ────────────────────────────────────────────────────────────────
def _num_count(r):
    return len(re.findall(r"crore|lakh|करोड़|लाख|\b\d{2,}\b", r.lower()))


def _looks_english(r):
    latin = len(re.findall(r"[A-Za-z]", r))
    deva = len(re.findall(r"[ऀ-ॿ]", r))
    return latin > deva * 2 and latin > 12


def _is_goodbye(r):
    return any(w in r.lower() for w in ["bye", "धन्यवाद", "शुक्रिया", "alvida", "रखत"])


def _markup(r):
    return bool(re.search(r"##|\bStep\s*\d|\*\*|(^|\n)\s*[-*]\s|\[[^\]]*\]\(|₹|%", r))


# ── scenarios: (name, turns, expectation-desc, check(reply)->bool) ──────────────
SCEN = [
    ("post-permission → QUALIFY (one question), NOT a price dump",
     [("assistant", "ji main Riya, Famit se — kya do minute baat ho sakti hai?"), ("user", "haan ji boliye")],
     "a discovery question; no price/number dump",
     lambda r: _num_count(r) <= 1 and ("?" in r or any(w in r.lower() for w in ["kya", "chah", "kaun", "kitn"]))),
    ("price objection → keeps selling, does NOT cut",
     [("assistant", "Sir ye Godrej ka RERA project hai, Golf Course Extension pe."),
      ("user", "अरे ये तो बहुत महंगा है, इतना पैसा नहीं है हमारे पास")],
     "acknowledges + reframes, not a goodbye",
     lambda r: len(r) > 12 and not _is_goodbye(r)),
    ("English switch → reply in English",
     [("assistant", "Sir ye low-density forest-theme project hai."),
      ("user", "what is the exact possession date and the starting price?")],
     "replies in English",
     _looks_english),
    ("price ask → ONE number in words, no list",
     [("assistant", "Sir location bahut strong hai, Cyber City paas."), ("user", "achha price kitni hai?")],
     "at most one number; no ₹",
     lambda r: _num_count(r) <= 1 and "₹" not in r),
    ("curiosity-chain → one detail + a hook, not a dump",
     [("assistant", "ji main Riya, Famit se."), ("user", "achha is project ke baare mein thoda batao")],
     "one thing, not a full brochure",
     lambda r: _num_count(r) <= 1),
    ("STT garble → ask to repeat, do NOT guess",
     [("assistant", "Sir ye Godrej ka ultra-luxury project hai."), ("user", "बलुन कि बलछेन?")],
     "asks to repeat (clear nahi / dobara)",
     lambda r: any(w in r.lower() for w in ["clear nahi", "dobara", "dobaara", "samajh nahi", "repeat", "phir se", "sun nahi", "aawaz"])),
    ("callback sanity → never '2 saal'",
     [("assistant", "Sir aap ek baar dekh lijiye."), ("user", "abhi nahi, थोड़ी देर बाद call karna")],
     "no absurd '2 saal'; offers kal/agle hafte",
     lambda r: "साल" not in r and "saal" not in r.lower()),
    ("yes but NO time → ask for a day/time",
     [("assistant", "Sir ek site visit kar lijiye."), ("user", "haan visit to karni hai")],
     "asks for a time; no fake-booked",
     lambda r: any(w in r.lower() for w in ["kab", "kaun", "time", "din", "baje", "subah", "shaam"])),
    ("explicit bye → short close",
     [("assistant", "ji bilkul Kunal ji."), ("user", "ok thik hai, rakhta hoon, bye")],
     "a short goodbye",
     lambda r: len(r) < 220),
]


def main():
    nk = len(_keys())
    print("MODEL: %s | groq keys: %d | prompt chars: %d" % (MODEL, nk, len(SYS)))
    if nk == 0:
        print("NO GROQ KEYS — run on the box.")
        return 1
    npass = 0
    for name, turns, desc, check in SCEN:
        rep = chat(turns)
        mk = _markup(rep)
        try:
            ok = bool(check(rep)) and not rep.startswith("[ERROR") and not mk
        except Exception:  # noqa: BLE001
            ok = False
        npass += 1 if ok else 0
        print("\n%s %s" % ("✅" if ok else "❌", name))
        print("   want: %s%s" % (desc, "  | MARKUP-LEAK!" if mk else ""))
        print("   USER: %s" % turns[-1][1])
        print("   RIYA: %s" % rep)
    print("\nEVAL_RESULT: %d/%d passed" % (npass, len(SCEN)))
    return 0 if npass == len(SCEN) else 2


if __name__ == "__main__":
    raise SystemExit(main())
