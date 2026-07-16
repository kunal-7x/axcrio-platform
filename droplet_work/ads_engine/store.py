"""ads_engine.store — the SINGLE enforced tenant-scoped accessor for every ads row.

REDTEAM C1 (tenant-isolation build-blocker): the file JSON store has ZERO infrastructural
tenant enforcement (unlike the Postgres-RLS vault). Isolation therefore CANNOT rest on every
handler remembering `.get(tenant_id)`. This module is the ONE door: every read/write takes a
`tenant_id` and STRUCTURALLY cannot return another tenant's rows. Handlers/analytics/tick MUST
call these accessors — a raw `_read` of an ads collection file anywhere else is forbidden.

Storage convention (ARCH_SKELETON §c):
  ADS_DIR = VAR / "ads"
  * collection file (tenant-keyed dict):  ADS_DIR/<name>.json  ->  { "<tid>": { "<row_id>": {...} } }
  * per-tenant file (high churn):         ADS_DIR/<tid>/<name>.json

All IO goes through the INJECTED caller seams (_read / _write / _atomic_write_json) — this module
imports NO IO primitive and never `from caller import ...`. Reads are default-safe (never throw).
Money is minor units (paise).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import seams

# Collections that live as one tenant-keyed dict file (small/medium sets).
COLLECTION_FILES = {
    "campaigns", "ad_variants", "bandit_state", "consent_ledger", "spend_caps",
    # W3 optimization + guardrails state (one row per campaign/account per tenant).
    "allocations", "guardrail_state", "op_budget",
    # V2-W3 PARITY OPTIMIZATION LOOP — per-campaign/per-account derived state rows (no spend; pure
    # signal/decision state the continuous daemon reads+writes). `learning_state` = one row per
    # campaign (learning-phase cursor surfaced to the UI); `fatigue_state` = one row per campaign
    # (per-variant CTR-decay snapshot + rotation proposals); `audience_state` = one row per campaign
    # (seed audience + discovered expansion segments, proposal-only); `reallocation_state` = one row
    # per account (the continuous reallocation cursor: live per-channel response history + last split).
    "learning_state", "fatigue_state", "audience_state", "reallocation_state",
    # W6 own-landing form tokens (signed/scoped/revocable) — one row per token per tenant.
    "form_tokens",
    # BLINDSPOTS B13/B14 — ad-budget funding (paise). The tenant's funded balance lives as ONE
    # CAS-guarded row ("account") in `budget_account`; funding intents (gateway orders) are one
    # row per intent in `budget_intents`. The append-only money movement log is `budget_ledger`
    # (per-tenant file below). Money is ALWAYS minor units (paise).
    "budget_account",
    "budget_intents",
    # BLINDSPOTS B9 — the AUTONOMY orchestrator's per-tenant opt-in config ("config" row) and its
    # state-machine cursor ("state" row). One row each per tenant; the orchestrator advances `state`
    # by exactly one phase per tick. BLINDSPOTS B6 — `media_assets` is the backend stand-in gallery a
    # media-engine asset is mirrored into, so it can be bridged into a moderated ad variant offline.
    "autorun_config",
    "autorun_state",
    "media_assets",
    # BLINDSPOTS B7 — the tenant's persisted guardrails overrides (caps / breaker / approval gate).
    # ONE row ("_config") per tenant; GET /ads/guardrails merges it over the config defaults and the
    # step-up-gated POST /ads/guardrails writes it. Never spends; pure policy config.
    "guardrails_config",
    # BLINDSPOTS B4 — OAuth connect handshake. `oauth_nonces` holds the single-use CSRF/replay nonce
    # written at /ads/connect/{provider}/start and CONSUMED (deleted) by the callback — without it
    # registered, put_row/get_row raise and the replay defence is silently dead (the connect router
    # swallows the error and the callback then ALWAYS fails 'replayed_or_expired'). `leadgen_subscriptions`
    # records the per-page Meta leadgen webhook subscribe state (B17). One row per nonce/page per tenant.
    "oauth_nonces",
    "leadgen_subscriptions",
    # V2-W4 — the vault-configurable reasoning-model gateway's per-tenant month-to-date LLM spend
    # metering (one row per YYYY-MM, paise) that enforces the per-tenant monthly cost cap; and the
    # asset-bridge fallback gallery (`ad_gallery`, one row per mirrored ad asset) used when the
    # in-tree creative_engine is absent so the bridge is never a silent no-op. Neither spends.
    "llm_usage",
    "ad_gallery",
}
# High-churn sets that live as a per-tenant file.
PER_TENANT_FILES = {
    "leads_ads", "conversions", "ads_audit", "ads_jobs",
    # W3 immutable, append-only explainability log (high-churn).
    "decision_log",
    # V2-W3 — the CONVERSION-SIGNAL SUBSTRATE. `ad_events` is the append-only, high-churn spine of
    # pixel/server conversion events (lead_submitted -> call_connected -> lead_qualified/hot ->
    # site_visit_booked -> booking) that the same-day CAPI mapping and the optimizer consume. Rows
    # are ONLY appended (idempotent on event_id), NEVER mutated in place except to stamp capi send
    # state — the same append-only discipline as the decision_log / consent_log.
    "ad_events",
    # W6 IMMUTABLE, APPEND-ONLY consent ledger (hash-chained) — a write-once artifact, NOT a
    # rewritten dict (redteam compliance C3). Rows are ONLY appended, NEVER mutated in place.
    "consent_log",
    # BLINDSPOTS B13 — APPEND-ONLY ad-budget money ledger (paise). Every credit (funding confirmed)
    # and debit (campaign spend draw-down) is a NEW row, NEVER an in-place edit, so the balance is
    # always reconstructable + auditable. The CAS balance row (budget_account) is the fast read.
    "budget_ledger",
}

# W6 — the page_id->tenant map is a SINGLE GLOBAL file (not tenant-keyed): it maps an external
# Meta page_id (the unauth webhook's only identifier) to the owning tenant_id. It is the trust
# root of the inbound webhook, so it lives apart from the tenant-scoped collections and is read
# by the unauth webhook BEFORE any tenant is known. Uniqueness (one page -> one tenant) + an
# ownership proof are enforced on write (redteam secrets-vault C3 / compliance M6).
_PAGE_TENANT_MAP_FILE = "page_tenant_map"

# A tenant_id must be a safe path segment (no traversal). Token-derived ids are
# slug-like already; this is belt-and-suspenders against any path-injection.
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def _require(name: str):
    fn = getattr(seams(), name, None)
    if fn is None:
        raise RuntimeError(f"ads_engine.store: seam '{name}' not wired")
    return fn


def _var_dir() -> Path:
    vd = getattr(seams(), "var_dir", None)
    if vd is None:
        # Degrade-safe default mirrors caller.VAR default; only used if wire() omitted var_dir.
        import os
        vd = Path(os.getenv("FAMIT_VAR", "/opt/famit-agent/var"))
    return Path(vd)


def _ads_dir() -> Path:
    return _var_dir() / "ads"


def _safe(tenant_id: str) -> str:
    tid = str(tenant_id or "").strip()
    if not tid or not _SAFE_ID.match(tid):
        raise ValueError("ads_engine.store: invalid/empty tenant_id")
    return tid


def _collection_path(name: str) -> Path:
    return _ads_dir() / f"{name}.json"


def _per_tenant_path(tenant_id: str, name: str) -> Path:
    return _ads_dir() / _safe(tenant_id) / f"{name}.json"


# ===========================================================================
# BACKEND SELECTION (V2 W2 — the Postgres-RLS strangler).
#
# store.py's accessors validate (_safe / collection membership) and then dispatch the actual
# storage primitive to the selected backend. ADS_STORE_BACKEND=postgres routes every primitive
# through the FORCE-RLS Postgres backend (store_pg.PgBackend); the DEFAULT (json / unset) keeps
# the original file-JSON code path byte-for-byte, so the RESTING engine is unchanged.
#
# When postgres is EXPLICITLY requested but PG is unreachable we raise (fail LOUD) — we never
# silently downgrade an isolation request to the non-RLS json store. The backend is memoized;
# `_reset_backend()` lets tests flip ADS_STORE_BACKEND between runs.
# ===========================================================================
_BACKEND = None          # memoized PgBackend instance (postgres) — None means "json file path"
_BACKEND_RESOLVED = False


def _reset_backend() -> None:
    """Test hook: drop the memoized backend so a changed ADS_STORE_BACKEND re-resolves."""
    global _BACKEND, _BACKEND_RESOLVED
    _BACKEND = None
    _BACKEND_RESOLVED = False


def _backend_name() -> str:
    try:
        from .config import cfg
        return (cfg("ADS_STORE_BACKEND", "json") or "json").strip().lower()
    except Exception:  # noqa: BLE001
        import os
        return (os.getenv("ADS_STORE_BACKEND", "json") or "json").strip().lower()


def _pg() -> Any:
    """The active Postgres backend, or None for the json file path. Memoized.

    Raises RuntimeError when ADS_STORE_BACKEND=postgres but no Postgres engine is reachable —
    an explicit isolation request must NEVER fall through to the non-RLS json store.
    """
    global _BACKEND, _BACKEND_RESOLVED
    if _BACKEND_RESOLVED:
        return _BACKEND
    name = _backend_name()
    if name in ("pg", "postgres", "postgresql"):
        from . import store_pg
        backend = store_pg.make_backend()
        if backend is None:
            raise RuntimeError(
                "ads_engine.store: ADS_STORE_BACKEND=postgres but no Postgres engine is reachable "
                "(set ADS_PG_DSN / db.engine). Refusing to fall back to the non-RLS json store.")
        _BACKEND = backend
    else:
        _BACKEND = None
    _BACKEND_RESOLVED = True
    return _BACKEND


# ---------------------------------------------------------------------------
# COLLECTION accessors (tenant-keyed dict files). The read CANNOT return another
# tenant's rows: it isolates `data.get(tenant_id, {})` and never exposes the
# top-level dict. The write merges ONLY into the caller's tenant slice.
# ---------------------------------------------------------------------------
def get_collection(tenant_id: str, name: str) -> dict:
    """Return THIS tenant's rows of a collection: { "<row_id>": {...} }. Never cross-tenant.

    REDTEAM C1: the only path that touches a collection file — isolates the tenant slice
    structurally; a caller can never see the outer { "<tid>": ... } map.
    """
    tid = _safe(tenant_id)
    if name not in COLLECTION_FILES:
        raise ValueError(f"ads_engine.store: '{name}' is not a collection")
    b = _pg()
    if b is not None:
        return b.get_collection(tid, name)
    read = _require("read")
    data = read(_collection_path(name), {})
    if not isinstance(data, dict):
        return {}
    rows = data.get(tid, {})
    return rows if isinstance(rows, dict) else {}


def get_row(tenant_id: str, name: str, row_id: str) -> dict | None:
    """One row by id, tenant-scoped. None if absent (or owned by another tenant)."""
    return get_collection(tenant_id, name).get(str(row_id))


def put_row(tenant_id: str, name: str, row_id: str, row: dict) -> dict:
    """Upsert ONE row into this tenant's slice. STAMPS tenant_id on the row (never trusts
    a body-supplied tenant_id). Read-modify-write the whole file via the atomic seam.

    Returns the stored row. The write merges into `data[tid][row_id]` and leaves every
    other tenant's slice byte-untouched.
    """
    tid = _safe(tenant_id)
    if name not in COLLECTION_FILES:
        raise ValueError(f"ads_engine.store: '{name}' is not a collection")
    b = _pg()
    if b is not None:
        return b.put_row(tid, name, str(row_id), row)
    read = _require("read")
    awrite_json = _require("atomic_write_json")
    p = _collection_path(name)
    data = read(p, {})
    if not isinstance(data, dict):
        data = {}
    slice_ = data.get(tid)
    if not isinstance(slice_, dict):
        slice_ = {}
    stored = dict(row or {})
    stored["tenant_id"] = tid  # server-stamped, ALWAYS; ignore any body tenant_id
    slice_[str(row_id)] = stored
    data[tid] = slice_
    awrite_json(p, data)
    return stored


def delete_row(tenant_id: str, name: str, row_id: str) -> bool:
    """Delete one row from this tenant's slice only. True if it existed."""
    tid = _safe(tenant_id)
    if name not in COLLECTION_FILES:
        raise ValueError(f"ads_engine.store: '{name}' is not a collection")
    b = _pg()
    if b is not None:
        return b.delete_row(tid, name, str(row_id))
    read = _require("read")
    awrite_json = _require("atomic_write_json")
    p = _collection_path(name)
    data = read(p, {})
    if not isinstance(data, dict):
        return False
    slice_ = data.get(tid)
    if not isinstance(slice_, dict) or str(row_id) not in slice_:
        return False
    del slice_[str(row_id)]
    data[tid] = slice_
    awrite_json(p, data)
    return True


