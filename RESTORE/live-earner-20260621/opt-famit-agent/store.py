"""store.py — P1 per-store MODE router over the _read/_write/_awrite seam (design §6).

THE strangler insertion point. caller.py's _read/_write/_awrite become thin shims that delegate
here ONLY for registered paths whose effective mode != "json"; everything else (and all-json default)
is a byte-identical pass-through to the ORIGINAL raw functions (R3: never reserialize in json mode).

Per-store MODE in {json, dual, pg}, keyed by file NAME, DEFAULT json for every store:
  json : original _read/_write (authoritative, byte-identical). Pass-through.
  dual : read JSON (authoritative); write JSON first, THEN best-effort mirror to PG off the request
         path via a single per-store coalescing worker (B1). Mirror failure swallowed + counted.
  pg   : read+write PG (leads only in P1; gated on a per-request tenant contextvar — until wired,
         max_safe caps leads at dual). Default pg still shadow-writes JSON (cheap rollback insurance).

Import-safe: if db.engine.available() is False -> EVERY store forced to json. Never raises to caller.

RED-TEAM fixes folded in:
  B1: NOT create_task-per-write (races -> persistent shadow_diff drift). ONE long-lived per-store
      worker fed by a depth-1 replace-on-full queue; always applies the LATEST whole-file snapshot.
  B2: delete-by-omission (DELETE WHERE id <> ALL(:ids)) is SKIPPED when incoming id-set is empty while
      PG is non-empty, and NEVER driven by a _read that raised (only a successful _read_raw snapshot).
  B-confirm: _awrite is a DEAD path in P1 (zero call sites) — its shim mirrors `write` mechanics exactly.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Optional

# ---- injected from caller.py via init() ----
_read_raw: Optional[Callable[[Path, Any], Any]] = None
_write_raw: Optional[Callable[[Path, Any], None]] = None
_awrite_raw = None  # async; dead path in P1 but wired for completeness
_store_lock = None  # caller's _STORE_LOCK (asyncio.Lock)
_config = None
_timeout_ms = 800
_ready = False

# the db package (set in init); None => degrade everything to json
_db = None

# ---- per-store specs + runtime status ----
class StoreSpec:
    __slots__ = ("name", "table", "max_safe", "to_rows", "key", "mode",
                 "cols", "key_cols", "order_by", "dict_store", "multi_file",
                 "pg_writes_ok", "pg_writes_fail", "last_error", "last_shadow_diff",
                 "_queue", "_worker", "_queues", "_workers")

    def __init__(self, name, table, max_safe, to_rows, key, cols, key_cols, order_by="id",
                 dict_store=False, multi_file=False):
        self.name = name            # file name, e.g. "leads.json"
        self.table = table          # pg table, e.g. "leads"
        self.max_safe = max_safe    # cap: "json" | "dual" | "pg"
        self.to_rows = to_rows      # fn(json_obj) -> list[dict rows]  (multi_file: fn(json_obj, stem))
        self.key = key              # fn(row) -> stable composite key string (id-set / diff key)
        self.cols = cols            # ordered promoted column names (excl. data) for the UPSERT
        self.key_cols = key_cols    # PK columns for ON CONFLICT + delete-by-omission
        self.order_by = order_by    # deterministic ORDER BY for pg reads
        # dict_store: the JSON file is a DICT keyed by PK (billing: org_id->rec), NOT a list. to_rows
        # iterates .items(). shadow_diff re-derives a single PG row's key by wrapping data as a 1-key
        # dict (it can't pass [data] like list-stores). Default False (every other store is a list).
        self.dict_store = dict_store
        # multi_file: this spec covers a DIRECTORY of per-tenant files (ledger: var/ledger/<stem>.json),
        # NOT one file. Resolved by parent-dir match (not Path.name). The org_id comes from the file STEM
        # (records carry no tenant_id), promoted into the column ONLY (never into `data` jsonb). Each
        # _write is a SINGLE-TENANT snapshot, so the mirror coalesces + reconciles PER STEM (a per-spec
        # queue would coalesce across tenants and drop a snapshot), and delete-by-omission is org-SCOPED.
        self.multi_file = multi_file
        self.mode = "json"          # effective configured mode (capped at runtime)
        self.pg_writes_ok = 0
        self.pg_writes_fail = 0
        self.last_error: Optional[str] = None
        self.last_shadow_diff: Optional[int] = None
        self._queue: Optional[asyncio.Queue] = None      # single-file stores: one queue/worker
        self._worker: Optional[asyncio.Task] = None
        self._queues: dict = {}     # multi_file (ledger): stem -> queue
        self._workers: dict = {}    # multi_file (ledger): stem -> worker task


_SPECS: dict[str, StoreSpec] = {}     # keyed by file name (single-file stores)
_LEDGER_SPEC: Optional["StoreSpec"] = None   # the multi_file ledger spec (resolved by parent-dir)
_MODE_RANK = {"json": 0, "dual": 1, "pg": 2}


# ===================== row mappers (JSON record -> PG row dict) =====================
def _leads_rows(data: Any) -> list[dict]:
    """leads.json is a flat list of lead dicts. Map each to a leads-table row.
    Promote indexed/RLS columns; stash the FULL original object in data jsonb (lossless).

    NOTE (P1 decision): the parsed timestamptz columns (added_at) are intentionally left NULL — only
    the verbatim *_raw string is populated. shadow_diff (§8) compares count + id-set + normalized
    `data jsonb`, NEVER the promoted columns, so leads shadow_diff==0 holds. Populating parsed
    timestamps (and the ORDER BY they back) is deferred to U7/analytics, keeping date-parse edge cases
    out of the riskiest unit. The pg-read ORDER BY tolerates this via `added_at NULLS FIRST, id`."""
    out = []
    if not isinstance(data, list):
        return out
    for x in data:
        if not isinstance(x, dict):
            continue
        out.append({
            "id": str(x.get("id") or x.get("lead_id") or ""),
            "org_id": str(x.get("tenant_id") or "admin"),
            "name": str(x.get("name") or ""),
            "phone": str(x.get("phone") or ""),
            "status": str(x.get("status") or "new"),
            "score": int(x.get("score") or 0) if str(x.get("score") or "0").lstrip("-").isdigit() else 0,
            "hot": bool(x.get("hot") or False),
            "last_outcome": str(x.get("last_outcome") or ""),
            "last_call_at": str(x.get("last_call_at") or ""),
            "added_at_raw": str(x.get("added_at") or ""),
            "data": x,
        })
    return out


def _lead_key(row: dict) -> str:
    return row.get("id") or ""


def _id_key(row: dict) -> str:
    """Stable key for id-PK stores (calls/retry_queue/webhooks)."""
    return str(row.get("id") or "")


def _orgphone_key(row: dict) -> str:
    """Stable composite key for the (org_id, phone) PK store (suppression)."""
    return f"{row.get('org_id', '')}|{row.get('phone', '')}"


def _calls_rows(data: Any) -> list[dict]:
    """calls.json is a flat list of call dicts (whole-list _write, like leads). dual-only (NEVER pg:
    in-RAM CALLS cache). Promote indexed/RLS columns; full object in data jsonb (lossless)."""
    out = []
    if not isinstance(data, list):
        return out
    for x in data:
        if not isinstance(x, dict):
            continue
        out.append({
            "id": str(x.get("id") or ""),
            "org_id": str(x.get("tenant_id") or "admin"),
            "campaign_id": str(x.get("campaign_id") or ""),
            "campaign_name": str(x.get("campaign_name") or ""),
            "name": str(x.get("name") or ""),
            "phone": str(x.get("phone") or ""),
            "status": str(x.get("status") or ""),
            "outcome": str(x.get("outcome") or ""),
            "answered": bool(x.get("answered") or False),
            "interest": int(x.get("interest") or 0) if str(x.get("interest") or "0").lstrip("-").isdigit() else 0,
            "variant_id": str(x.get("variant_id") or ""),
            "variant_label": str(x.get("variant_label") or ""),
            "room": str(x.get("room") or ""),
            "sip_call_id": str(x.get("sip_call_id") or ""),
            "duration_s": int(x.get("duration_s") or 0) if str(x.get("duration_s") or "0").lstrip("-").isdigit() else 0,
            "started_at_raw": str(x.get("started_at") or ""),
            "ended_at_raw": str(x.get("ended_at") or ""),
            "data": x,
        })
    return out


def _suppression_rows(data: Any) -> list[dict]:
    """suppression.json is a flat list keyed by (tenant_id, phone) — NO id column. Composite PK."""
    out = []
    if not isinstance(data, list):
        return out
    for x in data:
        if not isinstance(x, dict):
            continue
        org = str(x.get("tenant_id") or "admin")
        phone = str(x.get("phone") or "")
        if not phone:
            continue
        out.append({
            "org_id": org,
            "phone": phone,
            "reason": str(x.get("reason") or ""),
            "source": str(x.get("source") or ""),
            "data": x,
        })
    return out


def _retry_rows(data: Any) -> list[dict]:
    """retry_queue.json flat list (incl. callbacks: reason=='callback'). id-PK."""
    out = []
    if not isinstance(data, list):
        return out
    for x in data:
        if not isinstance(x, dict):
            continue
        out.append({
            "id": str(x.get("id") or ""),
            "org_id": str(x.get("tenant_id") or "admin"),
            "campaign_id": str(x.get("campaign_id") or ""),
            "name": str(x.get("name") or ""),
            "phone": str(x.get("phone") or ""),
            "attempts": int(x.get("attempts") or 0) if str(x.get("attempts") or "0").lstrip("-").isdigit() else 0,
            "max_attempts": int(x.get("max_attempts") or 3) if str(x.get("max_attempts") or "3").lstrip("-").isdigit() else 3,
            "next_attempt_raw": str(x.get("next_attempt_at") or ""),
            "reason": str(x.get("reason") or ""),
            "data": x,
        })
    return out


def _webhooks_rows(data: Any) -> list[dict]:
    """webhooks.json flat list. id-PK. `url` is NOT NULL (no default) — always populate."""
    out = []
    if not isinstance(data, list):
        return out
    for x in data:
        if not isinstance(x, dict):
            continue
        out.append({
            "id": str(x.get("id") or ""),
            "org_id": str(x.get("tenant_id") or "admin"),
            "url": str(x.get("url") or ""),
            "secret": str(x.get("secret") or ""),
            "active": bool(x.get("active", True)),
            "data": x,
        })
    return out


# -------- billing/usage stores (Part A — billing dict, no-id content-hash lists) --------
def _content_id(rec: dict) -> str:
    """DETERMINISTIC synthetic PK for a no-natural-id record (§8): sha256 of the canonical
    serialization of the FULL original record. Computed purely from the record in isolation
    (no positional/occurrence state) so backfill, the live mirror, AND shadow_diff's per-row
    `to_rows([data])` re-derivation ALL produce the IDENTICAL id from the SAME object → JSON↔PG
    is a bijection and shadow_diff reaches a true 0.
    ⚠ COLLISION CAVEAT: two byte-identical records hash to ONE id (one PG row) → json>pg → drift.
    Verified at flip time (distinct sha256 == total count for usage_events/cost_ledger/wa_log on the
    live box) so this is currently safe. If a future byte-identical duplicate ever appears, this is the
    place to add an occurrence-disambiguator — but ONLY one derivable from the record alone (a counter
    would break shadow_diff's per-row re-derivation contract above)."""
    return hashlib.sha256(
        json.dumps(rec, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _billing_rows(data: Any) -> list[dict]:
    """billing.json is a DICT keyed by org_id -> billing record (NOT a list). One row per org_id.
    The whole-dict snapshot spans all tenants, so admin-wide delete-by-omission is correct.
    ⚠ This mapper is dict-aware (unlike the list mappers) — guarding only `isinstance(data,list)`
    would return [] on the dict → empty-snapshot prune would wipe the mirror."""
    out = []
    if not isinstance(data, dict):
        return out
    for org_id, rec in data.items():
        if not isinstance(rec, dict):
            continue
        out.append({
            "org_id": str(org_id),
            "plan": str(rec.get("plan") or "postpaid"),
            "currency": str(rec.get("currency") or "INR"),
            "included_minutes": int(rec.get("included_minutes") or 0)
            if str(rec.get("included_minutes") or "0").lstrip("-").isdigit() else 0,
            "data": rec,
        })
    return out


def _wa_log_rows(data: Any) -> list[dict]:
    """wa_log.json flat list, NO natural id → content-hash PK. {tenant_id,phone,template,kind?,status,ok?,at}."""
    out = []
    if not isinstance(data, list):
        return out
    for x in data:
        if not isinstance(x, dict):
            continue
        out.append({
            "id": _content_id(x),
            "org_id": str(x.get("tenant_id") or ""),
            "phone": str(x.get("phone") or ""),
            "template": str(x.get("template") or ""),
            "kind": str(x.get("kind") or ""),
            "status": str(x.get("status") or ""),
            "ok": bool(x.get("ok") or False),
            "at_raw": str(x.get("at") or ""),
            "data": x,
        })
    return out


def _usage_events_rows(data: Any) -> list[dict]:
    """usage_events.json flat list, NO natural id → content-hash PK.
    {ts,call_id,room,tenant_id,campaign_id,vendor,service_type,qty,unit,est_cost_inr,...}.
    Schema promoted cols differ from JSON field names (units/unit_kind/cost vs qty/unit/est_cost_inr) —
    map what's indexable; the lossless full record is in data jsonb (shadow_diff compares only that)."""
    out = []
    if not isinstance(data, list):
        return out
    for x in data:
        if not isinstance(x, dict):
            continue
        out.append({
            "id": _content_id(x),
            "org_id": str(x.get("tenant_id") or ""),
            "call_id": str(x.get("call_id") or ""),
            "room": str(x.get("room") or ""),
            "vendor": str(x.get("vendor") or ""),
            "unit_kind": str(x.get("unit") or x.get("service_type") or ""),
            "at_raw": str(x.get("ts") or ""),
            "data": x,
        })
    return out


def _cost_ledger_rows(data: Any) -> list[dict]:
    """cost_ledger.json flat list, NO natural id → content-hash PK. Fully REBUILT each _write (@3223).
    {source,ts,call_id,room,tenant_id,campaign_id,vendor,service_type,qty,unit,cost,currency,...}."""
    out = []
    if not isinstance(data, list):
        return out
    for x in data:
        if not isinstance(x, dict):
            continue
        out.append({
            "id": _content_id(x),
            "org_id": str(x.get("tenant_id") or ""),
            "call_id": str(x.get("call_id") or ""),
            "room": str(x.get("room") or ""),
            "campaign_id": str(x.get("campaign_id") or ""),
            "currency": str(x.get("currency") or "INR"),
            "ts_raw": str(x.get("ts") or ""),
            "data": x,
        })
    return out


def _orgid_key(row: dict) -> str:
    """Stable key for the org_id-PK store (billing)."""
    return str(row.get("org_id") or "")


def _ledger_rows(data: Any, stem: str = "") -> list[dict]:
    """ledger is var/ledger/<stem>.json — a per-tenant list of charge records (id-PK). The records
    carry NO tenant_id inside; org_id comes from the file STEM and is promoted into the COLUMN ONLY.
    ⚠ The `data` jsonb stays the VERBATIM record (no org_id injected) — backfill, the live mirror, and
    shadow_diff must all derive `data` identically (the verbatim record) or shadow_diff never reaches 0.
    dual-only (max_safe=dual); whole-(tenant-)file snapshot like leads, but reconciled per stem."""
    out = []
    org = str(stem or "")
    if not isinstance(data, list):
        return out
    for x in data:
        if not isinstance(x, dict):
            continue
        out.append({
            "id": str(x.get("id") or ""),
            "org_id": org,                        # from the file stem (column only)
            "call_id": str(x.get("call_id") or ""),
            "phone": str(x.get("phone") or ""),
            "campaign_id": str(x.get("campaign_id") or ""),
            "duration_s": int(x.get("duration_s") or 0)
            if str(x.get("duration_s") or "0").lstrip("-").isdigit() else 0,
            "cost": x.get("cost") or 0,
            "currency": str(x.get("currency") or "INR"),
            "outcome": str(x.get("outcome") or ""),
            "at_raw": str(x.get("at") or ""),
            "data": x,                            # VERBATIM record — NEVER inject org_id here
        })
    return out


# -------- campaigns (per-id files var/campaigns/<id>.json — per-id UPSERT/DELETE, NOT a snapshot store) --------
def _campaign_row(rec: dict) -> dict:
    """Map ONE campaign record (the dict written to var/campaigns/<id>.json) -> a campaigns-table row.
    org_id == rec['tenant_id'] (VERIFIED top-level on disk). Promote indexed cols; `fields` (the campaign
    fields blob) and the FULL record go into jsonb (lossless). created_at/voice_id left to defaults — the
    parsed timestamp is deferred (same as leads: shadow_diff compares only `data`, never promoted cols).
    Per-ID mirror (NOT a whole-file snapshot): campaigns are written one file at a time via direct
    .write_text (bypassing _write), so the seam can't see them — hence dedicated upsert/delete hooks."""
    fields = rec.get("fields")
    if not isinstance(fields, dict):
        fields = {}
    return {
        "id": str(rec.get("id") or ""),
        "org_id": str(rec.get("tenant_id") or "admin"),
        "name": str(rec.get("name") or ""),
        "company": str(rec.get("company") or ""),
        "product": str(rec.get("product") or ""),
        "status": str(rec.get("status") or "active"),
        "created_at_raw": str(rec.get("created_at") or ""),
        "fields": fields,
        "system_prompt": str(rec.get("system_prompt") or ""),
        "data": rec,
    }


# campaigns promoted columns (excl. fields/data) for the per-id UPSERT.
_CAMPAIGN_COLS = ["id", "org_id", "name", "company", "product", "status", "created_at_raw", "system_prompt"]


def build_campaign_upsert_sql() -> str:
    """Per-id UPSERT for one campaign: INSERT (cols..., fields, data) ON CONFLICT (id) DO UPDATE SET
    <non-id cols>. NO delete-by-omission (campaigns are written one file at a time, not a whole-file
    snapshot — there is no all-tenants snapshot to reconcile against). The explicit DELETE hook handles
    removals. Single source of truth — backfill.py imports this so backfilled rows == the live mirror."""
    cols = list(_CAMPAIGN_COLS)
    collist = ", ".join(cols + ["fields", "data"])
    placeholders = ", ".join(f":{c}" for c in cols) + ", CAST(:fields AS jsonb), CAST(:data AS jsonb)"
    upd = [c for c in cols if c != "id"] + ["fields", "data"]
    setlist = ", ".join(f"{c}=EXCLUDED.{c}" for c in upd)
    return (f"INSERT INTO campaigns ({collist}) VALUES ({placeholders}) "
            f"ON CONFLICT (id) DO UPDATE SET {setlist}")


def _campaigns_mode() -> str:
    """Effective campaigns mode from STORE_MODES (capped at dual — campaigns NEVER freezes to pg: the
    agent reads campaigns/<id>.json directly, so freezing the file would break the live voice agent).
    db down => json. Per §3.2 campaigns is json-authoritative; dual adds a read-replica mirror only."""
    if _db is None:
        return "json"
    try:
        raw = (_config.get("STORE_MODES", "") if _config else "") or ""
    except Exception:
        raw = ""
    for part in raw.split(","):
        part = part.strip()
        if ":" not in part:
            continue
        name, mode = part.split(":", 1)
        name = name.strip()
        mode = mode.strip().lower()
        if name in ("campaigns", "campaigns.json"):
            return "dual" if mode in ("dual", "pg") else "json"
    return "json"


# campaigns is NOT a StoreSpec (per-id files, not the snapshot seam); its status lives here.
_CAMPAIGN_STATE = {"pg_writes_ok": 0, "pg_writes_fail": 0, "last_error": None}


def mirror_campaign_upsert(rec: dict) -> None:
    """LIVE dual-mirror hook called BEST-EFFORT by caller.py AFTER the authoritative .write_text of
    var/campaigns/<id>.json (create @save_campaign, edit @update_campaign). Per-id UPSERT of ONE campaign
    row. NEVER raises into the caller (campaign create/edit is the live earner — must not break). No-op
    unless db up AND campaigns flipped to dual in STORE_MODES (keeps the flag contract: unlisted => json,
    PG idle). Off the request hot path via run_in_executor; no running loop => skip (backfill heals).
    NOT the coalescing snapshot worker (campaigns has no whole-file snapshot — per-id writes)."""
    if _db is None or not _ready:
        return
    if _campaigns_mode() == "json":
        return
    if not isinstance(rec, dict) or not (rec.get("id")):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    try:
        row = _campaign_row(rec)
        loop.run_in_executor(None, _campaign_upsert_row, row)
    except Exception as exc:  # noqa: BLE001 — campaign mirror must never break create/edit
        _CAMPAIGN_STATE["pg_writes_fail"] += 1
        _CAMPAIGN_STATE["last_error"] = f"mirror_campaign_upsert enqueue failed: {exc!r}"[:300]


def mirror_campaign_delete(cid: str) -> None:
    """LIVE dual-mirror hook called BEST-EFFORT by caller.py AFTER the authoritative unlink of
    var/campaigns/<id>.json (@delete_campaign). DELETE the one campaign row. NEVER raises. Same gating +
    off-loop discipline as upsert. A delete that misses (PG already absent) is a harmless no-op."""
    if _db is None or not _ready:
        return
    if _campaigns_mode() == "json":
        return
    cid = str(cid or "")
    if not cid:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    try:
        loop.run_in_executor(None, _campaign_delete_row, cid)
    except Exception as exc:  # noqa: BLE001
        _CAMPAIGN_STATE["pg_writes_fail"] += 1
        _CAMPAIGN_STATE["last_error"] = f"mirror_campaign_delete enqueue failed: {exc!r}"[:300]


def _campaign_upsert_row(row: dict) -> None:
    """Blocking per-id UPSERT (admin GUC — a campaign carries its own org_id, but the mirror batches
    across tenants so admin GUC is consistent with the other mirrors + RLS). Swallows + counts."""
    from sqlalchemy import text
    try:
        sql = build_campaign_upsert_sql()
        params = {k: v for k, v in row.items() if k not in ("fields", "data")}
        params["fields"] = json.dumps(row.get("fields") or {}, ensure_ascii=False)
        params["data"] = json.dumps(row.get("data") or {}, ensure_ascii=False)
        with _db.session("", is_admin=True) as s:
            s.execute(text("SET LOCAL statement_timeout = :ms"), {"ms": str(int(_timeout_ms))})
            s.execute(text(sql), params)
        _CAMPAIGN_STATE["pg_writes_ok"] += 1
        _CAMPAIGN_STATE["last_error"] = None
    except Exception as exc:  # noqa: BLE001
        _CAMPAIGN_STATE["pg_writes_fail"] += 1
        _CAMPAIGN_STATE["last_error"] = f"campaign upsert failed: {exc!r}"[:300]


def _campaign_delete_row(cid: str) -> None:
    """Blocking single-row DELETE (admin GUC). Swallows + counts."""
    from sqlalchemy import text
    try:
        with _db.session("", is_admin=True) as s:
            s.execute(text("SET LOCAL statement_timeout = :ms"), {"ms": str(int(_timeout_ms))})
            s.execute(text("DELETE FROM campaigns WHERE id = :id"), {"id": cid})
        _CAMPAIGN_STATE["pg_writes_ok"] += 1
        _CAMPAIGN_STATE["last_error"] = None
    except Exception as exc:  # noqa: BLE001
        _CAMPAIGN_STATE["pg_writes_fail"] += 1
        _CAMPAIGN_STATE["last_error"] = f"campaign delete failed: {exc!r}"[:300]


# -------- events / audit_log (append-only JSONL, content-hash PK — NOT a snapshot store) --------
def _event_row(ev: dict) -> dict:
    """Map ONE parsed audit JSONL event -> an events-table row. PK = DETERMINISTIC content-hash of the
    parsed dict (sort_keys, ensure_ascii=False) — derived from the dict (NOT the raw line text), because
    audit.record writes json.dumps(ev, ensure_ascii=False) WITHOUT sort_keys, so the raw line is not a
    canonical form. backfill, the live mirror hook, AND shadow_diff ALL re-derive the id from the same
    parsed dict via _content_id → JSON↔PG bijection → shadow_diff reaches a true 0.
    org_id == the event's tenant_id (audit.record defaults tenant_id to actor, the data owner).
    The full original event lives in `data` jsonb (lossless); `meta` is promoted (jsonb). `at` is left to
    its column DEFAULT now() (NOT NULL) — shadow_diff compares only `data`, so the unparsed ts is fine."""
    meta = ev.get("meta")
    if not isinstance(meta, dict):
        meta = {}
    return {
        "id": _content_id(ev),
        "org_id": str(ev.get("tenant_id") or ev.get("actor") or ""),
        "actor": str(ev.get("actor") or ""),
        "action": str(ev.get("action") or ""),
        "object_type": str(ev.get("object_type") or ""),
        "object_id": str(ev.get("object_id") or ""),
        "ip": str(ev.get("ip") or ""),
        "channel": str(ev.get("channel") or "api"),
        "meta": meta,
        "data": ev,
    }


def _events_rows(data: Any) -> list[dict]:
    """List of parsed audit events -> rows. Used by backfill (reads JSONL) + shadow_diff. NOT registered
    in _SPECS / _resolve: events bypasses _write (audit.record open-"a" append), exactly like campaigns,
    so it has no snapshot seam — the live mirror is store.mirror_event (append, ON CONFLICT DO NOTHING)."""
    out = []
    if not isinstance(data, list):
        return out
    for x in data:
        if isinstance(x, dict):
            out.append(_event_row(x))
    return out


# events promoted columns (excl. meta/data) for the append INSERT.
_EVENTS_COLS = ["id", "org_id", "actor", "action", "object_type", "object_id", "ip", "channel"]


def build_events_insert_sql() -> str:
    """Append-only INSERT for events: ON CONFLICT (id) DO NOTHING (idempotent, re-runnable). NO update,
    NO delete-by-omission, NO snapshot reconcile (§3.6: insert+select only). Single source of truth —
    backfill.py imports this so backfilled rows are byte-identical to the live mirror."""
    cols = list(_EVENTS_COLS)
    collist = ", ".join(cols + ["meta", "data"])
    placeholders = ", ".join(f":{c}" for c in cols) + ", CAST(:meta AS jsonb), CAST(:data AS jsonb)"
    return (f"INSERT INTO events ({collist}) VALUES ({placeholders}) "
            f"ON CONFLICT (id) DO NOTHING")


def mirror_event(ev: dict) -> None:
    """LIVE dual-mirror hook for the append-only audit/events store. Called BEST-EFFORT by audit.record
    AFTER the JSONL line is written authoritatively (audit.py lazy-imports this; ZERO caller.py edit).
    Appends one row to events with ON CONFLICT (id) DO NOTHING (the content-hash dedupes vs backfill +
    re-runs). NEVER raises into the audit path; if PG is unavailable / not-events-enabled, no-op (backfill
    heals it later). Off the request hot path: schedules the blocking insert via the running loop's
    executor; if there is no running loop (sync/script context), skips silently.

    IMPORTANT: does NOT use the coalescing depth-1 snapshot worker (that is replace-on-full / last-wins
    and would DROP unique append-only events). Events is a pure append — one INSERT per event."""
    # gate: only mirror when db is up AND events is enabled to dual/pg (don't write PG when operator
    # hasn't flipped events — keeps the flag contract: unlisted store => json-only, PG idle).
    if _db is None or not _ready:
        return
    mode = _events_mode()
    if mode == "json":
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # no loop (import-time / sync script) -> skip; backfill converges it
    try:
        row = _event_row(ev if isinstance(ev, dict) else {})
        # run the blocking insert off the loop thread; fire-and-forget (append is independent per event,
        # no ordering/coalescing concern — unlike the snapshot mirror, two appends never race a key).
        loop.run_in_executor(None, _insert_event_row, row)
    except Exception as exc:  # noqa: BLE001 — auditing must never break the request
        _EVENTS_STATE["pg_writes_fail"] += 1
        _EVENTS_STATE["last_error"] = f"mirror_event enqueue failed: {exc!r}"[:300]


def _insert_event_row(row: dict) -> None:
    """Blocking single-row append INSERT (admin GUC). Increments the events status counters. Swallows."""
    from sqlalchemy import text
    try:
        sql = build_events_insert_sql()
        params = {k: v for k, v in row.items() if k not in ("meta", "data")}
        params["meta"] = json.dumps(row.get("meta") or {}, ensure_ascii=False)
        params["data"] = json.dumps(row.get("data") or {}, ensure_ascii=False)
        with _db.session("", is_admin=True) as s:
            s.execute(text("SET LOCAL statement_timeout = :ms"), {"ms": str(int(_timeout_ms))})
            s.execute(text(sql), params)
        _EVENTS_STATE["pg_writes_ok"] += 1
        _EVENTS_STATE["last_error"] = None
    except Exception as exc:  # noqa: BLE001
        _EVENTS_STATE["pg_writes_fail"] += 1
        _EVENTS_STATE["last_error"] = f"event insert failed: {exc!r}"[:300]


# events is NOT a StoreSpec (no snapshot seam); its mode + status live here.
_EVENTS_STATE = {"pg_writes_ok": 0, "pg_writes_fail": 0, "last_error": None}


def _events_mode() -> str:
    """Effective events mode from STORE_MODES (capped at dual — events never freezes the JSONL). db down
    => json. Append-only, so 'dual' is the max meaningful mode (the JSONL stays authoritative + audited)."""
    if _db is None:
        return "json"
    try:
        raw = (_config.get("STORE_MODES", "") if _config else "") or ""
    except Exception:
        raw = ""
    for part in raw.split(","):
        part = part.strip()
        if ":" not in part:
            continue
        name, mode = part.split(":", 1)
        name = name.strip()
        mode = mode.strip().lower()
        if name in ("events", "events.json", "events.jsonl", "audit_log", "audit"):
            return "dual" if mode in ("dual", "pg") else "json"
    return "json"


# ===================== init / config =====================
def init(read_fn, write_fn, awrite_fn, lock, config) -> bool:
    """Wire store.py to caller.py's raw seam funcs + lock + config. Register specs.
    Returns True if the PG layer is usable (db available); False => everything stays json.
    NEVER raises (degrades to all-json)."""
    global _read_raw, _write_raw, _awrite_raw, _store_lock, _config, _timeout_ms, _db, _ready
    _read_raw = read_fn
    _write_raw = write_fn
    _awrite_raw = awrite_fn
    _store_lock = lock
    _config = config

    try:
        _timeout_ms = int((config.get("STORE_PG_TIMEOUT_MS", "800") if config else "800") or "800")
    except Exception:
        _timeout_ms = 800

    # probe the db layer (import-safe)
    try:
        from db import engine as _engine
        _engine.init(config)
        if _engine.available():
            _db = _engine
    except Exception:
        _db = None

    _register_specs()
    _apply_config_modes(config)

    # If db unavailable, force every store json (the import-safe degrade).
    if _db is None:
        for s in _SPECS.values():
            s.mode = "json"
        if _LEDGER_SPEC is not None:
            _LEDGER_SPEC.mode = "json"

    _ready = True
    return _db is not None


def _register_specs() -> None:
    """Register the stores store.py knows about. Only registered paths are ever touched;
    an unregistered path falls straight through to the original raw funcs.
    P1 batch: leads (pg-capable), calls/suppression/retry_queue/webhooks (dual-capable) are registered
    for mirroring. campaigns is NOT registered (per-id files, json-only by §3.2). Each store stays at
    mode=json until explicitly flipped via STORE_MODES — registration alone is an inert pass-through."""
    if _SPECS:
        return
    _SPECS["leads.json"] = StoreSpec(
        name="leads.json", table="leads", max_safe="pg",
        to_rows=_leads_rows, key=_lead_key,
        cols=["id", "org_id", "name", "phone", "status", "score", "hot",
              "last_outcome", "last_call_at", "added_at_raw"],
        key_cols=["id"], order_by="added_at NULLS FIRST, id",
    )
    # calls: dual-only (NEVER pg — in-RAM CALLS cache + record_call). Whole-list snapshot like leads.
    _SPECS["calls.json"] = StoreSpec(
        name="calls.json", table="calls", max_safe="dual",
        to_rows=_calls_rows, key=_id_key,
        cols=["id", "org_id", "campaign_id", "campaign_name", "name", "phone", "status",
              "outcome", "answered", "interest", "variant_id", "variant_label", "room",
              "sip_call_id", "duration_s", "started_at_raw", "ended_at_raw"],
        key_cols=["id"], order_by="id",
    )
    # suppression: composite (org_id, phone) PK — no id column.
    _SPECS["suppression.json"] = StoreSpec(
        name="suppression.json", table="suppression", max_safe="dual",
        to_rows=_suppression_rows, key=_orgphone_key,
        cols=["org_id", "phone", "reason", "source"],
        key_cols=["org_id", "phone"], order_by="org_id, phone",
    )
    # retry_queue: id-PK (callbacks live here, reason=='callback').
    _SPECS["retry_queue.json"] = StoreSpec(
        name="retry_queue.json", table="retry_queue", max_safe="dual",
        to_rows=_retry_rows, key=_id_key,
        cols=["id", "org_id", "campaign_id", "name", "phone", "attempts",
              "max_attempts", "next_attempt_raw", "reason"],
        key_cols=["id"], order_by="id",
    )
    # webhooks: id-PK.
    _SPECS["webhooks.json"] = StoreSpec(
        name="webhooks.json", table="webhooks", max_safe="dual",
        to_rows=_webhooks_rows, key=_id_key,
        cols=["id", "org_id", "url", "secret", "active"],
        key_cols=["id"], order_by="id",
    )
    # ---- Part A: billing/usage stores (all dual-only — none agent-read, none in-RAM-cached as pg) ----
    # billing: DICT keyed by org_id (org_id-PK). Whole-dict snapshot spans all tenants.
    _SPECS["billing.json"] = StoreSpec(
        name="billing.json", table="billing", max_safe="dual",
        to_rows=_billing_rows, key=_orgid_key,
        cols=["org_id", "plan", "currency", "included_minutes"],
        key_cols=["org_id"], order_by="org_id", dict_store=True,
    )
    # wa_log: flat list, NO natural id -> content-hash PK.
    _SPECS["wa_log.json"] = StoreSpec(
        name="wa_log.json", table="wa_log", max_safe="dual",
        to_rows=_wa_log_rows, key=_id_key,
        cols=["id", "org_id", "phone", "template", "kind", "status", "ok"],
        key_cols=["id"], order_by="id",
    )
    # usage_events: flat list, NO natural id -> content-hash PK.
    _SPECS["usage_events.json"] = StoreSpec(
        name="usage_events.json", table="usage_events", max_safe="dual",
        to_rows=_usage_events_rows, key=_id_key,
        cols=["id", "org_id", "call_id", "room", "vendor", "unit_kind"],
        key_cols=["id"], order_by="id",
    )
    # cost_ledger: flat list, NO natural id -> content-hash PK. Fully rebuilt each _write.
    _SPECS["cost_ledger.json"] = StoreSpec(
        name="cost_ledger.json", table="cost_ledger", max_safe="dual",
        to_rows=_cost_ledger_rows, key=_id_key,
        cols=["id", "org_id", "call_id", "room", "campaign_id", "currency"],
        key_cols=["id"], order_by="id",
    )
    # ---- ledger: PER-TENANT files var/ledger/<stem>.json (multi_file). Resolved by parent-dir match,
    # NOT Path.name (the name is the dynamic <stem>.json). org_id == file stem; id-PK; dual-only.
    # NOT keyed in _SPECS by a file name (it has none) — held in _LEDGER_SPEC + resolved via _resolve().
    global _LEDGER_SPEC
    _LEDGER_SPEC = StoreSpec(
        name="ledger", table="ledger", max_safe="dual",
        to_rows=_ledger_rows, key=_id_key,   # to_rows is called as to_rows(data, stem) for multi_file
        cols=["id", "org_id", "call_id", "phone", "campaign_id",
              "duration_s", "cost", "currency", "outcome", "at_raw"],
        key_cols=["id"], order_by="id", multi_file=True,
    )


def _apply_config_modes(config) -> None:
    """STORE_MODES = comma list 'name:mode' (name without .json ok). Unlisted => json.
    Effective mode = min(configured, max_safe). Empty/absent => all json."""
    raw = ""
    try:
        raw = (config.get("STORE_MODES", "") if config else "") or ""
    except Exception:
        raw = ""
    wanted: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        name, mode = part.split(":", 1)
        name = name.strip()
        mode = mode.strip().lower()
        if mode not in _MODE_RANK:
            continue
        # accept both "leads" and "leads.json"
        key = name if name.endswith(".json") else f"{name}.json"
        wanted[key] = mode
    for key, spec in _SPECS.items():
        w = wanted.get(key, "json")
        capped = min(w, spec.max_safe, key=lambda m: _MODE_RANK[m])
        # leads-pg gating: pg needs a per-request tenant contextvar (R1). Until wired, cap leads at dual.
        if spec.name == "leads.json" and capped == "pg" and not _LEADS_PG_TENANT_WIRED:
            capped = "dual"
        spec.mode = capped
    # ledger (multi_file): config key is "ledger" (no .json). Same cap logic.
    if _LEDGER_SPEC is not None:
        w = wanted.get("ledger.json", "json")  # _apply normalized "ledger" -> "ledger.json"
        _LEDGER_SPEC.mode = min(w, _LEDGER_SPEC.max_safe, key=lambda m: _MODE_RANK[m])


# leads-pg is gated until the per-request tenant contextvar read path is wired (R1/U7).
_LEADS_PG_TENANT_WIRED = False


# ===================== public surface =====================
def available() -> bool:
    return bool(_ready)


def _name(path) -> str:
    try:
        return Path(path).name
    except Exception:
        return str(path)


def _resolve(path):
    """Resolve a path to (spec, stem). The 9 single-file stores hit the IDENTICAL fast path they always
    did — `_SPECS.get(Path(path).name)` first, returning (spec, "") — and NEVER reach the ledger branch.
    Only on a name MISS do we test the multi_file ledger by parent-dir (`<...>/ledger/<stem>.json`),
    returning (_LEDGER_SPEC, <stem>). Anything else -> (None, "")."""
    name = _name(path)
    spec = _SPECS.get(name)
    if spec is not None:
        return spec, ""
    if _LEDGER_SPEC is not None:
        try:
            p = Path(path)
            if p.parent.name == "ledger" and name.endswith(".json"):
                return _LEDGER_SPEC, p.stem
        except Exception:
            return None, ""
    return None, ""


def mode_of(path) -> str:
    """Effective mode for a path. Unregistered or db-down => json (pass-through)."""
    if _db is None:
        return "json"
    spec, _stem = _resolve(path)
    return spec.mode if spec else "json"


def read(path, default):
    """Used by the _read shim. json/dual read the authoritative JSON file (unchanged).
    pg (leads) reads PG; on ANY error falls back to _read_raw + flips to degraded-json. Never raises."""
    spec, _stem = _resolve(path)
    if _db is None or spec is None or spec.mode in ("json", "dual"):
        return _read_raw(path, default)
    # pg mode (leads) — deterministic ORDER BY; rebuild exact original objects from data jsonb.
    try:
        return _pg_read_leads(spec, default)
    except Exception as exc:  # noqa: BLE001
        spec.last_error = f"pg read failed: {exc!r}"[:300]
        spec.mode = "json"   # degrade-to-json for this store
        return _read_raw(path, default)


def write(path, data) -> None:
    """Used by the _write shim. json => original _write_raw ONLY (byte-identical pass-through).
    dual => _write_raw FIRST (authoritative), THEN enqueue a best-effort PG mirror snapshot (B1).
    pg (leads) => write PG, and (default) ALSO shadow-write JSON. Never raises.
    ledger (multi_file): mirror is enqueued PER STEM so two tenants' snapshots never coalesce."""
    spec, stem = _resolve(path)
    if _db is None or spec is None or spec.mode == "json":
        _write_raw(path, data)
        return
    if spec.mode == "dual":
        _write_raw(path, data)              # authoritative, unchanged, fast
        _enqueue_mirror(spec, data, stem)   # O(1) non-blocking; coalescing worker applies latest
        return
    if spec.mode == "pg":
        # P1: leads-pg gated off (capped to dual above); this branch is defensive.
        try:
            _pg_reconcile_leads(spec, data, stem)
            spec.pg_writes_ok += 1
        except Exception as exc:  # noqa: BLE001
            spec.pg_writes_fail += 1
            spec.last_error = f"pg write failed: {exc!r}"[:300]
        _write_raw(path, data)          # shadow-write JSON (rollback insurance)
        return
    _write_raw(path, data)


async def awrite(path, data) -> None:
    """Used by the _awrite shim. DEAD path in P1 (no call sites). Mirrors `write` mechanics:
    JSON write held inside _STORE_LOCK; same coalescing mirror. No second divergent mechanism."""
    spec, stem = _resolve(path)
    if _db is None or spec is None or spec.mode == "json":
        if _store_lock is not None:
            async with _store_lock:
                _write_raw(path, data)
        else:
            _write_raw(path, data)
        return
    if spec.mode in ("dual", "pg"):
        if _store_lock is not None:
            async with _store_lock:
                _write_raw(path, data)
        else:
            _write_raw(path, data)
        _enqueue_mirror(spec, data, stem)
        return
    if _store_lock is not None:
        async with _store_lock:
            _write_raw(path, data)
    else:
        _write_raw(path, data)


def _spec_status(s: StoreSpec) -> dict:
    if s.multi_file:
        worker = any(w and not w.done() for w in s._workers.values())
    else:
        worker = bool(s._worker and not s._worker.done()) if s._worker else False
    return {
        "mode": s.mode,
        "max_safe": s.max_safe,
        "pg_writes_ok": s.pg_writes_ok,
        "pg_writes_fail": s.pg_writes_fail,
        "last_error": s.last_error,
        "last_shadow_diff": s.last_shadow_diff,
        "worker": worker,
    }


def status() -> dict:
    out = {}
    for name, s in _SPECS.items():
        out[name] = _spec_status(s)
    if _LEDGER_SPEC is not None:
        out["ledger"] = _spec_status(_LEDGER_SPEC)
    # events (append-only, not a StoreSpec) — surface mode + counters for /admin/store-status.
    out["events"] = {
        "mode": _events_mode(),
        "max_safe": "dual",
        "pg_writes_ok": _EVENTS_STATE["pg_writes_ok"],
        "pg_writes_fail": _EVENTS_STATE["pg_writes_fail"],
        "last_error": _EVENTS_STATE["last_error"],
        "last_shadow_diff": None,
        "worker": False,  # append path uses the loop executor, not a long-lived worker
    }
    # campaigns (per-id files, not a StoreSpec) — per-id upsert/delete hooks (dual-only, never pg).
    out["campaigns"] = {
        "mode": _campaigns_mode(),
        "max_safe": "dual",
        "pg_writes_ok": _CAMPAIGN_STATE["pg_writes_ok"],
        "pg_writes_fail": _CAMPAIGN_STATE["pg_writes_fail"],
        "last_error": _CAMPAIGN_STATE["last_error"],
        "last_shadow_diff": None,
        "worker": False,  # per-id hooks use the loop executor, not a long-lived worker
    }
    db_status = {}
    try:
        if _db is not None:
            db_status = _db.status()
    except Exception:
        db_status = {}
    return {"db": db_status, "ready": _ready, "stores": out}


# ===================== PG read / mirror internals =====================
def _pg_read_leads(spec: StoreSpec, default):
    """Read a store from PG as the caller's tenant (R1: requires per-request tenant contextvar).
    NOT reached in P1 (every store capped at dual). Defensive impl using admin GUC as placeholder."""
    from sqlalchemy import text
    with _db.session("", is_admin=True) as s:  # placeholder; U7 wires per-request tenant scope
        rows = s.execute(text(
            f"SELECT data FROM {spec.table} ORDER BY {spec.order_by}"
        )).fetchall()
    return [r[0] for r in rows]


def _enqueue_mirror(spec: StoreSpec, data, stem: str = "") -> None:
    """O(1) non-blocking enqueue of the LATEST whole-file snapshot (B1). Replace-on-full (depth 1).
    Safe to call while holding _STORE_LOCK (the two hot leads writers do). If no running loop
    (import-time / sync script), skip the mirror silently.

    Single-file stores (all 9): ONE queue/worker on spec._queue/_worker — BYTE-UNCHANGED path.
    multi_file ledger: a queue/worker PER STEM (spec._queues[stem]/_workers[stem]) so writes to
    tenant A's file never coalesce with tenant B's in one depth-1 queue (the B1-class loss the
    build_log flagged). stem is carried into the worker so the reconcile is org-scoped.

    The ENTIRE body is wrapped so it can NEVER raise into the _write shim — the authoritative JSON
    write has already returned to the caller (which may be holding _STORE_LOCK); a mirror SETUP failure
    (queue create / create_task) must be swallowed+counted exactly like a mirror WRITE failure (§6.4b)."""
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no loop -> can't run the async worker; skip mirror (json file already written)
        if spec.multi_file:
            q = spec._queues.get(stem)
            w = spec._workers.get(stem)
            if q is None or w is None or w.done():
                q = asyncio.Queue(maxsize=1)
                spec._queues[stem] = q
                spec._workers[stem] = loop.create_task(_mirror_worker(spec, stem, q))
        else:
            q = spec._queue
            if q is None or spec._worker is None or spec._worker.done():
                # lazily start the single per-store worker on the running loop
                q = asyncio.Queue(maxsize=1)
                spec._queue = q
                spec._worker = loop.create_task(_mirror_worker(spec, "", q))
        # replace-on-full: always keep only the newest snapshot (last-snapshot-wins is correct)
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
            except Exception:
                pass
            try:
                q.put_nowait(data)
            except Exception:
                pass
    except Exception as exc:  # noqa: BLE001 — mirror setup must never break the request
        spec.pg_writes_fail += 1
        spec.last_error = f"mirror enqueue failed: {exc!r}"[:300]


async def _mirror_worker(spec: StoreSpec, stem: str, q: "asyncio.Queue") -> None:
    """Long-lived worker draining ONE queue to the LATEST snapshot, applying it with a hard timeout,
    swallowing+counting failures. Coalesces bursts (only newest matters: whole-(tenant-)file snapshot).
    For single-file stores stem=="" (one worker); for multi_file ledger, one worker PER STEM."""
    while True:
        snapshot = await q.get()
        # coalesce: if more snapshots are already queued, skip to the newest
        while not q.empty():
            try:
                snapshot = q.get_nowait()
            except Exception:
                break
        try:
            # Run the reconcile in a thread (the worker awaits it SEQUENTIALLY — no wait_for/cancel,
            # which would leave the thread committing a stale snapshot while the next one starts and
            # re-introduce a B1-class last-writer race). Slowness is bounded DB-side by statement_timeout
            # (set in _pg_reconcile_leads's session), not by cancelling the Python await.
            await asyncio.to_thread(_pg_reconcile_leads, spec, snapshot, stem)
            spec.pg_writes_ok += 1
            spec.last_error = None
        except Exception as exc:  # noqa: BLE001
            spec.pg_writes_fail += 1
            spec.last_error = f"mirror failed: {exc!r}"[:300]


def build_upsert_sql(spec: StoreSpec) -> str:
    """Spec-driven UPSERT: INSERT (cols..., data) ... ON CONFLICT (key_cols) DO UPDATE SET <non-key cols>.
    Single source of truth — backfill.py imports this so backfilled rows are byte-identical to the
    live mirror (same column list, same CAST(:data AS jsonb), same conflict target)."""
    cols = list(spec.cols)
    collist = ", ".join(cols + ["data"])
    placeholders = ", ".join(f":{c}" for c in cols) + ", CAST(:data AS jsonb)"
    conflict = ", ".join(spec.key_cols)
    upd_cols = [c for c in cols if c not in spec.key_cols] + ["data"]
    setlist = ", ".join(f"{c}=EXCLUDED.{c}" for c in upd_cols)
    return (f"INSERT INTO {spec.table} ({collist}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict}) DO UPDATE SET {setlist}")


def _delete_by_omission_sql(spec: StoreSpec, org_scoped: bool = False) -> str:
    """DELETE every row whose composite key is not in the incoming snapshot.
    Uses a per-key-column ANY(:col_vals) array filter (works for id-PK and (org_id,phone) PK alike):
        DELETE FROM t WHERE NOT ( (k1,k2) IN (SELECT * FROM unnest(:k1[], :k2[])) )
    Implemented portably via a row-tuple NOT IN against unnested arrays.

    org_scoped (multi_file ledger): a single _write is ONE tenant's snapshot, so the delete MUST be
    scoped to that tenant — `WHERE org_id=:org AND <key> NOT IN(...)` — or it would wipe every OTHER
    tenant's ledger rows (whose ids aren't in this tenant's snapshot)."""
    kc = spec.key_cols
    tup = "(" + ", ".join(kc) + ")"
    unnest = "unnest(" + ", ".join(f":kc_{c}" for c in kc) + ")"
    src = "(" + ", ".join(kc) + ")"
    scope = "org_id = :org AND " if org_scoped else ""
    return f"DELETE FROM {spec.table} WHERE {scope}{tup} NOT IN (SELECT * FROM {unnest} AS u{src})"


def _pg_reconcile_leads(spec: StoreSpec, snapshot, stem: str = "") -> None:
    """FULL-SNAPSHOT reconcile in ONE txn (B2 guarded), spec-driven for ANY registered store:
    UPSERT every keyed row in the snapshot AND DELETE rows whose key is not present. Admin GUC
    (a whole-file snapshot spans tenants).
    (Name kept `_pg_reconcile_leads` for call-site stability; it is now generic over `spec`.)

    multi_file (ledger): the snapshot is ONE tenant's file; `stem` is the tenant/org_id (records carry
    no tenant_id). to_rows is called as to_rows(snapshot, stem) to promote org_id into the column. ALL
    deletes are org-SCOPED (delete-by-omission AND the empty branch) so a single tenant's write can
    NEVER touch another tenant's rows.

    EMPTY-SNAPSHOT handling (B2, mode-scoped — this is the subtle correctness point):
      * In `dual` mode the snapshot IS the payload that `_write_raw` just wrote AUTHORITATIVELY to the
        JSON file (NOT a re-read that could transiently fail) — so an empty snapshot is GROUND TRUTH
        (JSON is now [] too) and PG MUST be pruned to match, else a legitimately-cleared store drifts
        to shadow_diff>0 forever. We prune (org-scoped for ledger; whole-table otherwise — also dodges
        the empty-array unnest cast).
      * In `pg` mode there is NO JSON backstop, so an empty/failed snapshot wiping PG is real data loss
        → keep the B2 skip-on-empty guard. (leads-pg is gated off in P1, so this is defensive.)"""
    from sqlalchemy import text
    rows = spec.to_rows(snapshot, stem) if spec.multi_file else spec.to_rows(snapshot)
    keyed = [r for r in rows if spec.key(r)]
    incoming_keys = [spec.key(r) for r in keyed]
    upsert_sql = build_upsert_sql(spec)
    with _db.session("", is_admin=True) as s:
        # bound a slow/locked reconcile DB-side (the worker no longer cancels the await — see worker note)
        s.execute(text("SET LOCAL statement_timeout = :ms"), {"ms": str(int(_timeout_ms))})
        for r in keyed:
            params = {k: v for k, v in r.items() if k != "data"}
            params["data"] = json.dumps(r["data"], ensure_ascii=False)
            s.execute(text(upsert_sql), params)
        if incoming_keys:
            del_params = {f"kc_{c}": [r[c] for r in keyed] for c in spec.key_cols}
            if spec.multi_file:
                del_params["org"] = stem
            s.execute(text(_delete_by_omission_sql(spec, org_scoped=spec.multi_file)), del_params)
        elif spec.mode == "pg":
            pass  # B2: pg mode has no JSON backstop — never wipe from an empty/failed snapshot
        elif spec.multi_file:
            # dual ledger: an empty tenant snapshot prunes ONLY that tenant's rows (NEVER bare DELETE).
            s.execute(text(f"DELETE FROM {spec.table} WHERE org_id = :org"), {"org": stem})
        else:
            # dual: empty snapshot == authoritative empty JSON → prune PG to match (converge to 0)
            s.execute(text(f"DELETE FROM {spec.table}"))
