"""shadow_diff.py — P1 JSON↔PG drift report (design §8).

    python shadow_diff.py <entity>      # exit 0 iff PG matches JSON, nonzero on any drift

Compares the authoritative JSON store against its PG table for one entity and reports:
  (a) row COUNT, (b) the set of IDs (+only_json / +only_pg), (c) per-id the `data jsonb`
  vs the JSON object, normalized identically on both sides (json.dumps sort_keys=True,
  ensure_ascii=False). Promoted/indexed columns (score/hot/added_at…) are DELIBERATELY NOT
  compared — the row-mapper coerces them (str→int, →bool), so comparing them would show
  false drift; the lossless `data jsonb` is the source of truth (spec §8 + §3 R3).

Runs with the ADMIN GUC (db.session("", is_admin=True)) — a whole-store diff spans tenants,
so RLS must not hide rows. This is the gate before any dual→pg flip and the periodic drift
report. Inert: imported by nothing in the running service; safe to run anytime (R8: prefer
quiescence so a transient dual-mirror lag isn't misread as drift).

It reuses store.py's row-mapper + key fn so the id derivation and `data` payload are byte-for-byte
what the live dual mirror writes — guaranteeing a true 0 when (and only when) they actually match.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# repo root = this file's dir (deployed to /opt/famit-agent alongside caller.py/store.py/db/)
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VAR = ROOT / "var"

# ---- config shim mirroring caller.py's _StoreConfigShim (.get surface for db.engine) ----
try:
    import config as _cfg  # type: ignore

    def _cfg_get(key, default=""):
        try:
            return _cfg.get(key, default)
        except Exception:
            import os
            return os.getenv(key, default)
except Exception:  # config.py unimportable -> pure env
    import os

    def _cfg_get(key, default=""):
        return os.getenv(key, default)


class _ConfigShim:
    @staticmethod
    def get(key, default=""):
        return _cfg_get(key, default)


def _norm(obj) -> str:
    """Canonical, comparison-stable serialization — identical on JSON side and PG `data` side."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def _load_json_store(filename: str):
    """Load a JSON store verbatim (list OR dict). billing.json is a dict keyed by org_id; the spec's
    to_rows handles either shape — do NOT coerce a dict to [] (that would drop every billing row)."""
    p = VAR / filename
    try:
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, (list, dict)):
                return d
    except Exception:
        return []
    return []


def _store_spec(entity: str):
    """Resolve a store.py StoreSpec by entity name. Reuses the LIVE registry so the key derivation
    and `data` payload are byte-for-byte what the dual mirror writes (no caller.py import)."""
    import store
    store._register_specs()
    return store._SPECS.get(f"{entity}.json")