# ---------------------------------------------------------------------------
# PER-TENANT file accessors (high-churn). The path itself is tenant-scoped, so a
# read of tenant A's file can never surface tenant B's rows — the file is private
# by directory. Stored as a list of rows.
# ---------------------------------------------------------------------------
def get_tenant_file(tenant_id: str, name: str) -> list:
    """Return this tenant's per-tenant file rows (a list). Never cross-tenant (separate path)."""
    if name not in PER_TENANT_FILES:
        raise ValueError(f"ads_engine.store: '{name}' is not a per-tenant file")
    b = _pg()
    if b is not None:
        return b.get_tenant_file(_safe(tenant_id), name)
    read = _require("read")
    rows = read(_per_tenant_path(tenant_id, name), [])
    return rows if isinstance(rows, list) else []


def append_tenant_row(tenant_id: str, name: str, row: dict) -> dict:
    """Append one row to this tenant's per-tenant file (e.g. audit, leads_ads). Stamps tenant_id."""
    if name not in PER_TENANT_FILES:
        raise ValueError(f"ads_engine.store: '{name}' is not a per-tenant file")
    b = _pg()
    if b is not None:
        return b.append_tenant_row(_safe(tenant_id), name, row)
    read = _require("read")
    awrite_json = _require("atomic_write_json")
    p = _per_tenant_path(tenant_id, name)
    rows = read(p, [])
    if not isinstance(rows, list):
        rows = []
    stored = dict(row or {})
    stored["tenant_id"] = _safe(tenant_id)
    rows.append(stored)
    awrite_json(p, rows)
    return stored


