#!/usr/bin/env python3
"""seed_kb_from_campaigns.py — populate the KB corpus from campaign brains (var/campaigns/*.json).

READ-ONLY against the campaigns (we only read their JSON). WRITES into the kb_* corpus via
kb.ingest (idempotent by sha256 checksum -> safe to re-run). Tenant-scoped + campaign-tagged +
channel_scope="voice" so the voice agents retrieve only their own campaign's chunks.

Per campaign we emit several SMALL, semantically-coherent docs (each its own kb_document) so that
FTS retrieval (the keyless leg that's live today) surfaces the RIGHT slice per turn:
  - product   : product summary + location + landmark
  - pricing   : price/offer line
  - product   : USPs + talking points + amenities (one bullet per line)
  - objection : EACH objection as a "Q -> rebuttal" chunk (+ negotiation ladder if present)
  - faq       : qualifying questions, credibility, EOI/urgency, value-prop, past projects, goal

Run (on the box, capsy venv which has sqlalchemy):
    cd /opt/famit-agent && /opt/capsy-agent/.venv/bin/python seed_kb_from_campaigns.py [--only c17e55e9f3 ...]

Exit 0 on success; prints a per-campaign + total chunk tally.
"""
from __future__ import annotations

import glob
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv("/opt/famit-agent/.env")
load_dotenv(".env")

CAMP_DIR = os.getenv("CAMP_DIR", os.path.join(os.getenv("FAMIT_VAR", "/opt/famit-agent/var"), "campaigns"))


def _as_lines(v) -> list[str]:
    """Coerce a field that may be a list[str] / list[dict] / str into a list of non-empty strings."""
    out: list[str] = []
    if isinstance(v, str):
        s = v.strip()
        if s:
            out.append(s)
    elif isinstance(v, (list, tuple)):
        for x in v:
            if isinstance(x, str) and x.strip():
                out.append(x.strip())
            elif isinstance(x, dict):
                q = (x.get("q") or x.get("question") or "").strip()
                a = (x.get("a") or x.get("answer") or "").strip()
                if q or a:
                    out.append((f"Q: {q}\nA: {a}").strip())
    return out


def _docs_for_campaign(camp: dict) -> list[dict]:
    """Build the list of {title, content, doc_type} docs to ingest for one campaign."""
    f = camp.get("fields", {}) or {}
    cname = (camp.get("name") or f.get("product_name") or camp.get("product") or "").strip()
    company = (f.get("company_name") or camp.get("company") or "").strip()
    hdr = (cname + (f" ({company})" if company else "")).strip() or "Campaign"
    docs: list[dict] = []

    # --- product overview (summary + location) ---
    overview_bits: list[str] = []
    if f.get("product_summary"):
        overview_bits.append(str(f["product_summary"]).strip())
    loc = (f.get("location") or "").strip()
    landmark = (f.get("landmark") or "").strip()
    if loc:
        overview_bits.append(f"Location: {loc}" + (f" (landmark: {landmark})" if landmark else ""))
    if overview_bits:
        docs.append({
            "title": f"{hdr} — Product overview & location",
            "doc_type": "product",
            "content": f"## {hdr} — Overview & Location\n\n" + "\n\n".join(overview_bits),
        })

    # --- pricing ---
    price = (f.get("price_offer") or "").strip()
    if price:
        docs.append({
            "title": f"{hdr} — Pricing",
            "doc_type": "pricing",
            "content": f"## {hdr} — Price / Offer\n\n{price}",
        })

    # --- USPs + talking points + amenities (product) ---
    sell_lines: list[str] = []
    for usp in _as_lines(f.get("usps")):
        sell_lines.append(f"- USP: {usp}")
    for tp in _as_lines(f.get("talking_points")):
        sell_lines.append(f"- Talking point: {tp}")
    for am in _as_lines(f.get("amenities")):
        sell_lines.append(f"- Amenity: {am}")
    if sell_lines:
        docs.append({
            "title": f"{hdr} — USPs, talking points & amenities",
            "doc_type": "product",
            "content": f"## {hdr} — Key selling points\n\n" + "\n".join(sell_lines),
        })

    # --- objections: ONE chunk-friendly doc, each rebuttal its own section ---
    obj_lines: list[str] = []
    objs = f.get("objections") or []
    if isinstance(objs, list):
        for o in objs:
            if isinstance(o, dict):
                q = (o.get("q") or o.get("question") or "").strip()
                a = (o.get("a") or o.get("answer") or "").strip()
                if q or a:
                    obj_lines.append(f"### Objection: {q}\nRebuttal: {a}")
            elif isinstance(o, str) and o.strip():
                obj_lines.append(f"### Objection\n{o.strip()}")
    for nl in _as_lines(f.get("negotiation_ladder")):
        obj_lines.append(f"### Negotiation step\n{nl}")
    if obj_lines:
        docs.append({
            "title": f"{hdr} — Objection handling & negotiation",
            "doc_type": "objection",
            "content": f"## {hdr} — Objection rebuttals\n\n" + "\n\n".join(obj_lines),
        })

    # --- FAQ-ish: qualifying questions, credibility, urgency, value-prop, projects, goal ---
    faq_lines: list[str] = []
    for qq in _as_lines(f.get("qualifying_questions")):
        faq_lines.append(f"- Qualifying question: {qq}")
    for key, label in (
        ("credibility", "Credibility / trust"),
        ("eoi_urgency", "Urgency / EOI stage"),
        ("value_prop", "Value proposition"),
        ("past_projects", "Past projects"),
        ("goal", "Call goal"),
    ):
        val = (f.get(key) or "").strip() if isinstance(f.get(key), str) else ""
        if val:
            faq_lines.append(f"### {label}\n{val}")
    for ao in _as_lines(f.get("appointment_options")):
        faq_lines.append(f"- Appointment option: {ao}")
    if faq_lines:
        docs.append({
            "title": f"{hdr} — Qualifying, credibility & next steps",
            "doc_type": "faq",
            "content": f"## {hdr} — Qualifying & trust\n\n" + "\n".join(faq_lines),
        })

    return docs


