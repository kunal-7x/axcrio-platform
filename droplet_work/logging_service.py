"""logging_service — Haptica's white-labeled error & event log + alerting.

Captures backend AND voice-agent errors/events into an append-only JSONL on the shared
/data volume, with:
  * in-memory recency ring for fast reads,
  * a stable fingerprint per event so repeat errors AGGREGATE (a count + last_seen)
    instead of flooding the operator,
  * a monotonic `seq` so the panel's notification bell can compute "unread since X"
    purely client-side (no server read-state),
  * an optional LLM-authored "why it happened + how to fix" suggestion per fingerprint,
  * an optional Telegram push (throttled) when something at error/critical level happens.

DESIGN LAWS (mirror the audit / comm modules):
  * IMPORT-GUARDED + BEST-EFFORT: every public function is wrapped so a logging fault can
    NEVER break the caller (the live earner or the API). Any failure -> silent no-op /
    empty result. This module must be safe to call from the hottest path.
  * DORMANT-SAFE: with nothing configured it still records to JSONL; the Telegram push and
    the AI suggestion are OPT-IN via env and do ZERO network I/O when unconfigured.
  * TENANT-AWARE: events carry tenant_id; super-admin reads everything, a tenant is scoped.
  * WHITE-LABEL: this module has no vendor identity. The panel surfaces it as "System Logs".

Public API (used by caller.py + agent.py):
    init(path, *, fixes_path=None)
    record(level, source, message, *, tenant_id, call_id, error_type, context) -> dict|None
    tail(*, limit, offset, level, source, tenant_id, q, since) -> dict
    summary(*, tenant_id) -> dict
    get(event_id, *, tenant_id) -> dict|None
    notifications(*, after_seq, limit, tenant_id) -> dict
    suggest_fix(event_id, *, tenant_id) -> str
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

# ── severity ladder ───────────────────────────────────────────────────────────
LEVELS = ("debug", "info", "warning", "error", "critical")
_LEVEL_RANK = {lv: i for i, lv in enumerate(LEVELS)}
_ALERT_MIN_RANK = _LEVEL_RANK["error"]  # error + critical fire a Telegram alert

# ── module state (all guarded behind _LOCK) ───────────────────────────────────
_LOCK = threading.RLock()
_PATH: Path | None = None          # the append-only JSONL
_FIXES_PATH: Path | None = None    # sidecar: fingerprint -> AI fix suggestion
_RING: deque = deque(maxlen=2000)  # recent events in memory (newest last)
_SEQ = 0                           # monotonic event counter (this process)
_AGG: dict = {}                    # fingerprint -> {count, first_seen, last_seen, last_id}
_FIXES: dict = {}                  # fingerprint -> suggestion text (cached + persisted)
_TG_LAST: dict = {}               # fingerprint -> last telegram-alert epoch (throttle)
_FILE_OFFSET = 0                   # bytes of the JSONL already ingested into _RING
_READY = False

# Rotate the on-disk JSONL when it grows past this (keeps one .1 backup). The in-memory ring
# is always bounded; this just stops slow unbounded disk growth on the shared volume.
_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(50 * 1024 * 1024)))


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fingerprint(level: str, source: str, message: str, error_type: str) -> str:
    """Stable short hash that groups the SAME recurring problem. Numbers/ids are stripped
    from the message so 'failed after 4 attempts' and 'after 5 attempts' collapse to one."""
    import re
    norm = re.sub(r"\d+", "#", (message or "")[:200]).strip().lower()
    raw = f"{level}|{source}|{error_type}|{norm}"
    return hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest()[:12]


def init(path, *, fixes_path=None) -> bool:
    """Point the store at `path` (a JSONL on the shared volume) and warm the in-memory ring
    from the tail of the file. Idempotent. Never raises -> returns False on any problem."""
    global _PATH, _FIXES_PATH, _SEQ, _READY, _FILE_OFFSET
    try:
        with _LOCK:
            _PATH = Path(path)
            _FIXES_PATH = Path(fixes_path) if fixes_path else _PATH.with_name("system_event_fixes.json")
            _PATH.parent.mkdir(parents=True, exist_ok=True)
            # warm the ring from the last ~2000 lines (cheap, bounded)
            _RING.clear()
            _AGG.clear()
            mx = 0
            if _PATH.exists():
                try:
                    lines = _PATH.read_text(encoding="utf-8").splitlines()[-_RING.maxlen:]
                except Exception:  # noqa: BLE001
                    lines = []
                for ln in lines:
                    try:
                        ev = json.loads(ln)
                    except Exception:  # noqa: BLE001
                        continue
                    if not isinstance(ev, dict):
                        continue
                    _RING.append(ev)
                    mx = max(mx, int(ev.get("seq", 0) or 0))
                    _index_agg(ev)
            _SEQ = mx
            # we've consumed the whole file into the ring; subsequent appends (by THIS or
            # ANOTHER process — the agent shares this file) are ingested lazily on read.
            try:
                _FILE_OFFSET = _PATH.stat().st_size if _PATH.exists() else 0
            except Exception:  # noqa: BLE001
                _FILE_OFFSET = 0
            # load cached AI fixes
            _FIXES.clear()
            try:
                if _FIXES_PATH.exists():
                    data = json.loads(_FIXES_PATH.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        _FIXES.update({k: v for k, v in data.items() if isinstance(v, str)})
            except Exception:  # noqa: BLE001
                pass
            _READY = True
        return True
    except Exception:  # noqa: BLE001
        return False


def _index_agg(ev: dict) -> None:
    fp = ev.get("fingerprint") or ""
    if not fp:
        return
    a = _AGG.get(fp)
    ts = ev.get("ts") or ""
    if a is None:
        _AGG[fp] = {"count": 1, "first_seen": ts, "last_seen": ts, "last_id": ev.get("id", "")}
    else:
        a["count"] += 1
        a["last_seen"] = ts or a["last_seen"]
        a["last_id"] = ev.get("id", a["last_id"])


def _sync_from_disk() -> None:
    """Ingest lines appended to the JSONL by OTHER processes since we last read (the voice
    agent writes booking/error events to the SAME shared file in a different container). Called
    at the start of every read so the panel + bell see agent-sourced events WITHOUT a backend
    restart. Byte-precise (binary, only complete lines) + id-deduped (so our own appends aren't
    double-counted) + seq REASSIGNED to this process's monotonic counter (the agent keeps its
    own _SEQ, so on-disk seq values collide across processes and must not be trusted for the
    bell cursor). Must be called under _LOCK. Best-effort; never raises."""
    global _FILE_OFFSET, _SEQ
    try:
        if _PATH is None or not _PATH.exists():
            return
        size = _PATH.stat().st_size
        if size < _FILE_OFFSET:
            _FILE_OFFSET = 0  # file rotated/truncated -> re-read from the top (id-dedup guards)
        if size <= _FILE_OFFSET:
            return
        with open(_PATH, "rb") as fh:
            fh.seek(_FILE_OFFSET)
            raw = fh.read()
        nl = raw.rfind(b"\n")
        if nl == -1:
            return  # no complete line yet (a write is mid-flight) — try again next read
        _FILE_OFFSET += nl + 1
        have = {e.get("id") for e in _RING}
        for ln in raw[:nl + 1].decode("utf-8", "ignore").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                ev = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(ev, dict) or ev.get("id") in have:
                continue  # malformed, or our OWN event already in the ring
            _SEQ += 1
            ev["seq"] = _SEQ  # reassign: on-disk seq is per-writer-process, not global
            _RING.append(ev)
            _index_agg(ev)
            have.add(ev.get("id"))
    except Exception:  # noqa: BLE001
        pass


def _maybe_rotate() -> None:
    """When the JSONL exceeds _MAX_BYTES, move it to a .1 backup and start fresh so the shared
    volume can't fill over months. The in-memory ring is unaffected. Must be called under _LOCK.
    Best-effort; never raises."""
    global _FILE_OFFSET
    try:
        if _PATH is None or not _PATH.exists():
            return
        if _PATH.stat().st_size < _MAX_BYTES:
            return
        os.replace(_PATH, _PATH.with_name(_PATH.name + ".1"))
        _FILE_OFFSET = 0
    except Exception:  # noqa: BLE001
        pass


def record(level: str, source: str, message: str, *, tenant_id: str = "",
           call_id: str = "", error_type: str = "", context: dict | None = None) -> dict | None:
    """Record one event. Returns the stored event dict, or None if the store is dormant or
    anything failed. NEVER raises — safe to call from the hottest path."""
    try:
        if not _READY or _PATH is None:
            return None
        lvl = (level or "info").strip().lower()
        if lvl not in _LEVEL_RANK:
            lvl = "info"
        fp = _fingerprint(lvl, source or "", message or "", error_type or "")
        global _SEQ
        with _LOCK:
            _SEQ += 1
            ev = {
                "id": uuid.uuid4().hex[:12],
                "seq": _SEQ,
                "ts": _utc_iso(),
                "level": lvl,
                "source": (source or "system")[:80],
                "message": (message or "")[:2000],
                "error_type": (error_type or "")[:120],
                "tenant_id": tenant_id or "",
                "call_id": call_id or "",
                "fingerprint": fp,
                "context": _safe_context(context),
            }
            # persist (append-only) then ring + aggregate
            try:
                _maybe_rotate()
                with open(_PATH, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
            except Exception:  # noqa: BLE001
                pass
            _RING.append(ev)
            _index_agg(ev)
        # side effects OUTSIDE the lock: telegram alert (throttled, best-effort)
        if _LEVEL_RANK[lvl] >= _ALERT_MIN_RANK:
            _maybe_telegram(ev)
        return ev
    except Exception:  # noqa: BLE001
        return None


def _safe_context(context: dict | None) -> dict:
    """Bound the context so a giant payload can't bloat the log line. Never raises."""
    if not isinstance(context, dict):
        return {}
    out: dict = {}
    try:
        for k, v in list(context.items())[:25]:
            ks = str(k)[:60]
            if isinstance(v, (str, int, float, bool)) or v is None:
                out[ks] = (v[:500] if isinstance(v, str) else v)
            else:
                out[ks] = str(v)[:500]
    except Exception:  # noqa: BLE001
        return {}
    return out


