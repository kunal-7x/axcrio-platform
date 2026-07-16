"""voice_analytics — per-call + per-turn voice latency telemetry → ClickHouse (P1).

Captures the latency breakdown the LiveKit agent ALREADY computes (EOU delay, LLM TTFT, TTS TTFB,
STT audio duration, token usage) into two ClickHouse tables that the panel's "Voice Performance
Analytics" page reads:
  * haptica_voice_turns — one row per metric event (stage-tagged) → per-utterance timeline + the
    P95/P99 distributions (quantile over each stage's latency_ms).
  * haptica_voice_calls — one header row per call → the live dashboard KPIs + the call list.

DESIGN LAWS (mirror logging_service / the earner): the live call must NEVER be affected.
  * FLAG-GATED + DORMANT-SAFE: start() returns None unless VOICE_ANALYTICS_ENABLED is on AND a
    ClickHouse write URL is configured. None ⇒ every agent call site is a cheap no-op.
  * NEVER BLOCKS A CALL: record() is a pure in-memory append in the metrics callback. The ONLY
    network I/O is a SINGLE batched INSERT fired on a DAEMON THREAD at call end (off the speech
    path), so a slow/hung ClickHouse can never stall call teardown.
  * BEST-EFFORT: every public method swallows all errors → silent no-op.

Write auth (env, all optional): CLICKHOUSE_WRITE_URL (falls back to CLICKHOUSE_URL),
CLICKHOUSE_USER, CLICKHOUSE_PASSWORD, VOICE_ANALYTICS_TIMEOUT (default 8s).
DDL lives in deploy/observability/voice_analytics.sql (operator runs once).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger("voice_analytics")

# The 4 real per-turn latency stages and where each comes from (all in SECONDS):
#   eou ← EOUMetrics.end_of_utterance_delay   (endpointing wait)
#   stt ← EOUMetrics.transcription_delay      (REAL STT latency — NOT STTMetrics.audio_duration,
#                                              which is the USER's speech length; that earlier bug
#                                              made "STT" read ~1.6s instead of ~0.25s)
#   llm ← LLMMetrics.ttft                      (+ prompt/completion tokens + tokens/sec)
#   tts ← TTSMetrics.ttfb                      (+ characters synthesised)
# STTMetrics.audio_duration is captured separately as speech_ms_total (informational, per call).


def _truthy(v: str) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def _enabled() -> bool:
    return _truthy(os.getenv("VOICE_ANALYTICS_ENABLED", "0"))


def _ch_write_url() -> str:
    return (os.getenv("CLICKHOUSE_WRITE_URL") or os.getenv("CLICKHOUSE_URL") or "").strip().rstrip("/")


def _active() -> bool:
    return _enabled() and bool(_ch_write_url())


def _ch_ts(epoch: float) -> str:
    """ClickHouse DateTime64(3) literal (UTC, millisecond precision)."""
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _u32(v) -> int:
    try:
        return max(0, min(int(v), 4_000_000_000))
    except Exception:  # noqa: BLE001
        return 0


class Recorder:
    """One per live call. Accumulate cheaply in memory; flush once at call end."""

    def __init__(self, meta: dict):
        self.meta = {k: ("" if v is None else str(v))[:200] for k, v in (meta or {}).items()}
        self.rows: list[dict] = []          # per-metric-event rows
        self.turn_index = 0                 # advanced on each EOU (user-utterance boundary)
        self.started = time.time()
        self.speech_ms_total = 0            # total USER speech captured (STTMetrics.audio_duration)
        self.net_quality = ""               # phone-leg connection quality (best-effort, from LiveKit)
        self.net_rtt_ms = 0
        self.net_packet_loss = 0.0
        self.counts: dict = {"stt": 0, "llm": 0, "tts": 0, "eou": 0,
                             "rate_limit_429": 0, "errors": 0}
        self._lock = threading.Lock()

    def _add(self, stage: str, latency_s, *, tokens_p=0, tokens_c=0, tps=0.0,
             characters=0, speech_id="") -> None:
        """Append one per-stage turn row. latency_s in SECONDS (None/neg -> 0). Never raises."""
        latency_ms = _u32(float(latency_s) * 1000) if (latency_s is not None and float(latency_s) >= 0) else 0
        row = {
            "stage": stage,
            "turn_index": min(self.turn_index, 65000),
            "speech_id": str(speech_id or "")[:64],
            "latency_ms": latency_ms,
            "prompt_tokens": _u32(tokens_p or 0),
            "completion_tokens": _u32(tokens_c or 0),
            "tokens_per_second": round(float(tps or 0.0), 1),
            "characters": _u32(characters or 0),
            "net_rtt_ms": _u32(self.net_rtt_ms or 0),   # TELECOM latency known at this turn (0 = unknown)
            "ts": time.time(),
        }
        with self._lock:
            self.rows.append(row)
            self.counts[stage] = self.counts.get(stage, 0) + 1

    def record(self, metric_type_name: str, m) -> None:
        """Called from the agent's metrics_collected hook — cheap append(s). Never raises.
        STT latency = EOUMetrics.transcription_delay (the real finalise-the-transcript time), NOT
        STTMetrics.audio_duration (the user's speech length — that was the bug)."""
        try:
            sid = str(getattr(m, "speech_id", None) or getattr(m, "request_id", None) or "")[:64]
            if metric_type_name == "EOUMetrics":
                self.turn_index += 1
                self._add("eou", getattr(m, "end_of_utterance_delay", None), speech_id=sid)
                td = getattr(m, "transcription_delay", None)
                if td is not None:
                    self._add("stt", td, speech_id=sid)          # <-- REAL STT latency
            elif metric_type_name == "LLMMetrics":
                self._add("llm", getattr(m, "ttft", None), speech_id=sid,
                          tokens_p=getattr(m, "prompt_tokens", 0),
                          tokens_c=getattr(m, "completion_tokens", 0),
                          tps=getattr(m, "tokens_per_second", 0))
            elif metric_type_name == "TTSMetrics":
                # ROBUST char capture: plugins name this differently (characters_count / characters /
                # text length) — try each so TTS chars (→ TTS cost) are never silently 0.
                _chars = (getattr(m, "characters_count", 0) or getattr(m, "characters", 0)
                          or len(str(getattr(m, "text", "") or "")))
                self._add("tts", getattr(m, "ttfb", None), speech_id=sid, characters=_chars)
            elif metric_type_name == "STTMetrics":
                # USER speech length — informational, NOT latency. Accumulate for the call header.
                ad = getattr(m, "audio_duration", None)
                if ad is not None and float(ad) >= 0:
                    with self._lock:
                        self.speech_ms_total += _u32(float(ad) * 1000)
                        self.counts["stt"] = self.counts.get("stt", 0) + 1
        except Exception:  # noqa: BLE001
            pass

    def set_network(self, quality: str = "", rtt_ms=0, packet_loss=0.0) -> None:
        """Best-effort: record the phone leg's connection quality / RTT / loss. Keeps the WORST quality
        seen over the call (a momentary dip matters more than the last sample). Never raises."""
        _rank = {"LOST": 0, "POOR": 1, "GOOD": 2, "EXCELLENT": 3}
        try:
            with self._lock:
                if quality:
                    new = str(quality).upper()
                    cur = (self.net_quality or "").upper()
                    if not cur or _rank.get(new, 9) < _rank.get(cur, 9):
                        self.net_quality = str(quality)[:20]
                if rtt_ms:
                    self.net_rtt_ms = max(self.net_rtt_ms, _u32(rtt_ms))
                if packet_loss:
                    self.net_packet_loss = max(self.net_packet_loss, round(float(packet_loss), 4))
        except Exception:  # noqa: BLE001
            pass

    def note(self, kind: str) -> None:
        """Bump a per-call counter (e.g. 'rate_limit_429', 'errors'). Never raises."""
        try:
            with self._lock:
                self.counts[kind] = self.counts.get(kind, 0) + 1
        except Exception:  # noqa: BLE001
            pass

    def finish(self, *, status: str = "completed", outcome: str = "",
               duration_s: float | None = None) -> None:
        """Flush the call to ClickHouse SYNCHRONOUSLY at call teardown. MUST NOT be a daemon thread:
        a LiveKit job runs in a subprocess that exits the instant the shutdown callback returns, which
        kills a daemon thread mid-POST so the row silently never lands (the original bug). This runs
        from the agent's shutdown callback — the call is already over, so a brief blocking POST is
        fine, and the httpx timeout (VOICE_ANALYTICS_TIMEOUT, default 8s) bounds it. No-op when
        dormant; never raises. Idempotent-ish: a second call just sends an extra (harmless) batch."""
        try:
            if not _active():
                return
            with self._lock:
                rows = list(self.rows)
                counts = dict(self.counts)
            ended = time.time()
            dur_ms = _u32((duration_s if duration_s is not None else (ended - self.started)) * 1000)
            self._flush(rows, counts, status, outcome, dur_ms, ended)
        except Exception:  # noqa: BLE001
            pass

    def _flush(self, rows, counts, status, outcome, dur_ms, ended) -> None:
        try:
            url = _ch_write_url()
            if not url:
                return
            base = {
                "call_id": self.meta.get("call_id", ""),
                "tenant_id": self.meta.get("tenant_id", ""),
                "campaign_id": self.meta.get("campaign_id", ""),
                "agent_name": self.meta.get("agent_name", ""),
                "phone": self.meta.get("phone", ""),
                "lead_name": self.meta.get("lead_name", ""),
                "stt_provider": self.meta.get("stt_provider", ""),
                "llm_provider": self.meta.get("llm_provider", ""),
                "tts_provider": self.meta.get("tts_provider", ""),
                "stt_model": self.meta.get("stt_model", ""),
                "llm_model": self.meta.get("llm_model", ""),
                "tts_model": self.meta.get("tts_model", ""),
                "voice_id": self.meta.get("voice_id", ""),
                "voice_name": self.meta.get("voice_name", ""),
                "language": self.meta.get("language", ""),
            }
            turn_objs = []
            for r in rows:
                o = dict(base)
                o.update({
                    "ts": _ch_ts(r["ts"]),
                    "turn_index": r["turn_index"],
                    "stage": r["stage"],
                    "speech_id": r["speech_id"],
                    "latency_ms": r["latency_ms"],
                    "prompt_tokens": r["prompt_tokens"],
                    "completion_tokens": r["completion_tokens"],
                    "tokens_per_second": r.get("tokens_per_second", 0.0),
                    "characters": r.get("characters", 0),
                    "net_rtt_ms": r.get("net_rtt_ms", 0),   # telecom RTT snapshot for this turn
                })
                turn_objs.append(o)
            header = dict(base)
            header.update({
                "ts": _ch_ts(self.started),
                "ended_at": _ch_ts(ended),
                "duration_ms": dur_ms,
                "status": (status or "completed")[:40],
                "outcome": (outcome or "")[:60],
                "turns": _u32(counts.get("eou", 0)),
                "llm_calls": _u32(counts.get("llm", 0)),
                "tts_calls": _u32(counts.get("tts", 0)),
                "stt_calls": _u32(counts.get("stt", 0)),
                "rate_limit_429": _u32(counts.get("rate_limit_429", 0)),
                "errors": _u32(counts.get("errors", 0)),
                "in_tokens": _u32(sum(r["prompt_tokens"] for r in rows)),
                "out_tokens": _u32(sum(r["completion_tokens"] for r in rows)),
                "speech_ms": _u32(self.speech_ms_total),
                "characters": _u32(sum(r.get("characters", 0) for r in rows)),
                "net_quality": (self.net_quality or "")[:20],
                "net_rtt_ms": _u32(self.net_rtt_ms),
                "net_packet_loss": round(float(self.net_packet_loss or 0.0), 4),
            })
            self._insert(url, "haptica_voice_turns", turn_objs)
            self._insert(url, "haptica_voice_calls", [header])
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _insert(url: str, table: str, objs: list) -> None:
        if not objs:
            return
        try:
            import httpx
            body = "\n".join(json.dumps(o, ensure_ascii=False) for o in objs)
            # skip_unknown_fields: forward-compat so a NEW row field (e.g. net_rtt_ms before the
            # operator runs the ALTER) is silently ignored on an older table instead of failing the
            # whole batch. Existing fields are unaffected. Decouples schema migration from code deploy.
            params = {"query": f"INSERT INTO {table} FORMAT JSONEachRow",
                      "input_format_skip_unknown_fields": "1"}
            # Auth: ClickHouse rejects an Authorization header AND user/password params at the SAME
            # time (Code 516). When CLICKHOUSE_URL carries userinfo (http://user:pass@host) httpx
            # already sends the Authorization header, so do NOT also add params. Only fall back to the
            # env user/password params when the URL has no userinfo (the original credential path).
            from urllib.parse import urlsplit
            if "@" not in (urlsplit(url).netloc or ""):
                user = (os.getenv("CLICKHOUSE_USER") or "").strip()
                pw = (os.getenv("CLICKHOUSE_PASSWORD") or "").strip()
                if user:
                    params["user"] = user
                if pw:
                    params["password"] = pw
            r = httpx.post(url + "/", params=params, content=body.encode("utf-8"),
                           timeout=float(os.getenv("VOICE_ANALYTICS_TIMEOUT", "8")))
            # Observable best-effort: log the outcome (write failures were previously silent). Never raises.
            if r.status_code >= 400:
                logger.warning("voice_analytics insert -> %s failed: HTTP %s %s",
                               table, r.status_code, (r.text or "")[:200])
            else:
                logger.info("voice_analytics insert -> %s ok (%d rows)", table, len(objs))
        except Exception as exc:  # noqa: BLE001
            logger.warning("voice_analytics insert -> %s error: %r", table, exc)


def start(**meta) -> "Recorder | None":
    """Begin recording a call. Returns None (every call site no-ops) unless analytics is enabled
    AND a ClickHouse write URL is configured. Never raises."""
    try:
        if not _active():
            return None
        return Recorder(meta)
    except Exception:  # noqa: BLE001
        return None


def flush_provider_key_usage(meta: dict, rows: list) -> None:
    """P2.2: flush this call's PER-KEY provider usage (deltas) to ClickHouse SYNCHRONOUSLY at call
    teardown, so the backend's /admin/provider-pool/usage sees cross-process key utilization. Gated
    only on a ClickHouse write URL (independent of VOICE_ANALYTICS_ENABLED — the agent only calls this
    when the provider manager is on). MUST be synchronous (not a daemon thread): the LiveKit job
    subprocess exits the moment the shutdown callback returns and would kill a daemon thread mid-POST.
    The httpx timeout bounds it; never raises. `rows` = [{provider, fingerprint, success, failures,
    rate_limits, latency_ms_avg, score, status}, ...]."""
    try:
        if not rows or not _ch_write_url():
            return
        m = {k: ("" if v is None else str(v))[:200] for k, v in (meta or {}).items()}
        ts = _ch_ts(time.time())
        objs = []
        for r in rows:
            try:
                objs.append({
                    "ts": ts,
                    "tenant_id": m.get("tenant_id", ""),
                    "provider": str(r.get("provider", ""))[:40],
                    "fingerprint": str(r.get("fingerprint", ""))[:64],
                    "call_id": m.get("call_id", ""),
                    "calls": 1,
                    "success": _u32(r.get("success", 0)),
                    "failures": _u32(r.get("failures", 0)),
                    "rate_limits": _u32(r.get("rate_limits", 0)),
                    "latency_ms_avg": _u32(r.get("latency_ms_avg", 0)),
                    "score": float(r.get("score", 0.0) or 0.0),
                    "status": str(r.get("status", ""))[:20],
                })
            except Exception:  # noqa: BLE001
                continue
        if objs:
            Recorder._insert(_ch_write_url(), "haptica_provider_key_usage", objs)
    except Exception:  # noqa: BLE001
        pass
