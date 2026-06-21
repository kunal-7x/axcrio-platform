"""backfill.py — P1 idempotent JSON→PG loader (design §8).

    python backfill.py <entity>            # DRY-RUN: read JSON, map rows, print counts, write NOTHING
    python backfill.py <entity> --commit   # UPSERT rows into PG (idempotent, re-runnable)

Prints:  BACKFILL <entity>: json=<n> pg=<m> upserted=<k>
  json     = objects in the JSON store that map to a non-empty id
  pg        = rows in the PG table AFTER the run (or current, in dry-run)
  upserted = rows INSERTed/UPDATEd this run (0 in dry-run)

Idempotent UPSERT by natural id (ON CONFLICT (id) DO UPDATE) — re-running converges, never
duplicates. Uses the SAME row-mapper as the live dual mirror (store._leads_rows) and the SAME
column list / CAST(:data AS jsonb) as store._pg_reconcile_leads, so a backfilled row is byte-
identical to what the mirror would write → shadow_diff.py reaches a true 0.

Runs with the ADMIN GUC (db.session("", is_admin=True)) since it batches all tenants. UPSERT-only:
it deliberately does NOT delete-by-omission (that is the live mirror's whole-file-snapshot job, with
the §6/B2 empty-snapshot guard). Backfill only ever ADDS/refreshes historical rows; pruning is the
mirror's responsibility once leads is at dual/pg. Inert: imported by nothing in the running service.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VAR = ROOT / "var"

try:
    import config as _cfg  # type: ignore

    def _cfg_get(key, default=""):
        try:
            return _cfg.get(key, default)
        except Exception:
            import os
            return os.getenv(key, default)
except Exception:
    import os

    def _cfg_get(key, default=""):
        return os.getenv(key, default)


class _ConfigShim:
    @staticmethod
    def get(key, default=""):
        return _cfg_get(key, default)


def _load_json_store(filename: str):
    """Load a JSON store verbatim (list OR dict). billing.json is a dict keyed by org_id; every
    other registered store is a list. The spec's to_rows handles whichever shape it receives, so
    we MUST NOT coerce a dict to [] here (that would yield 0 rows for billing)."""
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
    """Resolve a store.py StoreSpec by entity name (e.g. 'leads' -> 'leads.json').
    Reuses the LIVE registry so column list / mapper / key / UPSERT SQL are byte-identical to the
    dual mirror — guaranteeing backfilled rows match and shadow_diff reaches a true 0."""
    import store
    store._register_specs()
    return store._SPECS.get(f"{entity}.json")


def backfill(entity: str, commit: bool) -> int:
    import store
    from db import engine as eng
    from sqlalchemy import text

    eng.init(_ConfigShim)
    if not eng.available():
        print(f"BACKFILL {entity}: ABORT — Postgres unavailable")
        return 2

    sp = _store_spec(entity)
    if sp is None:
        known = ",".join(k[:-5] for k in sorted(store._SPECS))
        print(f"BACKFILL: unknown entity '{entity}' (known: {known})")
        return 2

    upsert_sql = store.build_upsert_sql(sp)
    objs = _load_json_store(sp.name)
    rows = [r for r in sp.to_rows(objs) if sp.key(r)]  # drop empty-key rows (mirror does too)
    n_json = len(rows)
    upserted = 0

    with eng.session("", is_admin=True) as s:
        if commit:
            for r in rows:
                params = {k: v for k, v in r.items() if k != "data"}
                params["data"] = json.dumps(r["data"], ensure_ascii=False)
                s.execute(text(upsert_sql), params)
                upserted += 1
            # session() commits on context exit
        n_pg = s.execute(text(f"SELECT count(*) FROM {sp.table}")).scalar() or 0

    mode = "" if commit else " (DRY-RUN, no write — pass --commit)"
    print(f"BACKFILL {entity}: json={n_json} pg={n_pg} upserted={upserted}{mode}")
    return 0


def _load_tenants() -> list[dict]:
    """tenants.json is a flat LIST of tenant dicts (verified on box): each has tenant_id, name,
    email, is_admin, role, pass_hash, salt. Authoritative for auth — we only MIRROR it into PG."""
    p = VAR / "tenants.json"
    try:
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, list):
                return [t for t in d if isinstance(t, dict)]
            if isinstance(d, dict):  # defensive: dict keyed by tenant_id
                out = []
                for k, v in d.items():
                    if isinstance(v, dict):
                        v = dict(v)
                        v.setdefault("tenant_id", k)
                        out.append(v)
                return out
    except Exception:
        return []
    return []


def backfill_identity(commit: bool) -> int:
    """orgs/users/memberships are NOT a file->table mirror — they are a 1->3 fan-out DERIVED from
    tenants.json (design §3.1, §5 ADDITIVE mirror): each existing tenant -> one org + its admin/manager
    user + a (org,user) membership. id == tenant_id for both org and the seeded single user; the user's
    org_id == tenant_id; membership == (tenant_id, tenant_id). is_admin/role/email/pass_hash/salt carried
    verbatim (mirror only — auth still reads tenants.json). Idempotent UPSERT by PK, re-runnable.

    This is its OWN path (not the spec-driven backfill) because there is no JSON file per table and the
    mapping is a fan-out, not a 1:1 row copy. Order: orgs -> users (FK org_id) -> memberships (FK both)."""
    from db import engine as eng
    from sqlalchemy import text

    eng.init(_ConfigShim)
    if not eng.available():
        print("BACKFILL identity: ABORT — Postgres unavailable")
        return 2

    tenants = _load_tenants()
    n_json = len(tenants)
    up_orgs = up_users = up_mem = 0

    org_sql = (
        "INSERT INTO orgs (id, name, is_admin, data) "
        "VALUES (:id, :name, :is_admin, CAST(:data AS jsonb)) "
        "ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, is_admin=EXCLUDED.is_admin, data=EXCLUDED.data"
    )
    user_sql = (
        "INSERT INTO users (id, org_id, email, name, role, is_admin, pass_hash, salt, data) "
        "VALUES (:id, :org_id, :email, :name, :role, :is_admin, :pass_hash, :salt, CAST(:data AS jsonb)) "
        "ON CONFLICT (id) DO UPDATE SET org_id=EXCLUDED.org_id, email=EXCLUDED.email, name=EXCLUDED.name, "
        "role=EXCLUDED.role, is_admin=EXCLUDED.is_admin, pass_hash=EXCLUDED.pass_hash, salt=EXCLUDED.salt, "
        "data=EXCLUDED.data"
    )
    mem_sql = (
        "INSERT INTO memberships (org_id, user_id, role) VALUES (:org_id, :user_id, :role) "
        "ON CONFLICT (org_id, user_id) DO UPDATE SET role=EXCLUDED.role"
    )

    with eng.session("", is_admin=True) as s:
        if commit:
            for t in tenants:
                tid = str(t.get("tenant_id") or "")
                if not tid:
                    continue
                is_admin = bool(t.get("is_admin"))
                role = str(t.get("role") or ("admin" if is_admin else "manager"))
                name = str(t.get("name") or "")
                email = str(t.get("email") or "")
                s.execute(text(org_sql), {
                    "id": tid, "name": name, "is_admin": is_admin,
                    "data": json.dumps(t, ensure_ascii=False),
                })
                up_orgs += 1
                s.execute(text(user_sql), {
                    "id": tid, "org_id": tid, "email": email, "name": name, "role": role,
                    "is_admin": is_admin, "pass_hash": str(t.get("pass_hash") or ""),
                    "salt": str(t.get("salt") or ""), "data": json.dumps(t, ensure_ascii=False),
                })
                up_users += 1
                s.execute(text(mem_sql), {"org_id": tid, "user_id": tid, "role": role})
                up_mem += 1
            # session() commits on context exit
        n_orgs = s.execute(text("SELECT count(*) FROM orgs")).scalar() or 0
        n_users = s.execute(text("SELECT count(*) FROM users")).scalar() or 0
        n_mem = s.execute(text("SELECT count(*) FROM memberships")).scalar() or 0

    mode = "" if commit else " (DRY-RUN, no write — pass --commit)"
    print(f"BACKFILL identity: tenants={n_json} orgs={n_orgs} users={n_users} memberships={n_mem} "
          f"upserted_orgs={up_orgs} upserted_users={up_users} upserted_memberships={up_mem}{mode}")
    return 0


def backfill_ledger(commit: bool) -> int:
    """ledger is var/ledger/<stem>.json — one file PER TENANT (org_id == stem; records carry no
    tenant_id). Iterate every file, map rows with the LEDGER spec (org_id from stem promoted into the
    column; `data` jsonb stays the verbatim record), idempotent UPSERT by id. Same spec/SQL/mapper as
    the live multi_file mirror, so backfilled rows are byte-identical and shadow_diff reaches a true 0.
    UPSERT-only (no delete-by-omission — the live per-stem mirror owns pruning)."""
    import store
    from db import engine as eng
    from sqlalchemy import text

    eng.init(_ConfigShim)
    if not eng.available():
        print("BACKFILL ledger: ABORT — Postgres unavailable")
        return 2

    store._register_specs()
    sp = store._LEDGER_SPEC
    if sp is None:
        print("BACKFILL ledger: ABORT — ledger spec not registered")
        return 2

    upsert_sql = store.build_upsert_sql(sp)
    ledger_dir = VAR / "ledger"
    n_json = upserted = 0
    files = sorted(ledger_dir.glob("*.json")) if ledger_dir.exists() else []

    with eng.session("", is_admin=True) as s:
        for f in files:
            stem = f.stem
            try:
                objs = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(objs, list):
                continue
            rows = [r for r in sp.to_rows(objs, stem) if sp.key(r)]
            n_json += len(rows)
            if commit:
                for r in rows:
                    params = {k: v for k, v in r.items() if k != "data"}
                    params["data"] = json.dumps(r["data"], ensure_ascii=False)
                    s.execute(text(upsert_sql), params)
                    upserted += 1
        n_pg = s.execute(text("SELECT count(*) FROM ledger")).scalar() or 0

    mode = "" if commit else " (DRY-RUN, no write — pass --commit)"
    print(f"BACKFILL ledger: files={len(files)} json={n_json} pg={n_pg} upserted={upserted}{mode}")
    return 0


def _load_audit_events() -> list[dict]:
    """Read the append-only audit JSONL (var/audit_log.jsonl + its rotated .1 if present) into a list of
    parsed event dicts. Rotation: audit.py renames to <file>.1 at 50MB, so the .1 holds OLDER events —
    read it FIRST then the live file (chronological, though order is irrelevant for content-hash PKs).
    Skips blank/unparseable lines exactly like audit.tail (a corrupt line never aborts the backfill)."""
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


def backfill_events(commit: bool) -> int:
    """events == the audit ledger (append-only JSONL). NOT a snapshot store — append INSERT with
    ON CONFLICT (id) DO NOTHING (idempotent vs the live mirror + re-runs). PK = content-hash of the
    parsed event dict (store._content_id) derived IDENTICALLY by backfill, the live mirror hook
    (audit.record -> store.mirror_event), and shadow_diff -> JSON↔PG bijection, true shadow_diff 0.
    org_id == event tenant_id; full event in `data` jsonb; meta promoted. NO delete-by-omission (§3.6)."""
    import store
    from db import engine as eng
    from sqlalchemy import text

    eng.init(_ConfigShim)
    if not eng.available():
        print("BACKFILL events: ABORT — Postgres unavailable")
        return 2

    evs = _load_audit_events()
    rows = [r for r in store._events_rows(evs) if r.get("id")]
    n_json = len(rows)
    insert_sql = store.build_events_insert_sql()
    inserted = 0

    with eng.session("", is_admin=True) as s:
        if commit:
            for r in rows:
                params = {k: v for k, v in r.items() if k not in ("meta", "data")}
                params["meta"] = json.dumps(r.get("meta") or {}, ensure_ascii=False)
                params["data"] = json.dumps(r.get("data") or {}, ensure_ascii=False)
                res = s.execute(text(insert_sql), params)
                inserted += int(res.rowcount or 0)  # ON CONFLICT DO NOTHING => rowcount 0 for dups
            # session() commits on context exit
        n_pg = s.execute(text("SELECT count(*) FROM events")).scalar() or 0

    mode = "" if commit else " (DRY-RUN, no write — pass --commit)"
    print(f"BACKFILL events: json={n_json} pg={n_pg} inserted={inserted}{mode}")
    return 0


def _load_campaign_files() -> list[dict]:
    """Load every real campaign record from var/campaigns/<id>.json. The glob matches only *.json so the
    rotated/backup files (*.json.P2bak, *.json.winrestore.bak — different extensions) are excluded; we
    ALSO defensively skip any path containing '.bak' or 'winrestore'. Skips unparseable / non-dict files."""
    cdir = VAR / "campaigns"
    out: list[dict] = []
    if not cdir.exists():
        return out
    for p in sorted(cdir.glob("*.json")):
        nm = p.name.lower()
        if ".bak" in nm or "winrestore" in nm:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and d.get("id"):
            out.append(d)
    return out


def backfill_campaigns(commit: bool) -> int:
    """campaigns are per-id files var/campaigns/<id>.json (written via direct .write_text, bypassing
    _write) — NOT the snapshot seam. Iterate the dir, per-id UPSERT by id using the SAME mapper + UPSERT
    SQL as the live mirror hooks (store._campaign_row + build_campaign_upsert_sql) so backfilled rows are
    byte-identical and shadow_diff reaches a true 0. UPSERT-only (the live delete hook owns removals)."""
    import store
    from db import engine as eng
    from sqlalchemy import text

    eng.init(_ConfigShim)
    if not eng.available():
        print("BACKFILL campaigns: ABORT — Postgres unavailable")
        return 2

    recs = _load_campaign_files()
    rows = [store._campaign_row(r) for r in recs if r.get("id")]
    n_json = len(rows)
    upsert_sql = store.build_campaign_upsert_sql()
    upserted = 0

    with eng.session("", is_admin=True) as s:
        if commit:
            for r in rows:
                params = {k: v for k, v in r.items() if k not in ("fields", "data")}
                params["fields"] = json.dumps(r.get("fields") or {}, ensure_ascii=False)
                params["data"] = json.dumps(r.get("data") or {}, ensure_ascii=False)
                s.execute(text(upsert_sql), params)
                upserted += 1
            # session() commits on context exit
        n_pg = s.execute(text("SELECT count(*) FROM campaigns")).scalar() or 0

    mode = "" if commit else " (DRY-RUN, no write — pass --commit)"
    print(f"BACKFILL campaigns: json={n_json} pg={n_pg} upserted={upserted}{mode}")
    return 0


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("-")]
    commit = "--commit" in argv[1:]
    if not args:
        print("usage: python backfill.py <entity> [--commit]   "
              "(entity 'identity' seeds orgs/users/memberships; 'ledger' = per-tenant files; "
              "'events' = audit_log.jsonl append-only; 'campaigns' = per-id files)")
        return 2
    if args[0] == "identity":
        return backfill_identity(commit)
    if args[0] == "ledger":
        return backfill_ledger(commit)
    if args[0] in ("events", "audit", "audit_log"):
        return backfill_events(commit)
    if args[0] == "campaigns":
        return backfill_campaigns(commit)
    return backfill(args[0], commit)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