def _matches(ev: dict, *, level: str, source: str, tenant_id: str, q: str, since: str) -> bool:
    if level and (ev.get("level") or "") != level:
        return False
    if source and source.lower() not in (ev.get("source") or "").lower():
        return False
    if tenant_id and (ev.get("tenant_id") or "") != tenant_id:
        return False
    if since and (ev.get("ts") or "") < since:
        return False
    if q:
        ql = q.lower()
        hay = f"{ev.get('message','')} {ev.get('source','')} {ev.get('error_type','')} {ev.get('call_id','')}".lower()
        if ql not in hay:
            return False
    return True


def tail(*, limit: int = 100, offset: int = 0, level: str = "", source: str = "",
         tenant_id: str = "", q: str = "", since: str = "") -> dict:
    """Newest-first filtered event list. `tenant_id` set => scope to that tenant (a tenant
    can only ever see its own); empty => all (super-admin). Never raises."""
    try:
        lvl = (level or "").strip().lower()
        if lvl and lvl not in _LEVEL_RANK:
            lvl = ""
        with _LOCK:
            _sync_from_disk()
            rows = list(_RING)
            agg = dict(_AGG)
        rows.reverse()  # newest first
        filt = [e for e in rows if _matches(e, level=lvl, source=source,
                                            tenant_id=tenant_id, q=q, since=since)]
        total = len(filt)
        # shallow-copy the page rows so we can attach the aggregate repeat-count badge
        # WITHOUT mutating the shared in-memory ring objects.
        page = [dict(e) for e in filt[offset:offset + max(1, min(limit, 500))]]
        for e in page:
            a = agg.get(e.get("fingerprint") or "")
            if a:
                e["count"] = a.get("count", 1)
        return {"events": page, "total": total, "limit": limit, "offset": offset}
    except Exception:  # noqa: BLE001
        return {"events": [], "total": 0, "limit": limit, "offset": offset}