def diff(entity: str) -> int:
    """Return the number of drifting keys (0 == perfect match). Prints a capped report.
    Key-agnostic: derives the same stable key (id, or composite e.g. org_id|phone) on BOTH the JSON
    and PG sides via the spec's mapper+key fn, so suppression (no `id` column) diffs correctly."""
    import store
    from db import engine as eng
    from sqlalchemy import text

    eng.init(_ConfigShim)
    if not eng.available():
        print(f"shadow_diff {entity}: ABORT — Postgres unavailable (db.engine.available()=False)")
        return 2

    sp = _store_spec(entity)
    if sp is None:
        known = ",".join(k[:-5] for k in sorted(store._SPECS))
        print(f"shadow_diff: unknown entity '{entity}' (known: {known})")
        return 2

    # JSON side: object list/dict -> {key: normalized_object}
    objs = _load_json_store(sp.name)
    rows = sp.to_rows(objs)  # same mapper the mirror uses (key derivation identical)
    json_map: dict[str, str] = {}
    for r in rows:
        rid = sp.key(r)
        if not rid:
            continue  # the mirror/upsert skips empty-key rows too
        json_map[rid] = _norm(r["data"])

    # PG side: admin GUC so RLS doesn't hide cross-tenant rows. Read ONLY `data` (no `id` column on
    # composite-PK stores like suppression); re-derive the key with the SAME mapper+key fn.
    # dict_store (billing): the bare record in `data` has no org_id inside it (org_id was the dict KEY),
    # so we also read the org_id column and wrap as {org_id: data} to re-feed the dict-shaped mapper.
    pg_map: dict[str, str] = {}
    with eng.session("", is_admin=True) as s:
        if sp.dict_store:
            for (org_id, data) in s.execute(
                text(f"SELECT org_id, data FROM {sp.table}")
            ).fetchall():
                mapped = sp.to_rows({org_id: data})
                rid = sp.key(mapped[0]) if mapped else ""
                if not rid:
                    continue
                pg_map[rid] = _norm(data)
        else:
            for (data,) in s.execute(text(f"SELECT data FROM {sp.table}")).fetchall():
                mapped = sp.to_rows([data])
                rid = sp.key(mapped[0]) if mapped else ""
                if not rid:
                    continue
                pg_map[rid] = _norm(data)

    json_ids, pg_ids = set(json_map), set(pg_map)
    only_json = sorted(json_ids - pg_ids)
    only_pg = sorted(pg_ids - json_ids)
    field_drift = sorted(i for i in (json_ids & pg_ids) if json_map[i] != pg_map[i])

    drift = len(only_json) + len(only_pg) + len(field_drift)
    print(f"shadow_diff {entity}: json={len(json_ids)} pg={len(pg_ids)} "
          f"only_json={len(only_json)} only_pg={len(only_pg)} field_drift={len(field_drift)} "
          f"=> shadow_diff={drift}")
    if only_json:
        print(f"  +only_json (in JSON, missing in PG): {only_json[:10]}")
    if only_pg:
        print(f"  +only_pg   (in PG, missing in JSON): {only_pg[:10]}")
    for i in field_drift[:10]:
        print(f"  ~field_drift id={i}")
        print(f"     json: {json_map[i][:200]}")
        print(f"     pg  : {pg_map[i][:200]}")
    return drift


def diff_identity() -> int:
    """Parity check for the orgs/users/memberships ADDITIVE mirror (not a 1:1 file->table store).
    Returns the number of mismatching tenants (0 == perfect). Each tenant in tenants.json must map to
    exactly one org (id==tenant_id), one user (id==org_id==tenant_id, is_admin/role/email carried), and
    one membership (org_id==user_id==tenant_id). Auth still reads tenants.json — this only proves the
    mirror is seeded + consistent."""
    from db import engine as eng
    from sqlalchemy import text

    eng.init(_ConfigShim)
    if not eng.available():
        print("shadow_diff identity: ABORT — Postgres unavailable")
        return 2

    p = VAR / "tenants.json"
    tenants = []
    try:
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
        if isinstance(d, list):
            tenants = [t for t in d if isinstance(t, dict)]
        elif isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, dict):
                    v = dict(v); v.setdefault("tenant_id", k); tenants.append(v)
    except Exception:
        tenants = []

    tids = {str(t.get("tenant_id") or "") for t in tenants if t.get("tenant_id")}

    with eng.session("", is_admin=True) as s:
        org_ids = {r[0] for r in s.execute(text("SELECT id FROM orgs")).fetchall()}
        user_ids = {r[0] for r in s.execute(text("SELECT id FROM users")).fetchall()}
        user_orgs = {r[0]: r[1] for r in s.execute(text("SELECT id, org_id FROM users")).fetchall()}
        mem_pairs = {(r[0], r[1]) for r in s.execute(
            text("SELECT org_id, user_id FROM memberships")).fetchall()}

    missing_org = sorted(tids - org_ids)
    missing_user = sorted(tids - user_ids)
    missing_mem = sorted(t for t in tids if (t, t) not in mem_pairs)
    bad_user_org = sorted(t for t in (tids & set(user_orgs)) if user_orgs[t] != t)
    # orphans: PG rows for a tenant no longer in tenants.json (mirror should not have extras)
    extra_org = sorted(org_ids - tids)
    extra_user = sorted(user_ids - tids)

    drift = (len(missing_org) + len(missing_user) + len(missing_mem)
             + len(bad_user_org) + len(extra_org) + len(extra_user))
    print(f"shadow_diff identity: tenants={len(tids)} orgs={len(org_ids)} users={len(user_ids)} "
          f"memberships={len(mem_pairs)} missing_org={len(missing_org)} missing_user={len(missing_user)} "
          f"missing_mem={len(missing_mem)} bad_user_org={len(bad_user_org)} "
          f"extra_org={len(extra_org)} extra_user={len(extra_user)} => shadow_diff={drift}")
    if missing_org:
        print(f"  +missing_org: {missing_org[:10]}")
    if missing_user:
        print(f"  +missing_user: {missing_user[:10]}")
    if missing_mem:
        print(f"  +missing_mem: {missing_mem[:10]}")
    if bad_user_org:
        print(f"  ~bad_user_org (user.org_id != tenant_id): {bad_user_org[:10]}")
    if extra_org or extra_user:
        print(f"  +extra_org={extra_org[:10]} extra_user={extra_user[:10]}")
    return drift