def put_tenant_file(tenant_id: str, name: str, rows: list) -> None:
    """Replace this tenant's per-tenant file with `rows` (each tenant-stamped). Tenant-scoped path."""
    if name not in PER_TENANT_FILES:
        raise ValueError(f"ads_engine.store: '{name}' is not a per-tenant file")
    tid = _safe(tenant_id)
    b = _pg()
    if b is not None:
        b.put_tenant_file(tid, name, rows)
        return
    awrite_json = _require("atomic_write_json")
    safe_rows = []
    for r in (rows or []):
        rr = dict(r or {})
        rr["tenant_id"] = tid
        safe_rows.append(rr)
    awrite_json(_per_tenant_path(tenant_id, name), safe_rows)


# Convenience used by analytics for the campaigns surface.
def list_campaigns(tenant_id: str) -> list:
    """All campaign records for this tenant, as a list (analytics/status surface)."""
    return list(get_collection(tenant_id, "campaigns").values())


def list_tenant_ids(name: str = "campaigns") -> list:
    """Every tenant_id that has at least one row in a COLLECTION file.

    The ONLY non-tenant-scoped read in the store — used by the background tick (W4) to
    enumerate which tenants have ads activity so it can sweep each one's slice via the
    tenant-scoped accessors above. It returns ONLY the top-level keys (tenant ids), never
    any tenant's row data, so it cannot leak one tenant's rows to another. Default-safe
    (returns [] on any error); never throws.
    """
    if name not in COLLECTION_FILES:
        raise ValueError(f"ads_engine.store: '{name}' is not a collection")
    try:
        b = _pg()
    except Exception:  # noqa: BLE001 — degrade-safe: tick must never crash on backend resolve
        return []
    if b is not None:
        return b.list_tenant_ids(name)
    try:
        read = _require("read")
        data = read(_collection_path(name), {})
    except Exception:  # noqa: BLE001 — degrade-safe: tick must never crash on a bad read
        return []
    if not isinstance(data, dict):
        return []
    out = []
    for tid in data.keys():
        try:
            out.append(_safe(str(tid)))
        except Exception:  # noqa: BLE001 — skip any malformed/unsafe key, don't fail the sweep
            continue
    return out


