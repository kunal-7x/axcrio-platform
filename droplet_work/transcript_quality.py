"""transcript_quality — post-call CONTENT-quality analysis of a voice-call transcript via OpenRouter.

The Voice Analytics 'quality meter' grades the TECHNICAL call (latency / 429s / network). THIS grades
the actual CONVERSATION: an LLM (Claude Sonnet via OpenRouter, off the live path) reads the transcript
and scores the AI agent's dialogue — catching exactly the failures small runtimes produce: repetition
(repeating a time / word / sentence), hallucination (a random mid-call "goodbye", invented facts),
hanging / dead-air rambling ("I didn't hear you", "hello hello"), robotic/bookish language, mangled
names, NOT listening, and whether it actually progressed toward the goal.

Best-effort + dormant-safe: returns {"ok": False, ...} when OPENROUTER_API_KEY is unset or the call
fails. NEVER raises. Result is meant to be CACHED by the caller (one paid analysis per call).
"""
from __future__ import annotations

import json
import os
import re

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.getenv("TRANSCRIPT_QA_MODEL", "anthropic/claude-sonnet-4.6")


def _render(turns: list) -> str:
    lines = []
    for t in (turns or [])[:90]:
        if not isinstance(t, dict):
            continue
        role = "AGENT" if str(t.get("role", "")).lower() in ("ai", "assistant", "agent") else "CALLER"
        txt = str(t.get("text") or t.get("content") or "").strip()
        if txt:
            lines.append(f"{role}: {txt}")
    return "\n".join(lines)


async def analyze(turns: list, context: dict | None = None) -> dict:
    """Run the content-quality analysis. Returns {ok, score, grade, summary, dims{}, issues[], model}.
    Dormant-safe; never raises."""
    key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not key:
        return {"ok": False, "error": "no_openrouter_key",
                "message": "Set OPENROUTER_API_KEY to enable transcript analysis."}
    convo = _render(turns)
    if not convo.strip():
        return {"ok": False, "error": "empty", "message": "No transcript for this call."}
    ctx = context or {}
    system = (
        "You are a strict QA analyst for an OUTBOUND AI tele-calling agent that speaks Hinglish "
        "(Hindi+English) to Indian prospects. Grade ONLY the AI AGENT's side of the call — be honest "
        "and specific. Hunt hard for these failures and QUOTE the exact offending agent line: "
        "repetition (repeating a time / word / whole sentence), hallucination (a random mid-call "
        "'goodbye/अलविदा', inventing facts/guarantees), hanging or dead-air recovery rambling ('मैंने "
        "आपकी बात नहीं सुनी', 'hello hello'), robotic / bookish (किताबी) language, a mangled company "
        "or person name, NOT listening to what the caller said, and whether the agent made real "
        "progress toward the goal (book a site visit / qualify the lead). A clean, warm, human, "
        "goal-advancing call scores high; a repetitive, rambling, or off-script one scores low."
    )
    user = (
        f"Campaign: {str(ctx.get('campaign', '') or '')[:120]} | Goal: book a free site visit / qualify the lead.\n\n"
        f"TRANSCRIPT:\n{convo}\n\n"
        'Return ONLY strict JSON (no prose, no code fence): {"score": <0-100 overall content quality>, '
        '"grade": "Excellent|Good|Fair|Poor", "summary": "<one honest sentence>", '
        '"dims": {"naturalness": <0-100>, "coherence": <0-100>, "listening": <0-100>, '
        '"goal_progress": <0-100>, "language": <0-100>}, '
        '"issues": [{"type": "repetition|hallucination|hanging|robotic|not_listening|off_goal", '
        '"severity": "high|medium|low", "quote": "<the exact agent line>", "note": "<why, ≤12 words>"}]}. '
        "List at most 6 issues, worst first. If the call was clean, issues can be []."
    )
    try:
        async with httpx.AsyncClient(timeout=50.0) as c:
            r = await c.post(
                OPENROUTER_URL,
                headers={"Authorization": "Bearer " + key, "content-type": "application/json",
                         "HTTP-Referer": (os.getenv("PANEL_BASE_URL") or "https://haptica.famit.in"),
                         "X-Title": "Haptica Transcript QA"},
                json={"model": MODEL, "max_tokens": 1100, "temperature": 0.2,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": user}]},
            )
        if r.status_code != 200:
            return {"ok": False, "error": f"http_{r.status_code}", "message": (r.text or "")[:200]}
        text = (((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        data = json.loads(m.group(0)) if m else {}
        if not isinstance(data, dict) or "score" not in data:
            return {"ok": False, "error": "parse_failed", "message": text[:200]}
        # bound + sanitise
        try:
            data["score"] = max(0, min(100, int(round(float(data.get("score", 0))))))
        except Exception:  # noqa: BLE001
            data["score"] = 0
        issues = data.get("issues")
        data["issues"] = (issues if isinstance(issues, list) else [])[:6]
        data["ok"] = True
        data["model"] = MODEL
        return data
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "request_failed", "message": type(exc).__name__}
