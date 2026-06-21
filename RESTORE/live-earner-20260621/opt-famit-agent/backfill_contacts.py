"""backfill_contacts.py — aggregate Contacts from the existing leads store (dual-safe, idempotent).

A Contact aggregates a lead: for every lead row (PG, dual-mirrored) we upsert one contact keyed by
canonical phone, then project stage/score/hot/last_outcome from the lead truth and rebuild its timeline
from calls+transcripts+wa+suppression. NEVER writes leads (read-only on the authoritative store) — it
only populates the PG-native `contacts`/`contact_timeline`/`contact_identity` projection.

Idempotent: re-running upserts the same deterministic contact_id + deterministic timeline ids -> 0 new
rows the second time. Admin GUC (spans tenants). Inert wrt the live service (nothing imports this).

Run ON the box:
  cd /opt/famit-agent && set -a && . ./.env && set +a && \
    /opt/capsy-agent/.venv/bin/python backfill_contacts.py [--commit] [--org <id>]

Default is a DRY-RUN report (counts the leads it WOULD aggregate); --commit performs the upserts.
"""
import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import engine  # noqa: E402
import crm  # noqa: E402
from sqlalchemy import text  # noqa: E402


def _leads(org_filter: str = "") -> list[dict]:
    """All lead rows from PG (admin GUC). Returns [{org_id, phone, data}]."""
    with engine.session(tenant_id="", is_admin=True) as s:
        if org_filter:
            rows = s.execute(text("SELECT org_id, phone, data FROM leads WHERE org_id=:o"),
                             {"o": org_filter}).fetchall()
        else:
            rows = s.execute(text("SELECT org_id, phone, data FROM leads")).fetchall()
    out = []
    for org_id, phone, data in rows:
        d = (data if isinstance(data, dict) else json.loads(data)) if data else {}
        out.append({"org_id": org_id, "phone": phone, "data": d})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="perform the upserts (default: dry-run)")
    ap.add_argument("--org", default="", help="restrict to one org_id")
    args = ap.parse_args()

    engine.init(None)
    if not crm.available():
        print("FATAL: PG unavailable"); sys.exit(3)
    crm.ensure_schema()

    leads = _leads(args.org)
    joinable = [l for l in leads if crm.canonical_phone(l["phone"])]
    distinct = {(l["org_id"], crm.canonical_phone(l["phone"])) for l in joinable}
    print(f"BACKFILL contacts: leads={len(leads)} joinable={len(joinable)} "
          f"distinct_contacts={len(distinct)} commit={args.commit}")

    if not args.commit:
        print("(dry-run — no writes. Re-run with --commit to aggregate.)")
        sys.exit(0)

    made = 0
    for l in joinable:
        org_id, phone, d = l["org_id"], l["phone"], l["data"]
        # carry the lead's display name into the contact (name niceties live on the contact).
        name = d.get("name", "") or ""
        crm.upsert_contact(org_id, phone, name=name, is_admin=True)
        crm.project_contact(org_id, phone, is_admin=True)
        made += 1
    # count the resulting contacts
    with engine.session(tenant_id="", is_admin=True) as s:
        ct = int(s.execute(text("SELECT count(*) FROM contacts")).scalar() or 0)
        tl = int(s.execute(text("SELECT count(*) FROM contact_timeline")).scalar() or 0)
    print(f"AGGREGATED leads_processed={made} -> contacts_rows={ct} timeline_rows={tl}")
    sys.exit(0)


if __name__ == "__main__":
    main()