def get_spend_caps(tenant_id: str) -> dict:
    """The tenant's spend_caps row (the breaker state). Empty dict when unset."""
    return get_collection(tenant_id, "spend_caps").get(_safe(tenant_id), {})


# ---------------------------------------------------------------------------
# W3 OPTIMIZATION + GUARDRAILS helpers (all tenant-scoped via the same accessors).
#
# REDTEAM C2: spend-mutating write-backs need read-modify-write safety. The store
# itself is single-process JSON; we provide an OPTIMISTIC-CONCURRENCY CAS helper
# (`cas_row`) that rejects on `version` mismatch, plus the guardrail layer holds a
# per-tenant(+account) async lock across read->guard->spend->writeback. Use BOTH:
# the lock serializes; the CAS is the backstop if two writers ever interleave.
# ---------------------------------------------------------------------------

class VersionConflict(Exception):
    """Raised by cas_row when the stored row's version != the expected version."""


def _bump_version(row: dict) -> dict:
    r = dict(row or {})
    try:
        r["version"] = int(r.get("version", 0)) + 1
    except Exception:  # noqa: BLE001
        r["version"] = 1
    return r


def cas_row(tenant_id: str, name: str, row_id: str, expected_version: int | None, row: dict) -> dict:
    """Compare-and-swap upsert of ONE collection row, tenant-scoped.

    REDTEAM C2: optimistic concurrency. If a row already exists and `expected_version`
    is not None, the stored `version` MUST equal `expected_version` or VersionConflict
    is raised (the caller re-reads + retries). On success the stored row's `version`
    is bumped by 1. First write (no existing row) is allowed when expected_version is
    None or 0. Tenant_id is server-stamped (never trusts the body) like put_row.
    """
    tid = _safe(tenant_id)
    if name not in COLLECTION_FILES:
        raise ValueError(f"ads_engine.store: '{name}' is not a collection")
    b = _pg()
    if b is not None:
        return b.cas_row(tid, name, str(row_id), expected_version, row, VersionConflict)
    read = _require("read")
    awrite_json = _require("atomic_write_json")
    p = _collection_path(name)
    data = read(p, {})
    if not isinstance(data, dict):
        data = {}
    slice_ = data.get(tid)
    if not isinstance(slice_, dict):
        slice_ = {}
    existing = slice_.get(str(row_id))
    if isinstance(existing, dict):
        cur_v = int(existing.get("version", 0) or 0)
        if expected_version is not None and cur_v != int(expected_version):
            raise VersionConflict(
                f"version mismatch on {name}/{row_id}: have {cur_v}, expected {expected_version}"
            )
    stored = _bump_version(row)
    stored["tenant_id"] = tid
    slice_[str(row_id)] = stored
    data[tid] = slice_
    awrite_json(p, data)
    return stored


# --- bandit_state ----------------------------------------------------------
def get_bandit_state(tenant_id: str, campaign_id: str) -> dict | None:
    """The BanditState row for one campaign. None when absent/cross-tenant."""
    return get_row(tenant_id, "bandit_state", campaign_id)


def put_bandit_state(tenant_id: str, campaign_id: str, state: dict,
                     expected_version: int | None = None) -> dict:
    """CAS-persist a BanditState (propose-only state; never spends)."""
    return cas_row(tenant_id, "bandit_state", campaign_id, expected_version, state)