def summary(*, tenant_id: str = "") -> dict:
    """Counts by level + last-24h error rate + the top recurring errors. Never raises."""
    try:
        with _LOCK:
            _sync_from_disk()
            rows = list(_RING)
            agg = dict(_AGG)
        if tenant_id:
            rows = [e for e in rows if (e.get("tenant_id") or "") == tenant_id]
        by_level = {lv: 0 for lv in LEVELS}
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        last24 = 0
        errs24 = 0
        for e in rows:
            lv = e.get("level") or "info"
            by_level[lv] = by_level.get(lv, 0) + 1
            if (e.get("ts") or "") >= cutoff:
                last24 += 1
                if _LEVEL_RANK.get(lv, 0) >= _ALERT_MIN_RANK:
                    errs24 += 1
        # top recurring (by aggregate count), scoped if a tenant
        top = []
        seen = {}
        for e in reversed(rows):  # newest first to grab a representative message
            fp = e.get("fingerprint") or ""
            if not fp or fp in seen:
                continue
            seen[fp] = True
            a = agg.get(fp) or {}
            top.append({
                "fingerprint": fp,
                "level": e.get("level"),
                "source": e.get("source"),
                "message": e.get("message", "")[:200],
                "count": a.get("count", 1),
                "last_seen": a.get("last_seen", e.get("ts")),
                "last_id": a.get("last_id", e.get("id")),
            })
        top.sort(key=lambda x: x["count"], reverse=True)
        return {
            "by_level": by_level,
            "total": len(rows),
            "last_24h": last24,
            "errors_24h": errs24,
            "top_errors": top[:12],
        }
    except Exception:  # noqa: BLE001
        return {"by_level": {lv: 0 for lv in LEVELS}, "total": 0, "last_24h": 0,
                "errors_24h": 0, "top_errors": []}


