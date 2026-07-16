"""research_analytics — persist Famit Research per-turn affect/prosody rows → ClickHouse.

Mirrors voice_analytics.py's DESIGN LAWS exactly (the live call must NEVER be affected):
  * FLAG-GATED + DORMANT-SAFE: nothing writes unless FAMIT_RESEARCH_ENABLED is on AND a
    ClickHouse write URL is configured. Dormant ⇒ every call site is a cheap no-op.
  * OFF THE SPEECH PATH: this is invoked by the POST-CALL extractor (a separate process,
    off the LiveKit/agent event loop), never mid-turn. The only network I/O is a batched
    INSERT bounded by an httpx timeout.
  * BEST-EFFORT: every public function swallows all errors → silent no-op, observable via
    a WARNING log (write failures were previously invisible).

Reuses the SAME ClickHouse env as voice_analytics (CLICKHOUSE_WRITE_URL / CLICKHOUSE_URL +
CLICKHOUSE_USER / CLICKHOUSE_PASSWORD). DDL lives in deploy/observability/voice_analytics.sql
(tables `famit_research_turns` + `famit_research_calls`); the operator applies it ONCE — this
module never auto-creates (a missing table fails the insert silently, never the call).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger("research_analytics")

TURNS_TABLE = "famit_research_turns"
CALLS_TABLE = "famit_research_calls"


def _truthy(v: str) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def _enabled() -> bool:
    return _truthy(os.getenv("FAMIT_RESEARCH_ENABLED", "0"))


def _ch_write_url() -> str:
    return (os.getenv("FAMIT_RESEARCH_CLICKHOUSE_URL")
            or os.getenv("CLICKHOUSE_WRITE_URL") or os.getenv("CLICKHOUSE_URL") or "").strip().rstrip("/")


def active() -> bool:
    return _enabled() and bool(_ch_write_url())


def _ch_ts(iso: str) -> str:
    """ISO8601 (…Z / +00:00) → ClickHouse DateTime64(3) literal 'YYYY-MM-DD HH:MM:SS.mmm' (UTC)."""
    try:
        dt = datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _f(v, d=0.0) -> float:
    try:
        return float(v)
    except Exception:  # noqa: BLE001
        return d


def _turn_row(t) -> dict:
    """A ResearchTurn (dataclass or dict) → one ClickHouse JSONEachRow object."""
    g = (lambda k, d=0.0: getattr(t, k, d)) if not isinstance(t, dict) else (lambda k, d=0.0: t.get(k, d))
    row = {
        "ts": _ch_ts(g("ts_iso", "")),
        "tenant_id": str(g("tenant_id", ""))[:120],
        "call_id": str(g("call_id", ""))[:120],
        "turn_num": int(g("turn_num", 0) or 0),
        "t_sec": _f(g("t_sec")),
        "speaker": str(g("speaker", "caller"))[:16],
        "f0_mean_hz": _f(g("f0_mean_hz")), "f0_range_hz": _f(g("f0_range_hz")),
        "f0_slope_hz_s": _f(g("f0_slope_hz_s")), "f0_var_hz": _f(g("f0_var_hz")),
        "loudness_db": _f(g("loudness_db")),
        "speech_rate_sps": _f(g("speech_rate_sps")),
        "pause_ratio": _f(g("pause_ratio")),
        "turn_latency_ms": _f(g("turn_latency_ms")),
        "voiced_sec": _f(g("voiced_sec")),
        "arousal": _f(g("arousal", 50.0)), "arousal_var": _f(g("arousal_var")),
        "friction": _f(g("friction", 50.0)), "friction_var": _f(g("friction_var")),
        "engagement": _f(g("engagement", 50.0)), "engagement_var": _f(g("engagement_var")),
        "valence_hint": _f(g("valence_hint")),
        "intent": str(g("intent", "") or "")[:24],
        "intervene": 1 if g("intervene", False) else 0,
        "confidence": _f(g("confidence")),
        "source": str(g("source", "asr_metadata"))[:24],
        "regime": str(g("regime", "steady"))[:24],
        "low_conf": 1 if g("low_conf", False) else 0,
        "transcript": str(g("transcript", ""))[:280],
    }
    # Nullable channels/extras — only include when present (clinical extras never headline).
    for k in ("conversion_risk", "llm_valence", "objection", "buying_intent", "talk_share",
              "backchannel_rate", "entrainment", "ssl_arousal",
              "jitter_local", "shimmer_local", "hnr_db"):
        v = g(k, None)
        if v is not None:
            row[k] = _f(v)
    return row


def _call_row(summary) -> dict:
    g = (lambda k, d=0.0: getattr(summary, k, d)) if not isinstance(summary, dict) else (lambda k, d=0.0: summary.get(k, d))
    conv = g("converted", None)
    return {
        # header ts = the call START (so a backfill/seed lands in the right window+partition), with
        # now() as a safe fallback when a summary carries no start time (keeps best-effort contract).
        "ts": _ch_ts(g("started_iso", "") or datetime.now(timezone.utc).isoformat()),
        "tenant_id": str(g("tenant_id", ""))[:120],
        "call_id": str(g("call_id", ""))[:120],
        "turns": int(g("turns", 0) or 0),
        "duration_s": _f(g("duration_s")),
        "arousal_mean": _f(g("arousal_mean", 50.0)), "arousal_peak": _f(g("arousal_peak", 50.0)),
        "friction_mean": _f(g("friction_mean", 50.0)), "friction_peak": _f(g("friction_peak", 50.0)),
        "arousal_trend": _f(g("arousal_trend")), "friction_trend": _f(g("friction_trend")),
        "engagement_mean": _f(g("engagement_mean", 50.0)), "engagement_peak": _f(g("engagement_peak", 50.0)),
        "engagement_trend": _f(g("engagement_trend")),
        "conversion_risk": _f(g("conversion_risk")), "intervene": 1 if g("intervene", False) else 0,
        "top_intent": str(g("top_intent", "") or "")[:24],
        "f0_mean_hz": _f(g("f0_mean_hz")), "speech_rate_sps": _f(g("speech_rate_sps")),
        "pause_ratio": _f(g("pause_ratio")),
        "confidence": _f(g("confidence")),
        "source": str(g("source", "asr_metadata"))[:24],
        "regimes": ",".join(g("regimes", []) or [])[:200],
        "outcome": str(g("outcome", ""))[:40],
        "converted": 1 if conv else 0,
        "has_outcome": 0 if conv is None else 1,
        "deal_value": _f(g("deal_value")),
    }


def persist_call(turns: List, summary, *, force: bool = False) -> bool:
    """Write a finished call's per-turn rows + the header to ClickHouse. No-op unless active()
    (or force=True for a one-shot backfill with an explicit URL). Returns True on a clean POST.
    Never raises."""
    try:
        if not (active() or force):
            return False
        url = _ch_write_url()
        if not url:
            return False
        turn_objs = [_turn_row(t) for t in (turns or [])]
        _insert(url, TURNS_TABLE, turn_objs)
        if summary is not None:
            _insert(url, CALLS_TABLE, [_call_row(summary)])
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("research persist_call error: %r", exc)
        return False


def _insert(url: str, table: str, objs: list) -> None:
    if not objs:
        return
    try:
        import httpx
        from urllib.parse import urlsplit
        body = "\n".join(json.dumps(o, ensure_ascii=False) for o in objs)
        params = {"query": f"INSERT INTO {table} FORMAT JSONEachRow"}
        # ClickHouse rejects an Authorization header AND user/password params together (Code 516):
        # only add the env credentials when the URL carries no userinfo (mirror voice_analytics.py).
        if "@" not in (urlsplit(url).netloc or ""):
            user = (os.getenv("CLICKHOUSE_USER") or "").strip()
            pw = (os.getenv("CLICKHOUSE_PASSWORD") or "").strip()
            if user:
                params["user"] = user
            if pw:
                params["password"] = pw
        r = httpx.post(url + "/", params=params, content=body.encode("utf-8"),
                       timeout=float(os.getenv("FAMIT_RESEARCH_TIMEOUT", "8")))
        if r.status_code >= 400:
            logger.warning("research insert -> %s failed: HTTP %s %s", table, r.status_code, (r.text or "")[:200])
        else:
            logger.info("research insert -> %s ok (%d rows)", table, len(objs))
    except Exception as exc:  # noqa: BLE001
        logger.warning("research insert -> %s error: %r", table, exc)