def main(argv: list[str]) -> int:
    only = set()
    if "--only" in argv:
        i = argv.index("--only")
        only = {a for a in argv[i + 1:] if not a.startswith("--")}

    from db import engine
    engine.init()
    if not engine.available():
        print("FATAL: Postgres not available (engine.init failed). PG_DSN set?", file=sys.stderr)
        return 2
    import kb
    if not kb.ensure_schema():
        print("FATAL: kb.ensure_schema() failed.", file=sys.stderr)
        return 2

    paths = sorted(glob.glob(os.path.join(CAMP_DIR, "*.json")))
    paths = [p for p in paths if not any(p.endswith(s) for s in (".bak",))]
    # only .json (drop .json.P2bak etc which glob *.json won't match anyway)

    grand_chunks = 0
    grand_docs = 0
    report: list[str] = []
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8") as fh:
                camp = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            print(f"skip {p}: {exc!r}", file=sys.stderr)
            continue
        if not isinstance(camp, dict):
            continue
        cid = str(camp.get("id") or os.path.splitext(os.path.basename(p))[0]).strip()
        tenant_id = str(camp.get("tenant_id") or "admin").strip() or "admin"
        if only and cid not in only:
            continue
        docs = _docs_for_campaign(camp)
        c_chunks = 0
        c_docs = 0
        for d in docs:
            res = kb.ingest(
                tenant_id, d["content"],
                title=d["title"], kind="campaign_seed", doc_type=d["doc_type"],
                scope="business", channel_scope="voice", scope_campaign_id=cid,
            )
            if res.get("ok"):
                c_docs += 1
                c_chunks += int(res.get("chunks", 0) or 0)
            else:
                report.append(f"    ! {cid} doc '{d['title'][:40]}' -> {res.get('reason')}")
        grand_chunks += c_chunks
        grand_docs += c_docs
        report.append(f"  {cid} (tenant={tenant_id}, '{camp.get('name','')[:30]}'): "
                      f"{c_docs} docs / {c_chunks} chunks")

    print("=== KB SEED REPORT ===")
    print("\n".join(report))
    print(f"=== TOTAL: {grand_docs} docs / {grand_chunks} chunks ingested (idempotent) ===")

    # final authoritative count from the DB
    from sqlalchemy import text
    with engine.session(tenant_id="", is_admin=True) as s:
        total = s.execute(text("SELECT count(*) FROM kb_chunks")).scalar()
        embedded = s.execute(text("SELECT count(*) FROM kb_chunks WHERE embedding IS NOT NULL")).scalar()
        tenants = s.execute(text("SELECT count(DISTINCT tenant_id) FROM kb_chunks")).scalar()
    print(f"=== DB NOW: kb_chunks={total} embedded={embedded} distinct_tenants={tenants} ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
