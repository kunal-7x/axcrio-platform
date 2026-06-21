"""ai_manager.registry — the registered-phone-number store + per-number permission grants (spec §5.1).

A manager registers their phone (caller-ID) ONCE, ownership-verified by an OTP at registration, before it
can command anything. Each number row carries: tenant_id, role, verify_mode, a per-number capability
allow-list (`grants`), and a status (active|locked|revoked). The effective permission for an action =
`role allows` AND `grants allows` (computed in identity.permits).

STORAGE: append-only JSONL with last-write-wins on `number_id` (same posture audit.py + workforce.store
take for their JSONL). Authoritative on the control-plane API box (this module sits WITH the foundation —
see AI_MANAGER_STATE correction #1). Tenant scoping is enforced IN-CODE on every read (rows filtered by
tenant_id); a future PG migration would use db.engine.session(org_id) RLS exactly like crm/core.py.

IMPORT-SAFE: no hard deps (stdlib only). NEVER raises on a read; a write failure is swallowed-and-reported
(returns ok:False) so a logging/disk error never crashes the request.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from . import config as _config

_IST = timezone(timedelta(hours=5, minutes=30))
_LOCK = threading.Lock()

# The set of capability families a number can be granted (mirrors the workforce tool-scope families).
KNOWN_GRANTS = (
    "campaigns", "leads", "calls", "whatsapp", "ads", "ads:read", "analytics", "contacts", "billing",
)
ROLES = ("manager", "admin", "operator")
VERIFY_MODES = ("voice_pin", "otp")
STATUSES = ("active", "locked", "revoked")


# ---------------- phone canonicalization (single source; mirrors crm.canonical_phone intent) -----------
def canonical_phone(phone: str) -> str:
    """Canonicalize a caller-ID to a stable lookup key: keep '+' + digits only, lowercase-free.
    Caller-ID match is by this canonical form so '+91 98XXX', '+9198XXX', '9198XXX' collapse to one.
    Returns '' for empty/garbage. NEVER raises."""
    if not phone:
        return ""
    s = str(phone).strip()
    plus = s.startswith("+")
    digits = re.sub(r"\D", "", s)
    if not digits:
        return ""
    return ("+" if plus else "") + digits


def _now_iso() -> str:
    return datetime.now(_IST).isoformat(timespec="seconds")


def _file() -> Path:
    return _config.numbers_file()


# ---------------- low-level JSONL read/append (last-write-wins on number_id) ----------------
def _read_all() -> dict:
    """Return {number_id: row} folding the append-only log (last write wins). NEVER raises."""
    out: dict[str, dict] = {}
    f = _file()
    try:
        if f.exists():
            with open(f, "r", encoding="utf-8") as fh:
                for ln in fh:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        row = json.loads(ln)
                    except Exception:  # noqa: BLE001
                        continue
                    nid = row.get("number_id")
                    if nid:
                        out[nid] = row
    except Exception:  # noqa: BLE001
        pass
    return out


def _append(row: dict) -> bool:
    f = _file()
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, ensure_ascii=False)
        with _LOCK:
            with open(f, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return True
    except Exception:  # noqa: BLE001
        return False


def available() -> bool:
    """The registry is always available (file-backed, stdlib). Reads degrade to empty if no file."""
    return True


# ---------------- public API ----------------
def register(*, tenant_id: str, phone: str, label: str = "", role: str = "manager",
             verify_mode: str = "voice_pin", grants: Optional[list] = None,
             registered_by: str = "", verified: bool = False) -> dict:
    """Register a manager phone. Returns the created row (with ok). Ownership-verification (the OTP at
    registration) is a SEPARATE step (mark_verified) — a number is NOT usable until verified=True.
    tenant_id MUST come from the authenticated request (never a model/body field — P1/RT-3)."""
    phone_c = canonical_phone(phone)
    if not tenant_id or not phone_c:
        return {"ok": False, "reason": "tenant_id and a valid phone are required"}
    role = role if role in ROLES else "manager"
    verify_mode = verify_mode if verify_mode in VERIFY_MODES else "voice_pin"
    g = [x for x in (grants or []) if x in KNOWN_GRANTS] or ["analytics"]
    row = {
        "number_id": "num_" + uuid.uuid4().hex[:12],
        "tenant_id": tenant_id,
        "phone": phone_c,
        "label": label or "",
        "role": role,
        "verify_mode": verify_mode,
        "grants": g,
        "verified": bool(verified),
        "status": "active",
        "registered_by": registered_by or "",
        "registered_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    ok = _append(row)
    return {"ok": ok, **row}


def _upsert(row: dict) -> bool:
    row = dict(row)
    row["updated_at"] = _now_iso()
    return _append(row)


def lookup(phone: str, *, tenant_id: Optional[str] = None) -> Optional[dict]:
    """caller-ID -> active+verified number record (spec §3.2 lookup hop). Returns None if not found,
    not verified, or not active. If tenant_id is given, the row MUST belong to it (defense in depth)."""
    phone_c = canonical_phone(phone)
    if not phone_c:
        return None
    for row in _read_all().values():
        if row.get("phone") != phone_c:
            continue
        if tenant_id is not None and row.get("tenant_id") != tenant_id:
            continue
        if not row.get("verified") or row.get("status") != "active":
            return None
        return dict(row)
    return None


def get(number_id: str, *, tenant_id: str) -> Optional[dict]:
    """Fetch a number by id, TENANT-SCOPED. Returns None if it doesn't belong to tenant_id."""
    row = _read_all().get(number_id)
    if not row or row.get("tenant_id") != tenant_id:
        return None
    return dict(row)


