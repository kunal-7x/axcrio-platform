"""ai_manager.team — the AUTHORIZED-USERS (team-member) store (R6b panel "Team" card).

A team member = a named person allowed to command the AI Manager, with a role + a per-person capability
allow-list (`permissions`) + their OWN step-up PIN status. This is SEPARATE from registry.py (which stores
the registered phone NUMBERS / caller-IDs). The panel Team card reads/writes GET/POST/PATCH/DELETE
`/ai-manager/authorized-users`; before this store those routes 404'd and the card stayed dormant, so the
"Add" button was disabled -> "does nothing". This makes the Team card fully live.

STORAGE: append-only JSONL with last-write-wins on `id` (the EXACT posture registry.py / audit.py take).
Tenant scoping is enforced IN-CODE on every read (rows filtered by tenant_id). A future PG migration would
use db.engine RLS exactly like crm/core.py.

PIN: the raw PIN is NEVER stored here. A member's PIN lives in the firewall's per-(tenant,user) salted hash
(firewall.set_pin / check_pin scoped by a stable `pin_subject`). We only persist + return the DERIVED
status fields (pin_set_at / failed_pin_attempts / locked_until) so the UI can show "Set / Not set / Locked".

IMPORT-SAFE: stdlib only. NEVER raises on a read; a write failure is swallowed-and-reported (ok:False).
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from . import config as _config
from . import registry as _registry  # reuse canonical_phone + KNOWN_GRANTS + ROLES

_IST = timezone(timedelta(hours=5, minutes=30))
_LOCK = threading.Lock()

ROLES = _registry.ROLES                 # ("manager", "admin", "operator")
KNOWN_GRANTS = _registry.KNOWN_GRANTS


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file() -> Path:
    # sibling of aim_numbers.jsonl, same var dir + override (AIM_VAR_DIR) as registry/sessions.
    return _config.var_dir() / "aim_team.jsonl"


# ---------------- low-level JSONL read/append (last-write-wins on id) ----------------
def _read_all() -> dict:
    """Return {id: row} folding the append-only log (last write wins). NEVER raises."""
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
                    rid = row.get("id")
                    if rid:
                        out[rid] = row
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


def _upsert(row: dict) -> bool:
    row = dict(row)
    row["updated_at"] = _now_iso()
    return _append(row)


# ---------------- PIN subject + firewall-derived status ----------------
def pin_subject(tenant_id: str, user_id: str) -> str:
    """Stable per-(tenant,user) firewall PIN subject. Distinct from the tenant-level step-up PIN so each
    team member can hold their own PIN without colliding."""
    return f"aim_user:{tenant_id}:{user_id}"


def _pin_status(tenant_id: str, user_id: str) -> dict:
    """Best-effort read of the firewall PIN status for this member. NEVER raises / never returns the hash.

    The firewall stores PINs keyed by an arbitrary string (`set_pin(key, pin)`); we key each team member
    by a composite `pin_subject` so per-member PINs never collide with the tenant-level step-up PIN.
    The firewall is tenant-keyed and exposes has_pin(key) + lockout_state(key) (NOT a per-subject status),
    so we derive the UI fields from those. `pin_set_at` truth comes from the locally-recorded marker we
    write in mark_pin_set (the firewall stores only an int set_at we cannot read per-key without poking the
    private store) — has_pin is the authoritative "is a PIN enrolled?" signal."""
    out = {"has_pin": False, "failed_pin_attempts": 0, "locked_until": None}
    try:
        import firewall as _fw  # type: ignore
    except Exception:  # noqa: BLE001
        return out
    subj = pin_subject(tenant_id, user_id)
    try:
        hp = getattr(_fw, "has_pin", None)
        if callable(hp):
            out["has_pin"] = bool(hp(subj))
    except Exception:  # noqa: BLE001
        pass
    try:
        ls = getattr(_fw, "lockout_state", None)
        if callable(ls):
            st = ls(subj)
            if isinstance(st, dict):
                out["failed_pin_attempts"] = int(st.get("fails") or 0)
                if st.get("locked"):
                    import time as _t
                    retry = int(st.get("retry_after_s") or 0)
                    out["locked_until"] = datetime.fromtimestamp(
                        _t.time() + retry, timezone.utc).isoformat() if retry else None
    except Exception:  # noqa: BLE001
        pass
    return out


def _hydrate(row: dict) -> dict:
    """Return a UI-facing copy with derived PIN status merged in (never the firewall hash)."""
    r = dict(row)
    tid = r.get("tenant_id", "")
    uid = r.get("id", "")
    st = _pin_status(tid, uid)
    # `has_pin` from the firewall is the AUTHORITATIVE "PIN enrolled?" signal. The locally-recorded
    # pin_set_at marker only supplies a timestamp; if the firewall has no PIN, force "Not set".
    if st["has_pin"]:
        r["pin_set_at"] = r.get("pin_set_at") or _now_iso()
    else:
        r["pin_set_at"] = None
    r["failed_pin_attempts"] = st["failed_pin_attempts"] or int(r.get("failed_pin_attempts") or 0)
    r["locked_until"] = st["locked_until"] or r.get("locked_until")
    r.pop("pin_hash", None)  # defensive: never leak a hash if one ever lands in the row
    return r


# ---------------- public API ----------------
def available() -> bool:
    return True


def list_users(tenant_id: str) -> list[dict]:
    """All team members for a tenant (PIN-status only, never the hash). TENANT-SCOPED. Excludes deleted."""
    rows = [r for r in _read_all().values()
            if r.get("tenant_id") == tenant_id and not r.get("deleted")]
    rows.sort(key=lambda r: r.get("created_at", ""))
    return [_hydrate(r) for r in rows]


def get(user_id: str, *, tenant_id: str) -> Optional[dict]:
    """Fetch a member by id, TENANT-SCOPED. Returns the RAW row (no PIN hydrate). None if not owned."""
    row = _read_all().get(user_id)
    if not row or row.get("tenant_id") != tenant_id or row.get("deleted"):
        return None
    return dict(row)


def create_user(*, tenant_id: str, name: str, phone_number: str = "", role: str = "operator",
                permissions: Optional[list] = None) -> dict:
    """Add a team member. tenant_id MUST come from the authenticated request. Returns the created row."""
    name = (name or "").strip()
    if not tenant_id or not name:
        return {"ok": False, "reason": "tenant_id and a name are required"}
    role = role if role in ROLES else "operator"
    phone_c = _registry.canonical_phone(phone_number) if phone_number else ""
    perms = [x for x in (permissions or []) if x in KNOWN_GRANTS]
    row = {
        "id": "usr_" + uuid.uuid4().hex[:12],
        "tenant_id": tenant_id,
        "name": name,
        "phone_number": phone_c,
        "role": role,
        "permissions": perms,
        "is_active": True,
        "pin_set_at": None,
        "failed_pin_attempts": 0,
        "locked_until": None,
        "last_used_at": None,
        "deleted": False,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    ok = _append(row)
    return {"ok": ok, **_hydrate(row)}


_PATCHABLE = ("name", "phone_number", "role", "permissions", "is_active")


def patch_user(user_id: str, *, tenant_id: str, fields: dict) -> dict:
    """Update name/phone/role/permissions/is_active. TENANT-SCOPED. Ignores unknown keys."""
    row = get(user_id, tenant_id=tenant_id)
    if not row:
        return {"ok": False, "reason": "not_found"}
    f = fields or {}
    if "name" in f and str(f["name"]).strip():
        row["name"] = str(f["name"]).strip()
    if "phone_number" in f:
        row["phone_number"] = _registry.canonical_phone(f["phone_number"]) if f["phone_number"] else ""
    if "role" in f and f["role"] in ROLES:
        row["role"] = f["role"]
    if "permissions" in f and isinstance(f["permissions"], list):
        row["permissions"] = [x for x in f["permissions"] if x in KNOWN_GRANTS]
    if "is_active" in f:
        row["is_active"] = bool(f["is_active"])
    return {"ok": _upsert(row), **_hydrate(row)}


def delete_user(user_id: str, *, tenant_id: str) -> dict:
    """Soft-delete (tombstone) a member. TENANT-SCOPED. The member's firewall PIN subject is left orphaned
    (the firewall has no clear_pin; an orphaned per-member hash is harmless and unreachable once the row is
    tombstoned — a re-created member gets a fresh subject id)."""
    row = get(user_id, tenant_id=tenant_id)
    if not row:
        return {"ok": False, "reason": "not_found"}
    row["deleted"] = True
    row["is_active"] = False
    return {"ok": _upsert(row)}


def mark_pin_set(user_id: str, *, tenant_id: str) -> dict:
    """Record a local pin_set_at marker (so the UI flips to 'Set' instantly even if the firewall status
    read lags). Resets the failed-attempts marker + lockout. TENANT-SCOPED. NEVER stores the PIN itself."""
    row = get(user_id, tenant_id=tenant_id)
    if not row:
        return {"ok": False, "reason": "not_found"}
    row["pin_set_at"] = _now_iso()
    row["failed_pin_attempts"] = 0
    row["locked_until"] = None
    return {"ok": _upsert(row), **_hydrate(row)}


def touch_used(user_id: str, *, tenant_id: str) -> None:
    """Best-effort last_used_at bump (called when a member issues a command). NEVER raises."""
    try:
        row = get(user_id, tenant_id=tenant_id)
        if row:
            row["last_used_at"] = _now_iso()
            _upsert(row)
    except Exception:  # noqa: BLE001
        pass


# ════════════════════════════ AI-MANAGER PROFILE (settings) ════════════════════════════
# Per-tenant settings the panel Settings card reads/writes (GET/PUT /ai-manager/profile). Stored in its
# OWN append-only JSONL (last-write-wins on tenant_id) so it never touches the team rows. Defaults mirror
# the FE AIM_PROFILE_DEFAULTS so an un-configured tenant renders sensible values instead of a dormant card.
_PROFILE_DEFAULTS = {
    "assistant_name": "AI Manager",
    "language": "hinglish",
    "voice_provider": "elevenlabs",
    "timezone": "Asia/Kolkata",
    "require_pin_for_level": "L3",
    "confirm_destructive": True,
    "max_bulk_leads_without_pin": 50,
    "daily_spend_cap_paise": None,
    "quiet_hours_start": None,
    "quiet_hours_end": None,
}
_PROFILE_KEYS = tuple(_PROFILE_DEFAULTS.keys())


def _profile_file() -> Path:
    return _config.var_dir() / "aim_profile.jsonl"


def _read_profiles() -> dict:
    out: dict[str, dict] = {}
    f = _profile_file()
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
                    tid = row.get("tenant_id")
                    if tid:
                        out[tid] = row
    except Exception:  # noqa: BLE001
        pass
    return out


def get_profile(tenant_id: str) -> dict:
    """Return the tenant's profile merged over defaults. NEVER raises. TENANT-SCOPED."""
    row = _read_profiles().get(tenant_id, {})
    out = dict(_PROFILE_DEFAULTS)
    for k in _PROFILE_KEYS:
        if k in row:
            out[k] = row[k]
    out["tenant_id"] = tenant_id
    return out


def put_profile(tenant_id: str, fields: dict) -> dict:
    """Merge-update the tenant's profile (only known keys). TENANT-SCOPED. Returns the full merged profile."""
    if not tenant_id:
        return {"ok": False, "reason": "tenant_id required"}
    cur = _read_profiles().get(tenant_id, {})
    merged = dict(cur)
    merged["tenant_id"] = tenant_id
    for k in _PROFILE_KEYS:
        if k in (fields or {}):
            merged[k] = fields[k]
    merged["updated_at"] = _now_iso()
    f = _profile_file()
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            with open(f, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(merged, ensure_ascii=False) + "\n")
        ok = True
    except Exception:  # noqa: BLE001
        ok = False
    res = get_profile(tenant_id)
    res["ok"] = ok
    return res
