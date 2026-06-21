#!/usr/bin/env python3
"""Offline live-Groq replay gate for voice-agent-v2 (ROUND-10).

Runs on the BOX venv. Loads the CLEAN prompt, replays the exact turns that BREAK on the
live agent today against the configured model (default llama-3.3-70b-versatile), prints
each reply, and flags red-flags (markdown/steps/₹/digit-spam/empty). This is a SANITY gate
before the founder's real call — it is NOT proof of "done". NEVER prints API keys.

  /opt/capsy-agent/.venv/bin/python /opt/famit-agent-v2/tests/replay.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx  # noqa: E402
from prompt import build_system_prompt, GODREJ_FIELDS  # noqa: E402


def _keys() -> list[str]:
    keys: list[str] = []
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


MODEL = os.getenv("GROQ_LLM_MODEL", "llama-3.3-70b-versatile")
SYS = build_system_prompt(GODREJ_FIELDS)

# Each scenario = a short prior context + the caller's latest turn (the one that breaks today).
SCEN = [
    ("price objection — must NOT cut the call, must keep selling", [
        ("assistant", "Good evening sir, main Riya, Famit se — Godrej Aristocrat ke baare mein baat karni thi."),
        ("user", "अरे रुको, ये तो बहुत महंगा है, इतना पैसा नहीं है हमारे पास")]),
    ("flat 'no interest' mid-pitch — must reframe once, must NOT hang up", [
        ("assistant", "Sir ye Godrej ka RERA project hai, Golf Course Extension Road pe."),
        ("user", "नहीं नहीं, मुझे अभी interest नहीं है")]),
    ("English turn — must reply in English", [
        ("assistant", "Sir, ye low-density forest-theme project hai, kaafi premium."),
        ("user", "what is the exact starting price and the possession date?")]),
    ("price ask — ONE number in words, no price-list / no digit garbage", [
        ("assistant", "Sir location bahut strong hai, Cyber City sirf paas mein hai."),
        ("user", "achha is project ki price kitni hai?")]),
    ("yes but NO time — must ask for a day+time, must NOT claim it's booked", [
        ("assistant", "Sir aap ek baar site dekh lijiye, aapko bahut accha lagega."),
        ("user", "haan theek hai, visit to karni hai")]),
    ("explicit bye — a short warm goodbye", [
        ("assistant", "Sir koi baat nahi, main aapko details bhej deti hoon."),
        ("user", "ok thik hai, rakhta hoon, bye")]),
]


def chat(turns: list[tuple[str, str]]) -> str:
    msgs = [{"role": "system", "content": SYS}] + [{"role": r, "content": c} for r, c in turns]
    body = {"model": MODEL, "messages": msgs,
            "temperature": float(os.getenv("GROQ_LLM_TEMPERATURE", "0.3")),
            "max_tokens": int(os.getenv("GROQ_MAX_TOKENS", "90"))}
    last = "no keys"
    for k in _keys():
        try:
            r = httpx.post("https://api.groq.com/openai/v1/chat/completions",
                           headers={"Authorization": "Bearer " + k,
                                    "Content-Type": "application/json",
                                    "User-Agent": "Mozilla/5.0"},
                           json=body, timeout=30.0)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
            last = "HTTP %d %s" % (r.status_code, r.text[:120])
        except Exception as e:  # noqa: BLE001
            last = repr(e)
    return "[ERROR: %s]" % last


def flags(reply: str) -> str:
    f = []
    if not reply.strip():
        f.append("EMPTY")
    if re.search(r"##|\bStep\s*\d|\*\*|(^|\n)\s*[-*]\s|\[[^\]]*\]\(", reply):
        f.append("MARKDOWN/STEPS")
    if "₹" in reply or "%" in reply:
        f.append("SYMBOL")
    if re.search(r"\d[\d.,]*\s+\d[\d.,]*\s+\d", reply):
        f.append("DIGIT-SPAM")
    return ", ".join(f) or "clean"


def main() -> int:
    nk = len(_keys())
    print("MODEL: %s | groq keys: %d | prompt chars: %d" % (MODEL, nk, len(SYS)))
    if nk == 0:
        print("NO GROQ KEYS FOUND — run on the box where .env exists.")
        return 1
    any_flag = False
    for name, turns in SCEN:
        rep = chat(turns)
        fl = flags(rep)
        if fl != "clean" or rep.startswith("[ERROR"):
            any_flag = True
        print("\n=== %s ===" % name)
        print("USER: %s" % turns[-1][1])
        print("RIYA: %s" % rep)
        print("FLAGS: %s" % fl)
    print("\nREPLAY_RESULT:", "FLAGS_PRESENT (eyeball above)" if any_flag else "ALL_CLEAN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