def get(event_id: str, *, tenant_id: str = "") -> dict | None:
    """Fetch one event by id (+ its aggregate count). Tenant-scoped. Never raises."""
    try:
        with _LOCK:
            _sync_from_disk()
            rows = list(_RING)
            agg = dict(_AGG)
        for e in reversed(rows):
            if e.get("id") == event_id:
                if tenant_id and (e.get("tenant_id") or "") != tenant_id:
                    return None
                out = dict(e)
                a = agg.get(e.get("fingerprint") or "") or {}
                out["count"] = a.get("count", 1)
                out["first_seen"] = a.get("first_seen", e.get("ts"))
                out["last_seen"] = a.get("last_seen", e.get("ts"))
                out["suggestion"] = _FIXES.get(e.get("fingerprint") or "", "")
                return out
        return None
    except Exception:  # noqa: BLE001
        return None


def notifications(*, after_seq: int = 0, limit: int = 30, tenant_id: str = "") -> dict:
    """Feed for the panel's notification bell: the most recent events + the latest seq, plus
    how many are NEWER than `after_seq` (the client's last-seen cursor in localStorage). The
    client computes the unread badge from `unread`; no server-side read-state. Never raises."""
    try:
        with _LOCK:
            _sync_from_disk()
            rows = list(_RING)
            cur = _SEQ
        rows.reverse()
        if tenant_id:
            rows = [e for e in rows if (e.get("tenant_id") or "") == tenant_id]
        recent = rows[:max(1, min(limit, 100))]
        unread = sum(1 for e in rows if int(e.get("seq", 0) or 0) > int(after_seq or 0))
        # for the bell we emphasise problems: count unread that are error/critical
        unread_err = sum(1 for e in rows if int(e.get("seq", 0) or 0) > int(after_seq or 0)
                         and _LEVEL_RANK.get(e.get("level") or "info", 0) >= _ALERT_MIN_RANK)
        return {"events": recent, "latest_seq": cur, "unread": unread, "unread_errors": unread_err}
    except Exception:  # noqa: BLE001
        return {"events": [], "latest_seq": 0, "unread": 0, "unread_errors": 0}


