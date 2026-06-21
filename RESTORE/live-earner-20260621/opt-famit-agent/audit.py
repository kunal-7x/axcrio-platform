"""audit.py — Famit P0 append-only immutable audit log (ADDITIVE).

Records every mutating action to an append-only JSONL file
(`var/audit_log.jsonl`). Each line is one self-contained JSON event:

    {"ts": "2026-06-04T12:00:00+05:30", "epoch": 1780600000.12,
     "actor": "<tenant_id>", "actor_role": "manager",
     "action": "campaign.create", "object_type": "campaign",
     "object_id": "abc123", "ip": "1.2.3.4", "channel": "api",
     "tenant_id": "<tenant_id>", "meta": {...}}

Immutability: the file is only ever APPENDED to (open mode "a"); existing lines
are never rewritten. (A move to Postgres — append-only table or WORM storage —
is noted as a later follow-up.) Best-effort: a logging failure must NEVER break
the mutating endpoint that called it, so `record()` swallows all exceptions.

Reads (`tail`) parse the file line-by-line and return newest-first, with simple
offset/limit pagination and optional tenant scoping for the read-only `GET /audit`
admin endpoint.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

_IST = timezone(timedelta(hours=5, minutes=30))
_LOCK = threading.Lock()          # serialize appends within this process
_AUDIT_FILE: Optional[Path] = None
_MAX_BYTES = 50 * 1024 * 1024     # soft cap; rotate-on-size to .1 (keeps it bounded)


def init(audit_file: Path) -> None:
    """Point the logger at its JSONL file (called once from caller.py)."""
    global _AUDIT_FILE
    _AUDIT_FILE = Path(audit_file)
    try:
        _AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass


def _rotate_if_big() -> None:
    try:
        if _AUDIT_FILE and _AUDIT_FILE.exists() and _AUDIT_FILE.stat().st_size > _MAX_BYTES:
            bak = _AUDIT_FILE.with_suffix(_AUDIT_FILE.suffix + ".1")
            try:
                if bak.exists():
                    bak.unlink()
            except Exception:  # noqa: BLE001
                pass
            _AUDIT_FILE.rename(bak)
    except Exception:  # noqa: BLE001
        pass


def record(actor: str,
           action: str,
           object_type: str = "",
           object_id: str = "",
           ip: str = "",
           channel: str = "api",
           tenant_id: Optional[str] = None,
           actor_role: str = "",
           meta: Optional[dict] = None) -> None:
    """Append one audit event. NEVER raises (best-effort). `actor` is the acting
    tenant/user id; `tenant_id` defaults to actor (the data owner). `channel` is
    api|call|whatsapp|system. `meta` is an optional small dict of extra context."""
    if _AUDIT_FILE is None:
        return
    ev = {
        "ts": datetime.now(_IST).isoformat(timespec="seconds"),
        "epoch": round(time.time(), 3),
        "actor": actor or "",
        "actor_role": actor_role or "",
        "action": action or "",
        "object_type": object_type or "",
        "object_id": str(object_id or ""),
        "ip": ip or "",
        "channel": channel or "api",
        "tenant_id": (tenant_id if tenant_id is not None else (actor or "")),
    }
    if meta:
        try:
            json.dumps(meta)  # ensure serializable; else drop
            ev["meta"] = meta
        except Exception:  # noqa: BLE001
            pass
    line = json.dumps(ev, ensure_ascii=False)
    try:
        with _LOCK:
            _rotate_if_big()
            with open(_AUDIT_FILE, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except Exception:  # noqa: BLE001
        pass  # auditing must never break the request
    # P1 DUAL MIRROR (best-effort, additive): after the authoritative JSONL append, mirror this event
    # to the Postgres `events` table. store.mirror_event is a no-op unless events is flipped to dual in
    # STORE_MODES AND the PG layer is up; it runs the insert OFF the loop thread and SWALLOWS all errors
    # (auditing must never break the request). Lazy import keeps audit.py dependency-free when store is
    # absent. Content-hash PK + ON CONFLICT DO NOTHING => idempotent vs backfill + re-runs (append-only).
    try:
        import store as _store
        _store.mirror_event(ev)
    except Exception:  # noqa: BLE001
        pass


def tail(limit: int = 100,
         offset: int = 0,
         tenant_id: Optional[str] = None,
         action_prefix: str = "",
         channel: str = "") -> dict:
    """Return newest-first audit rows with pagination. If `tenant_id` is given,
    only that tenant's rows are returned (admin endpoint passes None to see all).
    `action_prefix` optionally filters by action (e.g. 'campaign'). `channel`
    optionally filters by channel (e.g. 'ai' for AI-decision rows — F4 §7)."""
    rows: list[dict] = []
    try:
        if _AUDIT_FILE and _AUDIT_FILE.exists():
            with open(_AUDIT_FILE, "r", encoding="utf-8") as fh:
                for ln in fh:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        ev = json.loads(ln)
                    except Exception:  # noqa: BLE001
                        continue
                    if tenant_id is not None and ev.get("tenant_id") != tenant_id:
                        continue
                    if action_prefix and not str(ev.get("action", "")).startswith(action_prefix):
                        continue
                    if channel and str(ev.get("channel", "")) != channel:
                        continue
                    rows.append(ev)
    except Exception:  # noqa: BLE001
        pass
    rows.reverse()  # newest first
    total = len(rows)
    try:
        limit = max(1, min(int(limit), 1000))
        offset = max(0, int(offset))
    except Exception:  # noqa: BLE001
        limit, offset = 100, 0
    page = rows[offset:offset + limit]
    return {"events": page, "total": total, "limit": limit, "offset": offset}