def list_bandit_states(tenant_id: str) -> list:
    """All BanditState rows for the tenant."""
    return list(get_collection(tenant_id, "bandit_state").values())


# --- allocations -----------------------------------------------------------
def get_allocation(tenant_id: str, account_id: str) -> dict | None:
    """The AllocationState row for one account. None when absent/cross-tenant."""
    return get_row(tenant_id, "allocations", account_id)


def put_allocation(tenant_id: str, account_id: str, alloc: dict,
                   expected_version: int | None = None) -> dict:
    """CAS-persist an AllocationState (proposed split; budget-raises gated by approve)."""
    return cas_row(tenant_id, "allocations", account_id, expected_version, alloc)


# --- guardrail_state -------------------------------------------------------
def get_guardrail_state(tenant_id: str, campaign_id: str) -> dict | None:
    """The GuardrailState row for one campaign. None when absent/cross-tenant."""
    return get_row(tenant_id, "guardrail_state", campaign_id)


def put_guardrail_state(tenant_id: str, campaign_id: str, gstate: dict,
                        expected_version: int | None = None) -> dict:
    """CAS-persist a GuardrailState snapshot."""
    return cas_row(tenant_id, "guardrail_state", campaign_id, expected_version, gstate)


def list_guardrail_states(tenant_id: str) -> list:
    """All GuardrailState rows for the tenant (the spend-sweep surface)."""
    return list(get_collection(tenant_id, "guardrail_state").values())


# --- guardrails_config (BLINDSPOTS B7: persisted tenant policy overrides) ----
_GUARDRAILS_CONFIG_ROW = "_config"


def get_guardrails_config(tenant_id: str) -> dict:
    """The tenant's persisted guardrails overrides ({} when never saved). Pure policy, no spend."""
    row = get_row(tenant_id, "guardrails_config", _GUARDRAILS_CONFIG_ROW)
    return row if isinstance(row, dict) else {}


def put_guardrails_config(tenant_id: str, cfg: dict) -> dict:
    """Upsert the tenant's guardrails overrides row (tenant-stamped by put_row)."""
    return put_row(tenant_id, "guardrails_config", _GUARDRAILS_CONFIG_ROW, dict(cfg or {}))


# --- decision_log (per-tenant, append-only, immutable) ---------------------
def append_decision(tenant_id: str, row: dict) -> dict:
    """Append one immutable DecisionRow to the tenant's decision_log.

    Append-only: rows are NEVER mutated in place (audit trail). Tenant-stamped.
    """
    return append_tenant_row(tenant_id, "decision_log", row)


def get_decisions(tenant_id: str, limit: int = 50, campaign_id: str | None = None) -> list:
    """Newest-first tail of the decision_log, optionally filtered by campaign.

    limit clamped to [1, 200] (the explained-actions feed; never throws)."""
    try:
        n = max(1, min(int(limit), 200))
    except Exception:  # noqa: BLE001
        n = 50
    rows = get_tenant_file(tenant_id, "decision_log")
    if campaign_id is not None:
        rows = [r for r in rows if r.get("campaign_id") == campaign_id]
    return list(reversed(rows))[:n]


# --- ad_events (V2-W3 conversion-signal substrate, per-tenant append-only) ---
def append_ad_event(tenant_id: str, row: dict) -> dict:
    """Append ONE conversion-signal event to the tenant's append-only ad_events spine. Tenant-stamped.

    The producer (pixel/server/webhook/voice outcome) writes here; ad_events.ingest_event dedups on
    event_id BEFORE calling, so this is a pure append. Never mutated in place except via update_ad_event
    (used only to stamp CAPI send-state on an existing row)."""
    return append_tenant_row(tenant_id, "ad_events", row)


def get_ad_events(tenant_id: str, *, limit: int | None = None,
                  since_ts: float | None = None) -> list:
    """This tenant's ad_events, oldest-first. Optional `since_ts` window + `limit` tail (newest)."""
    rows = get_tenant_file(tenant_id, "ad_events")
    if since_ts is not None:
        rows = [r for r in rows if float(r.get("ts", 0) or 0) >= float(since_ts)]
    if limit is not None:
        try:
            n = max(1, int(limit))
            rows = rows[-n:]
        except Exception:  # noqa: BLE001
            pass
    return rows


def find_ad_event(tenant_id: str, event_id: str) -> dict | None:
    """Find an ad_event by its idempotency event_id (None if absent). Used to dedup on ingest."""
    eid = str(event_id or "")
    if not eid:
        return None
    for r in get_tenant_file(tenant_id, "ad_events"):
        if str(r.get("event_id", "")) == eid:
            return r
    return None


def update_ad_event(tenant_id: str, event_id: str, patch: dict) -> bool:
    """Patch an existing ad_event in place by event_id (ONLY to stamp capi_sent_at/capi_status — the
    spine stays otherwise append-only). True if a row was found+updated. Never raises."""
    eid = str(event_id or "")
    if not eid:
        return False
    try:
        rows = get_tenant_file(tenant_id, "ad_events")
        found = False
        out = []
        for r in rows:
            if str(r.get("event_id", "")) == eid:
                rr = dict(r)
                rr.update(patch or {})
                out.append(rr)
                found = True
            else:
                out.append(r)
        if found:
            put_tenant_file(tenant_id, "ad_events", out)
        return found
    except Exception:  # noqa: BLE001
        return False


