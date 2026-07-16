"""ads_engine.migrate_store — one-shot JSON-collections -> Postgres-RLS migration (V2 W2).

Copies the file-JSON ads store (VAR/ads/*.json + VAR/ads/<tid>/*.json + page_tenant_map.json)
into the FORCE-RLS Postgres tables of db/ddl_ads_engine.sql, via the SAME store.py accessors the
PG backend implements — so the migration writes go through RLS exactly like a live write would
(tenant_id stamped + WITH-CHECK enforced), and a row that can't be safely attributed is skipped,
never silently mis-tenanted.

Idempotent: collection rows upsert by (tenant_id, collection, row_id); page-map rows upsert by
page_id. RE-RUNNING is safe for collections + page map. Per-tenant LIST files (leads_ads,
decision_log, budget_ledger, …) are APPEND tables, so a naive re-run would DOUBLE them — this
script uses put_tenant_file (replace) for those, making a re-run idempotent too (the JSON file is
the source of truth; the PG list is replaced to match it).

This is a DEPLOY-WAVE tool. In W2 it is code + a self-test only; the actual cutover runs in the
deploy wave (apply DDL, run this with ADS_PG_DSN set + ADS_STORE_BACKEND temporarily forced).

Usage:
    python -c "import sys; sys.path.insert(0,'droplet_work'); \
               import ads_engine.migrate_store as m; m.main(var_dir='/opt/famit-agent/var')"
Requires ADS_PG_DSN (or db.engine on the box) + the DDL applied. Reads the JSON directly (NOT via
the store json backend) and writes via the store PG backend.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from . import store
from .store import COLLECTION_FILES, PER_TENANT_FILES, _PAGE_TENANT_MAP_FILE


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _force_pg_backend() -> Any:
    """Resolve the PG backend (raises if ADS_STORE_BACKEND!=postgres or PG unreachable)."""
    prev = os.environ.get("ADS_STORE_BACKEND")
    os.environ["ADS_STORE_BACKEND"] = "postgres"
    store._reset_backend()
    backend = store._pg()
    if backend is None:
        raise RuntimeError("migrate_store: PG backend did not resolve (set ADS_PG_DSN / apply DDL)")
    return prev


def migrate(var_dir: str) -> dict:
    """Migrate VAR/ads/* into Postgres via the store PG accessors. Returns a counts report."""
    _force_pg_backend()
    ads_dir = Path(var_dir) / "ads"
    report = {"collections": 0, "collection_rows": 0, "tenant_files": 0,
              "tenant_rows": 0, "pages": 0, "skipped": 0}

    # 1) COLLECTION files: VAR/ads/<name>.json == { "<tid>": { "<row_id>": {...} } }
    for name in sorted(COLLECTION_FILES):
        data = _read_json(ads_dir / f"{name}.json", {})
        if not isinstance(data, dict):
            continue
        report["collections"] += 1
        for tid, rows in data.items():
            if not isinstance(rows, dict):
                report["skipped"] += 1
                continue
            for row_id, row in rows.items():
                if not isinstance(row, dict):
                    report["skipped"] += 1
                    continue
                store.put_row(str(tid), name, str(row_id), row)
                report["collection_rows"] += 1

    # 2) PER-TENANT LIST files: VAR/ads/<tid>/<name>.json == [ {...}, ... ]
    for tdir in sorted(p for p in ads_dir.iterdir() if p.is_dir()) if ads_dir.exists() else []:
        tid = tdir.name
        for name in sorted(PER_TENANT_FILES):
            f = tdir / f"{name}.json"
            if not f.exists():
                continue
            rows = _read_json(f, [])
            if not isinstance(rows, list):
                report["skipped"] += 1
                continue
            store.put_tenant_file(tid, name, rows)   # replace => idempotent re-run
            report["tenant_files"] += 1
            report["tenant_rows"] += len(rows)

    # 3) GLOBAL page_id -> tenant map.
    pmap = _read_json(ads_dir / f"{_PAGE_TENANT_MAP_FILE}.json", {})
    if isinstance(pmap, dict):
        for pid, prow in pmap.items():
            if not isinstance(prow, dict):
                report["skipped"] += 1
                continue
            owner = prow.get("tenant_id")
            if not owner:
                report["skipped"] += 1
                continue
            try:
                store.link_page_to_tenant(str(owner), str(pid), actor=str(prow.get("actor", "")),
                                          evidence=prow.get("evidence"))
                report["pages"] += 1
            except store.PageOwnershipConflict:
                report["skipped"] += 1

    return report


def main(var_dir: str = "") -> int:
    vd = var_dir or os.getenv("FAMIT_VAR", "/opt/famit-agent/var")
    rep = migrate(vd)
    print("ads_engine.migrate_store: migrated", rep)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
