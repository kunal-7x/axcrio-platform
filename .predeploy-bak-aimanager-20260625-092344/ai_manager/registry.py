"""ai_manager.registry — authorized-number registry (spec §E, security-critical caller-ID resolution).

The registry is the SOURCE OF TRUTH for "which phone may issue commands, as which tenant, with what
role/grants/verify-mode". The voice machine resolves an inbound caller-ID against it (S1 VERIFY), the
dashboard manages it (register/verify/grants/revoke), and the state machine locks a number after N PIN
failures. Caller-ID alone NEVER grants access — it only resolves WHO is calling; the PIN/OTP (S2) proves
the human. So this module reveals nothing secret: no PIN, no hash, no token ever stored/returned here.

House pattern (mirror grow/store.py + provider_registry/store.py): a dependency-free, thread-safe
InMemory dict (the tested + dormant default) plus a best-effort lazy `_Pg` backend that rides the shared
`db.engine` spine (RLS GUCs per session) — ZERO sqlalchemy at import. When `db.engine` is absent (this
local box), every read/write degrades to InMemory; nothing crashes. Phone validation + caller-ID matching
go through `identity.canonical_phone` / `identity.match_forms` (lazy import).

TENANT IS ALWAYS THE ARG. Every fn except `lookup()` is tenant-scoped and fail-closed on a blank tenant.
`lookup()` is the ONLY cross-tenant function (service-token gated at the endpoint) — it resolves an inbound
caller-ID across all tenants and returns the minimal row needed to start a session. Nothing here raises.
Backing table: ai_manager_authorized_users (grants live in the `permissions` JSONB column as a list).
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from typing import Any, Optional

log = logging.getLogger("ai_manager.registry")

# Roles that may appear on a number row (mirrors the frontend AimNumber.role union + owner/admin elevation).
_KNOWN_ROLES = {"owner", "admin", "manager", "operator", "viewer", "member"}
_DEFAULT_ROLE = "manager"
_DEFAULT_VERIFY = "voice_pin"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _ok(tenant_id: str) -> bool:
    return bool((tenant_id or "").strip())


def _identity():
    """Lazy import of the sibling identity module (phone-norm + caller-ID match forms). Never raises."""
    try:
        from . import identity as _id  # type: ignore
        return _id
    except Exception:  # noqa: BLE001
        return None


def _canon(phone: str) -> str:
    """Normalize a phone to +91 E.164 via identity; degrade to a best-effort strip when identity absent."""
    idn = _identity()
    if idn is not None:
        try:
            return idn.canonical_phone(phone or "")
        except Exception:  # noqa: BLE001
            pass
    # degraded fallback: keep digits, prefix '+' (NEVER raise) — identity should normally be present.
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    return ("+" + digits) if digits else ""


def _match_forms(phone: str) -> set:
    """The equivalence set for caller-ID matching (canonical, bare10, 0+bare10, 91+bare10)."""
    idn = _identity()
    if idn is not None:
        try:
            return set(idn.match_forms(phone or ""))
        except Exception:  # noqa: BLE001
            pass
    c = _canon(phone)
    return {c} if c else set()


def _new_number_id() -> str:
    return "num_" + uuid.uuid4().hex[:12]


def _clean_grants(grants: Any) -> list:
    """Coerce a grants arg into a clean list[str] (drop blanks/dupes, preserve order). Never raises."""
    out: list[str] = []
    try:
        if isinstance(grants, dict):
            it = list(grants.keys())
        elif isinstance(grants, (list, tuple, set)):
            it = list(grants)
        elif grants in (None, ""):
            it = []
        else:
            it = [grants]
        seen = set()
        for g in it:
            s = str(g or "").strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    except Exception:  # noqa: BLE001
        return []
    return out


def _status_of(rec: dict) -> str:
    """Derive the public status (active|locked|revoked) from the internal flags."""
    if not rec.get("active", True):
        return "revoked"
    if rec.get("locked"):
        return "locked"
    return "active"


def _public_row(rec: dict) -> dict:
    """The tenant-facing AimNumber shape (frontend §5a) — NO secrets (no PIN/hash/token)."""
    return {
        "number_id": rec.get("number_id", ""),
        "tenant_id": rec.get("tenant_id", ""),
        "phone": rec.get("phone", ""),
        "label": rec.get("label", ""),
        "role": rec.get("role", _DEFAULT_ROLE),
        "verify_mode": rec.get("verify_mode", _DEFAULT_VERIFY),
        "grants": list(rec.get("grants", []) or []),
        "verified": bool(rec.get("verified", False)),
        "status": _status_of(rec),
        "registered_by": rec.get("registered_by", ""),
        "registered_at": rec.get("registered_at", ""),
        "updated_at": rec.get("updated_at", ""),
    }


def _resolve_row(rec: dict) -> dict:
    """The minimal caller-ID resolution row (what identity.resolve / the state machine consume).

    Carries exactly what S1 needs: tenant + number id, role, grants list, verify_mode, canonical phone.
    Cross-tenant via lookup() — still NO secret material. Inactive/revoked numbers don't resolve.
    """
    return {
        "tenant_id": rec.get("tenant_id", ""),
        "number_id": rec.get("number_id", ""),
        "role": rec.get("role", _DEFAULT_ROLE),
        "grants": list(rec.get("grants", []) or []),
        "verify_mode": rec.get("verify_mode", _DEFAULT_VERIFY),
        "phone": rec.get("phone", ""),
    }


# --------------------------------------------------------------------------- #
# InMemory backend (the tested + dormant default)
# --------------------------------------------------------------------------- #
class _InMem:
    """Thread-safe in-memory registry. Keyed by (tenant_id, number_id); a flat scan serves lookup()."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], dict] = {}
        self._lock = threading.RLock()

    def upsert_by_phone(self, tenant_id: str, canon: str, fields: dict) -> dict:
        """Idempotent on (tenant_id, canonical phone): re-registering a phone updates the SAME row."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            existing = None
            for (t, _nid), rec in self._rows.items():
                if t == tenant_id and rec.get("phone") == canon:
                    existing = rec
                    break
            if existing is None:
                nid = _new_number_id()
                rec = {
                    "number_id": nid, "tenant_id": tenant_id, "phone": canon,
                    "label": fields.get("label", ""), "role": fields.get("role", _DEFAULT_ROLE),
                    "verify_mode": fields.get("verify_mode", _DEFAULT_VERIFY),
                    "grants": list(fields.get("grants", []) or []),
                    "verified": False, "active": True, "locked": False,
                    "registered_by": fields.get("registered_by", ""),
                    "registered_at": now, "updated_at": now,
                }
                self._rows[(tenant_id, nid)] = rec
                return dict(rec)
            # update-in-place (re-register): keep id + verified + registered_at; refresh the rest.
            existing["label"] = fields.get("label", existing.get("label", ""))
            existing["role"] = fields.get("role", existing.get("role", _DEFAULT_ROLE))
            existing["verify_mode"] = fields.get("verify_mode", existing.get("verify_mode", _DEFAULT_VERIFY))
            existing["grants"] = list(fields.get("grants", existing.get("grants", [])) or [])
            existing["active"] = True
            existing["updated_at"] = now
            return dict(existing)

    def get(self, tenant_id: str, number_id: str) -> Optional[dict]:
        with self._lock:
            rec = self._rows.get((tenant_id, number_id))
            return dict(rec) if rec else None

    def patch(self, tenant_id: str, number_id: str, **fields) -> Optional[dict]:
        from datetime import datetime, timezone
        with self._lock:
            rec = self._rows.get((tenant_id, number_id))
            if rec is None:
                return None
            rec.update(fields)
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            return dict(rec)

    def list_tenant(self, tenant_id: str) -> list[dict]:
        with self._lock:
            rows = [dict(r) for (t, _nid), r in self._rows.items() if t == tenant_id]
        rows.sort(key=lambda r: r.get("registered_at", ""), reverse=True)
        return rows

    def find_by_forms(self, forms: set) -> Optional[dict]:
        """Cross-tenant scan: first ACTIVE, non-revoked, NON-LOCKED row whose phone is in the
        match set. A locked number (state-machine lockout after N PIN failures) must NOT resolve
        on caller-ID — a re-calling locked number reveals nothing, exactly like an unknown one."""
        if not forms:
            return None
        with self._lock:
            for rec in self._rows.values():
                if not rec.get("active", True):
                    continue
                if rec.get("locked"):
                    continue
                if rec.get("phone", "") in forms:
                    return dict(rec)
        return None


# --------------------------------------------------------------------------- #
# Pg backend (best-effort; rides the shared db.engine spine, ZERO sqlalchemy at import)
# --------------------------------------------------------------------------- #
class _Pg:
    """Best-effort Postgres backend over ai_manager_authorized_users. Grants live in `permissions` JSONB.

    Mirrors grow/store.py: every method self-degrades to a no-op / None / [] when db.engine is absent or a
    query fails. `available()` False → registry.py falls back to InMemory. Status is derived from
    is_active + locked_until: revoked = is_active False; locked = locked_until in the future; else active.
    """

    def _engine(self):
        try:
            from db import engine as eng  # type: ignore
            return eng if eng.available() else None
        except Exception:  # noqa: BLE001
            return None

    def available(self) -> bool:
        return self._engine() is not None

    def _text(self, sql: str):
        from sqlalchemy import text
        return text(sql)

    def _row_to_rec(self, r) -> dict:
        # r: (id, vendor_id, phone_number, normalized_phone_number, name, role, permissions,
        #     is_active, verify_mode, registered_by, locked_until, pin_set_at, created_at, updated_at)
        perms = r[6]
        grants: list = []
        if isinstance(perms, str):
            try:
                perms = json.loads(perms)
            except Exception:  # noqa: BLE001
                perms = {}
        if isinstance(perms, list):
            grants = [str(g) for g in perms]
        elif isinstance(perms, dict):
            g = perms.get("grants")
            grants = [str(x) for x in g] if isinstance(g, (list, tuple)) else list(perms.keys())
        locked = False
        try:
            if r[10] is not None:
                from datetime import datetime, timezone
                lu = r[10]
                if hasattr(lu, "timestamp"):
                    locked = lu.timestamp() > datetime.now(timezone.utc).timestamp()
        except Exception:  # noqa: BLE001
            locked = False

        def _iso(v):
            try:
                return v.isoformat() if hasattr(v, "isoformat") else (str(v) if v else "")
            except Exception:  # noqa: BLE001
                return ""

        return {
            "number_id": r[0], "tenant_id": r[1], "phone": r[3] or r[2] or "",
            "label": r[4] or "", "role": r[5] or _DEFAULT_ROLE,
            "verify_mode": r[8] or _DEFAULT_VERIFY, "grants": grants,
            "verified": bool(r[11] is not None),  # pin_set_at present ~= verified ownership
            "active": bool(r[7]), "locked": locked,
            "registered_by": r[9] or "", "registered_at": _iso(r[12]), "updated_at": _iso(r[13]),
        }

    _SEL = (
        "SELECT id, vendor_id, phone_number, normalized_phone_number, name, role, permissions, "
        "is_active, verify_mode, registered_by, locked_until, pin_set_at, created_at, updated_at "
        "FROM ai_manager_authorized_users WHERE vendor_id=:org"
    )

    def upsert_by_phone(self, tenant_id: str, canon: str, fields: dict) -> Optional[dict]:
        eng = self._engine()
        if eng is None:
            return None
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                row = s.execute(self._text(
                    self._SEL + " AND normalized_phone_number=:np LIMIT 1"
                ), {"org": tenant_id, "np": canon}).fetchone()
                grants_json = json.dumps(list(fields.get("grants", []) or []))
                if row is None:
                    nid = _new_number_id()
                    s.execute(self._text(
                        "INSERT INTO ai_manager_authorized_users "
                        "(id, vendor_id, name, phone_number, normalized_phone_number, role, "
                        " permissions, is_active, verify_mode, registered_by) "
                        "VALUES (:id,:org,:label,:ph,:np,:role,CAST(:perms AS jsonb),TRUE,:vm,:by)"
                    ), {"id": nid, "org": tenant_id, "label": fields.get("label", ""),
                        "ph": canon, "np": canon, "role": fields.get("role", _DEFAULT_ROLE),
                        "perms": grants_json, "vm": fields.get("verify_mode", _DEFAULT_VERIFY),
                        "by": fields.get("registered_by", "")})
                    rid = nid
                else:
                    rid = row[0]
                    s.execute(self._text(
                        "UPDATE ai_manager_authorized_users SET name=:label, role=:role, "
                        " verify_mode=:vm, permissions=CAST(:perms AS jsonb), is_active=TRUE, "
                        " updated_at=now() WHERE id=:id AND vendor_id=:org"
                    ), {"id": rid, "org": tenant_id, "label": fields.get("label", row[4] or ""),
                        "role": fields.get("role", row[5] or _DEFAULT_ROLE),
                        "vm": fields.get("verify_mode", row[8] or _DEFAULT_VERIFY),
                        "perms": grants_json})
                out = s.execute(self._text(self._SEL + " AND id=:id"),
                                {"org": tenant_id, "id": rid}).fetchone()
                return self._row_to_rec(out) if out else None
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_authorized_users upsert failed: %r", exc)
            return None

    def get(self, tenant_id: str, number_id: str) -> Optional[dict]:
        eng = self._engine()
        if eng is None:
            return None
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                r = s.execute(self._text(self._SEL + " AND id=:id"),
                              {"org": tenant_id, "id": number_id}).fetchone()
                return self._row_to_rec(r) if r else None
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_authorized_users get failed: %r", exc)
            return None

    def list_tenant(self, tenant_id: str) -> Optional[list[dict]]:
        eng = self._engine()
        if eng is None:
            return None
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                rows = s.execute(self._text(self._SEL + " ORDER BY created_at DESC LIMIT 1000"),
                                 {"org": tenant_id}).fetchall()
                return [self._row_to_rec(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_authorized_users list failed: %r", exc)
            return None

    def set_active(self, tenant_id: str, number_id: str, active: bool) -> Optional[dict]:
        return self._patch_sql(
            tenant_id, number_id,
            "UPDATE ai_manager_authorized_users SET is_active=:active, updated_at=now() "
            "WHERE id=:id AND vendor_id=:org",
            {"active": bool(active)})

    def set_verified(self, tenant_id: str, number_id: str) -> Optional[dict]:
        return self._patch_sql(
            tenant_id, number_id,
            "UPDATE ai_manager_authorized_users SET pin_set_at=COALESCE(pin_set_at, now()), "
            "updated_at=now() WHERE id=:id AND vendor_id=:org", {})

    def set_grants(self, tenant_id: str, number_id: str, grants: list) -> Optional[dict]:
        return self._patch_sql(
            tenant_id, number_id,
            "UPDATE ai_manager_authorized_users SET permissions=CAST(:perms AS jsonb), "
            "updated_at=now() WHERE id=:id AND vendor_id=:org",
            {"perms": json.dumps(list(grants or []))})

    def lock(self, tenant_id: str, number_id: str) -> Optional[dict]:
        return self._patch_sql(
            tenant_id, number_id,
            "UPDATE ai_manager_authorized_users SET locked_until=now() + interval '1 hour', "
            "updated_at=now() WHERE id=:id AND vendor_id=:org", {})

    def _patch_sql(self, tenant_id: str, number_id: str, sql: str, params: dict) -> Optional[dict]:
        eng = self._engine()
        if eng is None:
            return None
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                p = {"id": number_id, "org": tenant_id}
                p.update(params)
                res = s.execute(self._text(sql), p)
                if getattr(res, "rowcount", 0) == 0:
                    return None
                r = s.execute(self._text(self._SEL + " AND id=:id"),
                              {"org": tenant_id, "id": number_id}).fetchone()
                return self._row_to_rec(r) if r else {"number_id": number_id, "tenant_id": tenant_id}
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_authorized_users patch failed: %r", exc)
            return None

    def find_by_forms(self, forms: set) -> Optional[dict]:
        """Cross-tenant caller-ID resolution (the ONLY cross-tenant read) — admin GUC over all tenants.
        Excludes LOCKED numbers (locked_until in the future): a number locked by the state-machine
        lockout must NOT resolve on caller-ID, mirroring the InMemory backend + the security invariant."""
        eng = self._engine()
        if eng is None or not forms:
            return None
        try:
            with eng.session(tenant_id="", is_admin=True) as s:
                rows = s.execute(self._text(
                    "SELECT id, vendor_id, phone_number, normalized_phone_number, name, role, "
                    " permissions, is_active, verify_mode, registered_by, locked_until, pin_set_at, "
                    " created_at, updated_at FROM ai_manager_authorized_users "
                    "WHERE is_active=TRUE AND (locked_until IS NULL OR locked_until <= now()) "
                    "AND normalized_phone_number = ANY(:forms) LIMIT 1"
                ), {"forms": list(forms)}).fetchall()
                return self._row_to_rec(rows[0]) if rows else None
        except Exception as exc:  # noqa: BLE001
            log.info("ai_manager_authorized_users lookup failed: %r", exc)
            return None


# --------------------------------------------------------------------------- #
# backend selection — Pg when db.engine is live, else the InMemory default
# --------------------------------------------------------------------------- #
_MEM = _InMem()
_PG = _Pg()


def _pg() -> Optional[_Pg]:
    """Return the Pg backend iff db.engine is importable + available; else None (→ InMemory). Never raises."""
    try:
        return _PG if _PG.available() else None
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# public surface (exact names/sigs — consumers: endpoints, identity, state_machine)
# --------------------------------------------------------------------------- #
def register(*, tenant_id: str, phone: str, label: str = "", role: str = "manager",
             verify_mode: str = "voice_pin", grants=None, registered_by: str = "") -> dict:
    """Register (or idempotently update) an authorized number for a tenant.

    Validates the phone via identity.canonical_phone (+91 10-digit). Invalid → {"ok":False,
    "reason":"invalid_phone"}. Re-registering an existing phone for the same tenant updates that row
    (same number_id). The number stays verified=False until /verify. Returns the public AimNumber row
    plus {"ok":True}. Fail-closed on blank tenant. Never raises.
    """
    if not _ok(tenant_id):
        return {"ok": False, "reason": "no_tenant"}
    canon = _canon(phone)
    # Require a normal +91 10-digit India number for a registered command-issuer (E.164, 13 chars).
    if not canon or not (canon.startswith("+91") and len(canon) == 13 and canon[1:].isdigit()):
        return {"ok": False, "reason": "invalid_phone"}
    role = (role or _DEFAULT_ROLE).strip().lower()
    if role not in _KNOWN_ROLES:
        role = _DEFAULT_ROLE
    verify_mode = (verify_mode or _DEFAULT_VERIFY).strip().lower()
    if verify_mode not in ("voice_pin", "otp"):
        verify_mode = _DEFAULT_VERIFY
    fields = {
        "label": (label or "").strip(), "role": role, "verify_mode": verify_mode,
        "grants": _clean_grants(grants), "registered_by": (registered_by or "").strip(),
    }
    try:
        pg = _pg()
        rec = pg.upsert_by_phone(tenant_id, canon, fields) if pg is not None else None
        if rec is None:
            rec = _MEM.upsert_by_phone(tenant_id, canon, fields)
        out = _public_row(rec)
        out["ok"] = True
        return out
    except Exception as exc:  # noqa: BLE001
        log.info("register failed: %r", exc)
        return {"ok": False, "reason": "register_error"}


def mark_verified(number_id: str, *, tenant_id: str) -> dict:
    """Mark a number's ownership verified (post-OTP). Tenant-scoped. {"ok":bool}. Never raises."""
    if not _ok(tenant_id) or not (number_id or "").strip():
        return {"ok": False, "reason": "not_found"}
    try:
        pg = _pg()
        rec = pg.set_verified(tenant_id, number_id) if pg is not None else None
        if rec is None:
            rec = _MEM.patch(tenant_id, number_id, verified=True)
        if rec is None:
            return {"ok": False, "reason": "not_found"}
        out = _public_row(rec)
        out["ok"] = True
        out["verified"] = True
        return out
    except Exception as exc:  # noqa: BLE001
        log.info("mark_verified failed: %r", exc)
        return {"ok": False, "reason": "verify_error"}