# --- per-tenant daily op sub-budget (REDTEAM M5) ---------------------------
# A per-tenant daily cap on the NUMBER of spend-mutating ops the engine may apply
# itself (auto-applies + approved moves), so a runaway bandit/allocator loop can't
# fan out unbounded platform mutations even within the money caps. Decrement-and-check
# is CAS-guarded; once exhausted, the guard chain blocks further auto-applies that day.
def get_op_budget(tenant_id: str, day_key: str, default_limit: int) -> dict:
    """The op-budget row for a UTC day_key (YYYYMMDD). Seeds default_limit on first use."""
    row = get_row(tenant_id, "op_budget", str(day_key))
    if not isinstance(row, dict) or not row:
        return {"day": str(day_key), "limit": int(default_limit), "used": 0, "version": 0}
    return row


def try_consume_op(tenant_id: str, day_key: str, default_limit: int, cost: int = 1) -> bool:
    """Atomically reserve `cost` ops from today's sub-budget. False when exhausted.

    REDTEAM M5: caps the count of self-applied spend-mutations per tenant per day.
    CAS-guarded so two concurrent consumers can't both pass the last unit; on a
    version conflict it returns False (fail-closed — the caller treats it as denied).
    """
    row = get_op_budget(tenant_id, day_key, default_limit)
    limit = int(row.get("limit", default_limit) or 0)
    used = int(row.get("used", 0) or 0)
    c = max(1, int(cost))
    if used + c > limit:
        return False
    row = dict(row)
    row["used"] = used + c
    try:
        cas_row(tenant_id, "op_budget", str(day_key), int(row.get("version", 0) or 0), row)
    except VersionConflict:
        return False
    return True


# ===========================================================================
# BLINDSPOTS B13/B14 — AD-BUDGET FUNDING STORE (paise, tenant-scoped).
#
# The funded balance is ONE CAS-guarded row id="account" in the `budget_account` collection:
#   { balance_minor, currency, funded_total_minor, spent_total_minor, version, updated_ts }
# Credits/debits go through CAS (cas_row) so two concurrent writers can never double-count, and
# every movement also appends an immutable row to the per-tenant `budget_ledger` (audit truth).
# Funding intents (gateway orders) are one row per intent in `budget_intents`, keyed by intent_id;
# idempotency is by the intent's idem_key (the route resolves an existing intent before creating).
# NO money is fronted by the platform: a balance only rises when a real gateway payment is verified.
# ===========================================================================
_BUDGET_ACCOUNT_ROW = "account"  # the single per-tenant balance row id in `budget_account`.


def get_budget_account(tenant_id: str) -> dict:
    """The tenant's funded ad-budget balance row. Seeds a zero balance on first read (never None)."""
    row = get_row(tenant_id, "budget_account", _BUDGET_ACCOUNT_ROW)
    if not isinstance(row, dict) or not row:
        return {"balance_minor": 0, "currency": "INR", "funded_total_minor": 0,
                "spent_total_minor": 0, "version": 0}
    return row


def _apply_budget_delta(tenant_id: str, *, delta_minor: int, currency: str,
                        kind: str, ref: dict | None) -> dict:
    """Apply a signed paise delta to the balance under CAS, append a ledger row, return the new row.

    A debit (negative delta) is FLOORED at zero balance (never goes negative — fail-closed: a spend
    draw-down can at most empty the account). The CAS read+write is RETRIED on a concurrent
    VersionConflict (re-read the current balance, re-apply the delta) so an interleaving credit can
    never silently drop money; VersionConflict only escapes after the retry budget is exhausted. The
    ledger append (the immutable audit record) happens ONLY after the balance write commits.
    """
    import time as _t
    applied = int(delta_minor)
    new_bal = 0
    stored = None
    last_exc: Exception | None = None
    for _ in range(8):  # bounded retry — re-read + re-apply on a concurrent CAS conflict.
        acct = get_budget_account(tenant_id)
        cur_bal = int(acct.get("balance_minor", 0) or 0)
        raw_new = cur_bal + int(delta_minor)
        if raw_new < 0:
            new_bal = 0
            applied = -cur_bal
        else:
            new_bal = raw_new
            applied = int(delta_minor)
        funded = int(acct.get("funded_total_minor", 0) or 0)
        spent = int(acct.get("spent_total_minor", 0) or 0)
        if applied >= 0:
            funded += applied
        else:
            spent += -applied
        row = {
            "balance_minor": new_bal, "currency": currency or acct.get("currency", "INR"),
            "funded_total_minor": funded, "spent_total_minor": spent,
            "updated_ts": int(_t.time()), "version": int(acct.get("version", 0) or 0),
        }
        try:
            stored = cas_row(tenant_id, "budget_account", _BUDGET_ACCOUNT_ROW,
                             int(acct.get("version", 0) or 0), row)
            break
        except VersionConflict as exc:  # concurrent writer won — re-read and retry.
            last_exc = exc
            continue
    if stored is None:
        raise last_exc or VersionConflict("budget_account CAS retries exhausted")
    ledger_row = {
        "kind": kind, "delta_minor": applied, "balance_after_minor": new_bal,
        "currency": stored.get("currency", "INR"), "ts": int(_t.time()),
    }
    if isinstance(ref, dict):
        # keep ONLY non-secret references (ids), never a gateway secret/signature.
        for k in ("intent_id", "payment_id", "order_id", "campaign_id", "provider", "note"):
            if k in ref and ref[k] is not None:
                ledger_row[k] = str(ref[k])[:128]
    append_tenant_row(tenant_id, "budget_ledger", ledger_row)
    return stored