def diff_ledger() -> int:
    """ledger drift: union over ALL var/ledger/<stem>.json files vs the PG ledger table (admin GUC).
    id-keyed; compares the verbatim `data` jsonb on both sides (the records carry no tenant_id, so we do
    NOT compare org_id — it lives in the column only, derived from the stem). Returns drifting-key count."""
    import store
    from db import engine as eng
    from sqlalchemy import text

    eng.init(_ConfigShim)
    if not eng.available():
        print("shadow_diff ledger: ABORT — Postgres unavailable")
        return 2

    store._register_specs()
    sp = store._LEDGER_SPEC
    if sp is None:
        print("shadow_diff ledger: ABORT — ledger spec not registered")
        return 2

    ledger_dir = VAR / "ledger"
    files = sorted(ledger_dir.glob("*.json")) if ledger_dir.exists() else []
    json_map: dict[str, str] = {}
    for f in files:
        try:
            objs = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(objs, list):
            continue
        for r in sp.to_rows(objs, f.stem):
            rid = sp.key(r)
            if rid:
                json_map[rid] = _norm(r["data"])

    pg_map: dict[str, str] = {}
    with eng.session("", is_admin=True) as s:
        for (rid, data) in s.execute(text("SELECT id, data FROM ledger")).fetchall():
            if rid:
                pg_map[rid] = _norm(data)

    json_ids, pg_ids = set(json_map), set(pg_map)
    only_json = sorted(json_ids - pg_ids)
    only_pg = sorted(pg_ids - json_ids)
    field_drift = sorted(i for i in (json_ids & pg_ids) if json_map[i] != pg_map[i])
    drift = len(only_json) + len(only_pg) + len(field_drift)
    print(f"shadow_diff ledger: files={len(files)} json={len(json_ids)} pg={len(pg_ids)} "
          f"only_json={len(only_json)} only_pg={len(only_pg)} field_drift={len(field_drift)} "
          f"=> shadow_diff={drift}")
    if only_json:
        print(f"  +only_json: {only_json[:10]}")
    if only_pg:
        print(f"  +only_pg: {only_pg[:10]}")
    for i in field_drift[:10]:
        print(f"  ~field_drift id={i}")
        print(f"     json: {json_map[i][:200]}")
        print(f"     pg  : {pg_map[i][:200]}")
    return drift


def _load_audit_events() -> list[dict]:
    """Read the append-only audit JSONL (var/audit_log.jsonl + rotated .1) into parsed event dicts.
    Same loader contract as backfill (skip blank/unparseable lines) so json/pg sides agree exactly."""
    out: list[dict] = []
    for fn in ("audit_log.jsonl.1", "audit_log.jsonl"):
        p = VAR / fn
        if not p.exists():
            continue
        try:
            with open(p, "r", encoding="utf-8") as fh:
                for ln in fh:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        ev = json.loads(ln)
                    except Exception:
                        continue
                    if isinstance(ev, dict):
                        out.append(ev)
        except Exception:
            continue
    return out