def list_numbers(tenant_id: str) -> list[dict]:
    """All numbers for a tenant (PIN/secret-free rows). TENANT-SCOPED."""
    return [dict(r) for r in _read_all().values() if r.get("tenant_id") == tenant_id]


def mark_verified(number_id: str, *, tenant_id: str) -> dict:
    """Confirm ownership-OTP -> flip verified=True. TENANT-SCOPED."""
    row = get(number_id, tenant_id=tenant_id)
    if not row:
        return {"ok": False, "reason": "not_found"}
    row["verified"] = True
    return {"ok": _upsert(row), **row}


def set_grants(number_id: str, *, tenant_id: str, grants: list) -> dict:
    """Replace a number's capability allow-list. TENANT-SCOPED. Unknown grants are dropped."""
    row = get(number_id, tenant_id=tenant_id)
    if not row:
        return {"ok": False, "reason": "not_found"}
    row["grants"] = [x for x in (grants or []) if x in KNOWN_GRANTS]
    return {"ok": _upsert(row), **row}


def set_status(number_id: str, *, tenant_id: str, status: str) -> dict:
    """Set a number's status (active|locked|revoked). TENANT-SCOPED."""
    if status not in STATUSES:
        return {"ok": False, "reason": "bad_status"}
    row = get(number_id, tenant_id=tenant_id)
    if not row:
        return {"ok": False, "reason": "not_found"}
    row["status"] = status
    return {"ok": _upsert(row), **row}


def revoke(number_id: str, *, tenant_id: str) -> dict:
    return set_status(number_id, tenant_id=tenant_id, status="revoked")


def lock(number_id: str, *, tenant_id: str, ttl_s: Optional[int] = None) -> dict:
    """Lock a number (lockout after N PIN fails). Records a locked_until for a TTL-based auto-unlock read."""
    row = get(number_id, tenant_id=tenant_id)
    if not row:
        return {"ok": False, "reason": "not_found"}
    row["status"] = "locked"
    row["locked_until"] = int(time.time()) + int(ttl_s if ttl_s is not None else _config.lock_ttl_s())
    return {"ok": _upsert(row), **row}