def credit_budget(tenant_id: str, amount_minor: int, *, currency: str = "INR",
                  ref: dict | None = None) -> dict:
    """Credit the tenant's ad-budget balance (a verified gateway payment). amount_minor >= 0."""
    amt = max(0, int(amount_minor or 0))
    return _apply_budget_delta(tenant_id, delta_minor=amt, currency=currency,
                               kind="credit", ref=ref)


def debit_budget(tenant_id: str, amount_minor: int, *, currency: str = "INR",
                 ref: dict | None = None) -> dict:
    """Debit the tenant's ad-budget balance (campaign spend draw-down). Floored at zero (never < 0)."""
    amt = max(0, int(amount_minor or 0))
    return _apply_budget_delta(tenant_id, delta_minor=-amt, currency=currency,
                               kind="debit", ref=ref)


def get_budget_ledger(tenant_id: str, limit: int = 50) -> list:
    """Newest-first tail of the immutable ad-budget ledger (clamped [1,200])."""
    try:
        n = max(1, min(int(limit), 200))
    except Exception:  # noqa: BLE001
        n = 50
    rows = get_tenant_file(tenant_id, "budget_ledger")
    return list(reversed(rows))[:n]


def put_budget_intent(tenant_id: str, intent_id: str, intent: dict,
                      expected_version: int | None = None) -> dict:
    """CAS-persist a funding intent (gateway order) row, tenant-scoped."""
    return cas_row(tenant_id, "budget_intents", str(intent_id), expected_version, intent)


def get_budget_intent(tenant_id: str, intent_id: str) -> dict | None:
    """One funding intent by id, tenant-scoped. None if absent/cross-tenant."""
    return get_row(tenant_id, "budget_intents", str(intent_id))


def list_budget_intents(tenant_id: str) -> list:
    """All funding intents for the tenant."""
    return list(get_collection(tenant_id, "budget_intents").values())


def find_budget_intent_by_idem(tenant_id: str, idem_key: str) -> dict | None:
    """Resolve an existing intent by its idem_key (funding-intent idempotency). None if no match."""
    ik = str(idem_key or "").strip()
    if not ik:
        return None
    for row in list_budget_intents(tenant_id):
        if str(row.get("idem_key", "")) == ik:
            return row
    return None


def find_budget_intent_by_order(tenant_id: str, order_id: str) -> dict | None:
    """Resolve an intent by the gateway's order id (webhook/confirm lookup). None if no match."""
    oid = str(order_id or "").strip()
    if not oid:
        return None
    for row in list_budget_intents(tenant_id):
        if str(row.get("order_id", "")) == oid:
            return row
    return None


# ===========================================================================
# W6 — PAGE_ID -> TENANT MAP (the inbound-webhook trust root).
#
# The Meta leadgen webhook is the ONLY unauthenticated PII surface. Its body is UNTRUSTED until
# HMAC-verified, but HMAC needs the tenant's app_secret, which needs the tenant. We break the
# cycle with a persisted page_id->tenant map written at CONNECT time (when the tenant proves it
# owns the Page via an authenticated OAuth/connect flow). The webhook resolves tenant from this
# map ONLY — NEVER from the body. Properties enforced here (redteam compliance M6 / secrets C3):
#   * UNIQUENESS — one page_id maps to AT MOST one tenant. A second tenant claiming the same page
#     is REJECTED (PageOwnershipConflict), not silently re-pointed (anti-hijack).
#   * OWNERSHIP — the write requires the caller to pass the authenticated tenant_id (token-derived
#     upstream); the map row records who/when for audit.
#   * MISS = FAIL-CLOSED upstream — lookup returns None for an unmapped page; the webhook then
#     rejects (no default/admin tenant). This module never invents a tenant.
# ===========================================================================
_SAFE_PAGE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class PageOwnershipConflict(Exception):
    """Raised when a page_id is already mapped to a DIFFERENT tenant (uniqueness violation)."""


def _page_map_path() -> Path:
    return _ads_dir() / f"{_PAGE_TENANT_MAP_FILE}.json"