def diff_events() -> int:
    """events drift: the audit JSONL vs the PG events table (admin GUC). Append-only, content-hash PK:
    JSON side maps each event via store._events_rows (id = content-hash of the dict); PG side reads
    `data` and RE-DERIVES the id with store._event_row(data) (identical content-hash) so the id-set +
    `data` jsonb compare byte-for-byte. NO snapshot/prune — only_pg flags an unexpected PG-extra row
    (should be 0; an immutable store never deletes, so PG only grows toward JSON, never past it)."""
    import store
    from db import engine as eng
    from sqlalchemy import text

    eng.init(_ConfigShim)
    if not eng.available():
        print("shadow_diff events: ABORT — Postgres unavailable")
        return 2

    evs = _load_audit_events()
    json_map: dict[str, str] = {}
    for r in store._events_rows(evs):
        rid = r.get("id")
        if rid:
            json_map[rid] = _norm(r["data"])

    pg_map: dict[str, str] = {}
    with eng.session("", is_admin=True) as s:
        for (data,) in s.execute(text("SELECT data FROM events")).fetchall():
            rid = store._event_row(data).get("id") if isinstance(data, dict) else ""
            if rid:
                pg_map[rid] = _norm(data)

    json_ids, pg_ids = set(json_map), set(pg_map)
    only_json = sorted(json_ids - pg_ids)
    only_pg = sorted(pg_ids - json_ids)
    field_drift = sorted(i for i in (json_ids & pg_ids) if json_map[i] != pg_map[i])
    drift = len(only_json) + len(only_pg) + len(field_drift)
    print(f"shadow_diff events: json={len(json_ids)} pg={len(pg_ids)} "
          f"only_json={len(only_json)} only_pg={len(only_pg)} field_drift={len(field_drift)} "
          f"=> shadow_diff={drift}")
    if only_json:
        print(f"  +only_json (in JSONL, missing in PG): {only_json[:10]}")
    if only_pg:
        print(f"  +only_pg   (in PG, missing in JSONL): {only_pg[:10]}")
    for i in field_drift[:10]:
        print(f"  ~field_drift id={i}")
        print(f"     json: {json_map[i][:200]}")
        print(f"     pg  : {pg_map[i][:200]}")
    return drift


def diff_campaigns() -> int:
    """campaigns drift: the per-id files var/campaigns/<id>.json vs the PG campaigns table (admin GUC).
    id-keyed; compares the verbatim `data` jsonb on both sides via store._campaign_row (so the id + data
    derivation is byte-identical to the live mirror hooks). only_pg flags a stale PG row whose file was
    deleted (the live delete hook should prevent it; a residual means the delete mirror missed)."""
    import store
    from db import engine as eng
    from sqlalchemy import text

    eng.init(_ConfigShim)
    if not eng.available():
        print("shadow_diff campaigns: ABORT — Postgres unavailable")
        return 2

    cdir = VAR / "campaigns"
    json_map: dict[str, str] = {}
    if cdir.exists():
        for p in sorted(cdir.glob("*.json")):
            nm = p.name.lower()
            if ".bak" in nm or "winrestore" in nm:
                continue
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(d, dict) and d.get("id"):
                r = store._campaign_row(d)
                json_map[r["id"]] = _norm(r["data"])

    pg_map: dict[str, str] = {}
    with eng.session("", is_admin=True) as s:
        for (rid, data) in s.execute(text("SELECT id, data FROM campaigns")).fetchall():
            if rid:
                pg_map[rid] = _norm(data)

    json_ids, pg_ids = set(json_map), set(pg_map)
    only_json = sorted(json_ids - pg_ids)
    only_pg = sorted(pg_ids - json_ids)
    field_drift = sorted(i for i in (json_ids & pg_ids) if json_map[i] != pg_map[i])
    drift = len(only_json) + len(only_pg) + len(field_drift)
    print(f"shadow_diff campaigns: json={len(json_ids)} pg={len(pg_ids)} "
          f"only_json={len(only_json)} only_pg={len(only_pg)} field_drift={len(field_drift)} "
          f"=> shadow_diff={drift}")
    if only_json:
        print(f"  +only_json (file present, missing in PG): {only_json[:10]}")
    if only_pg:
        print(f"  +only_pg   (in PG, file deleted): {only_pg[:10]}")
    for i in field_drift[:10]:
        print(f"  ~field_drift id={i}")
        print(f"     json: {json_map[i][:200]}")
        print(f"     pg  : {pg_map[i][:200]}")
    return drift


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python shadow_diff.py <entity>   "
              "(entity 'identity' = orgs/users/memberships parity; 'ledger' = per-tenant files; "
              "'events' = audit_log.jsonl append-only; 'campaigns' = per-id files)")
        return 2
    if argv[1] == "identity":
        d = diff_identity()
    elif argv[1] == "ledger":
        d = diff_ledger()
    elif argv[1] in ("events", "audit", "audit_log"):
        d = diff_events()
    elif argv[1] == "campaigns":
        d = diff_campaigns()
    else:
        d = diff(argv[1])
    return 0 if d == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