def health() -> dict:
    """Operator self-test: is the store LIVE, where does it write, can it actually write, how many
    events are buffered, and the current seq. Backs /admin/logs/health so an operator can answer
    the #1 question — 'is logging even on?' — in one click. The writability probe touches a SIBLING
    temp file (never the live JSONL) so it cannot corrupt the log. Never raises."""
    try:
        with _LOCK:
            path = str(_PATH) if _PATH is not None else ""
            ready = bool(_READY and _PATH is not None)
            ring_count = len(_RING)
            seq = _SEQ
            agg_groups = len(_AGG)
        file_exists = False
        file_bytes = 0
        writable = False
        if _PATH is not None:
            try:
                file_exists = _PATH.exists()
                file_bytes = _PATH.stat().st_size if file_exists else 0
            except Exception:  # noqa: BLE001
                pass
            try:  # probe a sibling temp file — proves the volume is writable WITHOUT touching the log
                probe = _PATH.with_name(".write_probe")
                probe.write_text("ok", encoding="utf-8")
                probe.unlink()
                writable = True
            except Exception:  # noqa: BLE001
                writable = False
        return {"ready": ready, "path": path, "writable": writable,
                "file_exists": file_exists, "file_bytes": file_bytes,
                "ring_count": ring_count, "agg_groups": agg_groups, "latest_seq": seq,
                "telegram": bool((os.getenv("ALERT_TELEGRAM_BOT_TOKEN")
                                  or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
                                 and (os.getenv("ALERT_TELEGRAM_CHAT_ID") or "").strip()),
                "ai_fix": bool((os.getenv("GROQ_API_KEY") or "").strip())}
    except Exception:  # noqa: BLE001
        return {"ready": False, "path": "", "writable": False, "file_exists": False,
                "file_bytes": 0, "ring_count": 0, "agg_groups": 0, "latest_seq": 0,
                "telegram": False, "ai_fix": False}


# ── AI fix-suggestion (Groq, lazy + cached per fingerprint) ───────────────────
def suggest_fix(event_id: str, *, tenant_id: str = "", force: bool = False) -> str:
    """Return (generating + caching on first use) a short 'why it happened + how to fix'
    for the event's fingerprint, via Groq. Cached per fingerprint and persisted. Returns ""
    when no Groq key is configured or on any failure. Never raises."""
    try:
        ev = get(event_id, tenant_id=tenant_id)
        if not ev:
            return ""
        fp = ev.get("fingerprint") or ""
        cached = _FIXES.get(fp)
        if cached and not force:
            return cached  # the "Regenerate" button passes force=True to bypass this + re-ask the LLM
        key = (os.getenv("GROQ_API_KEY") or "").strip()
        if not key or not fp:
            return ""
        prompt = (
            "You are a senior SRE for 'Haptica', an AI voice-telecaller + dashboard platform "
            "(FastAPI backend, LiveKit voice agent with Groq LLM + Sarvam STT + ElevenLabs TTS, "
            "Next.js panel). Diagnose ONE production event.\n"
            "GROUND YOUR ANSWER STRICTLY in the event's source / error_type / message / path below — "
            "do NOT assume the voice agent, Groq, or any provider is the cause unless the event "
            "explicitly says so. Guidance: an HTTP 5xx on a backend route (path starting with /admin, "
            "/report, /campaigns, …) is almost always a backend route/module/config issue (e.g. a "
            "module not configured, a missing env var, a dependency down), NOT the live voice pipeline. "
            "A 503 usually means a feature/dependency isn't configured yet. A 502 on an LLM-drafting "
            "route usually means a missing/invalid API key or an upstream timeout.\n"
            "Reply in plain English:\n"
            "WHY: one short sentence on the most likely root cause, specific to THIS path/error.\n"
            "FIX: 2-4 concrete, ordered steps for the named route/module.\n"
            "No preamble, no markdown other than the WHY:/FIX: labels.\n\n"
            f"level: {ev.get('level')}\nsource: {ev.get('source')}\n"
            f"error_type: {ev.get('error_type')}\nmessage: {ev.get('message')}\n"
            f"context: {json.dumps(ev.get('context') or {}, ensure_ascii=False)[:800]}\n"
            f"occurrences: {ev.get('count', 1)}"
        )
        text = ""
        try:
            r = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": "Bearer " + key},
                json={
                    "model": os.getenv("LOG_SUGGEST_MODEL",
                                       os.getenv("GROQ_LLM_MODEL", "llama-3.1-8b-instant")),
                    "temperature": 0.2,
                    "max_tokens": 320,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=float(os.getenv("LOG_SUGGEST_TIMEOUT", "12")),
            )
            if r.status_code == 200:
                text = (r.json()["choices"][0]["message"]["content"] or "").strip()
        except Exception:  # noqa: BLE001
            text = ""
        if text:
            with _LOCK:
                _FIXES[fp] = text
                _persist_fixes()
        return text
    except Exception:  # noqa: BLE001
        return ""


def _persist_fixes() -> None:
    try:
        if _FIXES_PATH is None:
            return
        tmp = _FIXES_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(_FIXES, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, _FIXES_PATH)
    except Exception:  # noqa: BLE001
        pass


# ── Telegram push (direct minimal Bot API, env-gated, throttled) ──────────────
def _maybe_telegram(ev: dict) -> None:
    """Push an error/critical event to the OPERATOR's Telegram, if configured. Self-contained
    (a direct sendMessage) so it never depends on the per-tenant comm engine. Throttled per
    fingerprint so a recurring error alerts at most once per window. Best-effort; never raises."""
    try:
        token = (os.getenv("ALERT_TELEGRAM_BOT_TOKEN")
                 or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        chat = (os.getenv("ALERT_TELEGRAM_CHAT_ID") or "").strip()
        if not token or not chat:
            return  # dormant -> no network I/O
        fp = ev.get("fingerprint") or ""
        now = time.time()
        window = float(os.getenv("ALERT_TELEGRAM_THROTTLE_S", "900"))
        with _LOCK:
            last = _TG_LAST.get(fp, 0.0)
            if last and (now - last) < window:
                return
            _TG_LAST[fp] = now
        icon = "🛑" if ev.get("level") == "critical" else "⚠️"
        panel = (os.getenv("PANEL_BASE_URL") or os.getenv("FRONTEND_URL")
                 or "https://haptica.famit.in").rstrip("/")
        lines = [
            f"{icon} Haptica {ev.get('level','').upper()} — {ev.get('source','system')}",
            (ev.get("message") or "")[:400],
        ]
        if ev.get("error_type"):
            lines.append(f"type: {ev.get('error_type')}")
        if ev.get("tenant_id"):
            lines.append(f"tenant: {ev.get('tenant_id')}")
        if ev.get("call_id"):
            lines.append(f"call: {ev.get('call_id')}")
        lines.append(f"{panel}/super-admin/system-logs")
        text = "\n".join(lines)
        timeout = float(os.getenv("ALERT_TELEGRAM_TIMEOUT", "6"))

        # Fire the network call on a DAEMON THREAD so a slow/hung Telegram API can NEVER block
        # the caller — critically the backend's asyncio event loop (record() is invoked inline
        # from the error-capture middleware + sync _log_event helpers).
        def _post() -> None:
            try:
                httpx.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat, "text": text, "disable_web_page_preview": True},
                    timeout=timeout,
                )
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=_post, daemon=True).start()
    except Exception:  # noqa: BLE001
        pass