def get_tenant_for_page(page_id: str) -> str | None:
    """Resolve the owning tenant_id for an external Meta page_id. None when unmapped (FAIL-CLOSED
    at the webhook: an unmapped page is rejected, NEVER attributed to a default tenant).

    The ONE non-tenant-scoped read that the unauth webhook performs — it returns ONLY the owning
    tenant_id (a token-derived slug), never any tenant's rows. Default-safe; never raises.
    """
    pid = str(page_id or "").strip()
    if not pid or not _SAFE_PAGE_ID.match(pid):
        return None
    try:
        b = _pg()
    except Exception:  # noqa: BLE001 — degrade-safe: never crash the unauth webhook
        return None
    if b is not None:
        return b.get_tenant_for_page(pid)
    try:
        read = _require("read")
        data = read(_page_map_path(), {})
    except Exception:  # noqa: BLE001 — degrade-safe: a bad read => unmapped => fail-closed
        return None
    if not isinstance(data, dict):
        return None
    row = data.get(pid)
    if not isinstance(row, dict):
        return None
    tid = row.get("tenant_id")
    return str(tid) if tid else None


def link_page_to_tenant(tenant_id: str, page_id: str, *, actor: str = "",
                        evidence: dict | None = None) -> dict:
    """Bind a page_id to THIS tenant (called from the authenticated connect flow ONLY).

    UNIQUENESS: if page_id already maps to a different tenant -> PageOwnershipConflict (anti-hijack).
    Re-linking by the SAME tenant is idempotent (updates the audit fields). tenant_id is the
    token-derived owner (caller resolves it; this module trusts the passed value as already-authed).
    """
    tid = _safe(tenant_id)
    pid = str(page_id or "").strip()
    if not pid or not _SAFE_PAGE_ID.match(pid):
        raise ValueError("ads_engine.store: invalid/empty page_id")
    b = _pg()
    if b is not None:
        return b.link_page_to_tenant(tid, pid, actor, evidence, PageOwnershipConflict)
    read = _require("read")
    awrite_json = _require("atomic_write_json")
    p = _page_map_path()
    data = read(p, {})
    if not isinstance(data, dict):
        data = {}
    existing = data.get(pid)
    if isinstance(existing, dict):
        owner = existing.get("tenant_id")
        if owner and str(owner) != tid:
            raise PageOwnershipConflict(
                f"page_id {pid} already linked to a different tenant")
    import time as _t
    row = {
        "page_id": pid, "tenant_id": tid, "actor": str(actor or "")[:128],
        "linked_at": (existing or {}).get("linked_at", _t.time()) if isinstance(existing, dict) else _t.time(),
        "updated_at": _t.time(),
    }
    if isinstance(evidence, dict):
        # keep ONLY non-secret connect evidence (ids/timestamps); never store tokens here.
        row["evidence"] = {k: v for k, v in evidence.items()
                           if k in ("oauth_flow", "connected_by", "business_id")}
    data[pid] = row
    awrite_json(p, data)
    return row


def unlink_page(tenant_id: str, page_id: str) -> bool:
    """Remove a page mapping (ownership-checked: a tenant can only unlink its OWN page). True if removed."""
    tid = _safe(tenant_id)
    pid = str(page_id or "").strip()
    if not pid:
        return False
    b = _pg()
    if b is not None:
        return b.unlink_page(tid, pid)
    read = _require("read")
    awrite_json = _require("atomic_write_json")
    p = _page_map_path()
    data = read(p, {})
    if not isinstance(data, dict):
        return False
    row = data.get(pid)
    if not isinstance(row, dict) or str(row.get("tenant_id")) != tid:
        return False
    del data[pid]
    awrite_json(p, data)
    return True


# ===========================================================================
# W6 — APPEND-ONLY HASH-CHAINED CONSENT LEDGER (the immutable consent artifact).
#
# redteam compliance C3: "append-only" must be a PROPERTY of the artifact, not a convention. The
# ledger is a per-tenant file (`consent_log`) of rows ONLY EVER appended (never a rewritten dict).
# Each row carries prev_hash + hash_chain (sha256 over the canonical row + prev_hash). Revocation
# is a NEW appended row (kind unchanged, granted=False), never an in-place edit. verify_chain()
# re-walks the chain and reports the first break (tamper evidence). compliance.py owns the row
# shape + hashing; this module owns the durable append + the read.
# ===========================================================================
def consent_log_rows(tenant_id: str) -> list:
    """All consent rows for the tenant, in append order (oldest first). Tenant-scoped path."""
    return get_tenant_file(tenant_id, "consent_log")


def append_consent_row(tenant_id: str, row: dict) -> dict:
    """Append ONE consent row to the tenant's immutable consent_log. NEVER mutates an existing row.

    The row MUST already carry its computed hash_chain/prev_hash (compliance.py computes them off
    the current tail BEFORE calling). Tenant-stamped. Returns the stored row.
    """
    return append_tenant_row(tenant_id, "consent_log", row)


def latest_consent_hash(tenant_id: str) -> str:
    """The hash_chain of the newest row (the chain head to extend), or '' for an empty ledger."""
    rows = consent_log_rows(tenant_id)
    if not rows:
        return ""
    return str(rows[-1].get("hash_chain", "") or "")