def list_numbers(tenant_id: str) -> list[dict]:
    """All of a tenant's numbers (no secrets), newest-first. Fail-closed on blank tenant. Never raises."""
    if not _ok(tenant_id):
        return []
    try:
        pg = _pg()
        rows = pg.list_tenant(tenant_id) if pg is not None else None
        if rows is None:
            rows = _MEM.list_tenant(tenant_id)
        return [_public_row(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        log.info("list_numbers failed: %r", exc)
        return []


def lookup(phone: str) -> Optional[dict]:
    """Cross-tenant caller-ID resolution (the ONLY cross-tenant fn; service-token gated at the endpoint).

    Resolves an inbound caller-ID against ALL tenants via identity.match_forms and returns the minimal
    resolution row {tenant_id, number_id, role, grants, verify_mode, phone} for the FIRST active match,
    or None when unknown (reveals nothing). No secret material. Never raises.
    """
    forms = _match_forms(phone)
    if not forms:
        return None
    try:
        pg = _pg()
        rec = pg.find_by_forms(forms) if pg is not None else None
        if rec is None:
            rec = _MEM.find_by_forms(forms)
        if rec is None:
            return None
        return _resolve_row(rec)
    except Exception as exc:  # noqa: BLE001
        log.info("lookup failed: %r", exc)
        return None


def set_grants(number_id: str, *, tenant_id: str, grants: list) -> dict:
    """Replace the capability grants on a number (admin + step-up gated at the endpoint). {"ok":bool}."""
    if not _ok(tenant_id) or not (number_id or "").strip():
        return {"ok": False, "reason": "not_found"}
    clean = _clean_grants(grants)
    try:
        pg = _pg()
        rec = pg.set_grants(tenant_id, number_id, clean) if pg is not None else None
        if rec is None:
            rec = _MEM.patch(tenant_id, number_id, grants=clean)
        if rec is None:
            return {"ok": False, "reason": "not_found"}
        out = _public_row(rec)
        out["ok"] = True
        out["grants"] = clean
        return out
    except Exception as exc:  # noqa: BLE001
        log.info("set_grants failed: %r", exc)
        return {"ok": False, "reason": "grants_error"}


def revoke(number_id: str, *, tenant_id: str) -> dict:
    """Deactivate a number (status→revoked). It no longer resolves on caller-ID. {"ok":bool}. Never raises."""
    if not _ok(tenant_id) or not (number_id or "").strip():
        return {"ok": False, "reason": "not_found"}
    try:
        pg = _pg()
        rec = pg.set_active(tenant_id, number_id, False) if pg is not None else None
        if rec is None:
            rec = _MEM.patch(tenant_id, number_id, active=False)
        if rec is None:
            return {"ok": False, "reason": "not_found"}
        out = _public_row(rec)
        out["ok"] = True
        out["status"] = "revoked"
        return out
    except Exception as exc:  # noqa: BLE001
        log.info("revoke failed: %r", exc)
        return {"ok": False, "reason": "revoke_error"}


def lock(number_id: str, *, tenant_id: str) -> dict:
    """Lock a number after N PIN failures (state-machine lockout). Status→locked. {"ok":bool}. Never raises."""
    if not _ok(tenant_id) or not (number_id or "").strip():
        return {"ok": False, "reason": "not_found"}
    try:
        pg = _pg()
        rec = pg.lock(tenant_id, number_id) if pg is not None else None
        if rec is None:
            rec = _MEM.patch(tenant_id, number_id, locked=True)
        if rec is None:
            return {"ok": False, "reason": "not_found"}
        out = _public_row(rec)
        out["ok"] = True
        out["status"] = "locked"
        return out
    except Exception as exc:  # noqa: BLE001
        log.info("lock failed: %r", exc)
        return {"ok": False, "reason": "lock_error"}
