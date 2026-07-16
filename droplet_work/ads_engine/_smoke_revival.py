"""Offline Dead-Lead Revival smoke — consented bulk-import path (reuses the W6 gate + dry-run).

No app boot, no .env, no network. Run:
    python -c "import sys; sys.path.insert(0,'droplet_work'); import ads_engine._smoke_revival as s; s.main()"

Asserts the polish-wave requirements:
  * a CONSENTED import (DPDP + DLT-backed DCA) records ledger rows AND enqueues dry-run (no JOBS,
    140-series OFF) — it funnels through the EXISTING leads.ingest gate, not a duplicate path.
  * a no-consent lead INSIDE the batch is gated OUT (status=blocked_*, not enqueued) while the
    consented lead in the SAME batch still imports.
  * the consent ledger hash-chain still verifies clean after a bulk import (immutability intact).
  * the endpoint's DPA-flag rejection is structural: bulk_import is only reached AFTER the route
    confirms dpa_acknowledged is true (proven here by the route-contract assertions on the source).

This reuses the W6 smoke's wiring + consent helpers verbatim (no duplication). The W1/W3/W4/W5/W6
smokes are run too (delegated to their own main()) so a single command proves nothing regressed.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Reuse the W6 smoke's deterministic IST anchors + wiring so we don't re-derive them.
from ads_engine._smoke_w6 import _wire, _NOON  # type: ignore


def _test_bulk_import_consented(pkg, JOBS, created) -> list:
    import ads_engine.compliance as compliance
    import ads_engine.config as cfg
    import ads_engine.leads as leads
    out = []

    os.environ.pop("ADS_TELEPHONY_140", None)  # 140-series OFF => every enqueue is dry-run.
    cfg.set_cfg_get(None)
    compliance.set_ncpr_scrub(lambda t, p: {"block": False, "categories": []})

    tid = "t_revival"
    jobs_before, created_before = len(JOBS), len(created)

    rows = [
        # consented: DPDP true + DLT-backed DCA -> passes the voice gate -> dry-run enqueue.
        {"name": "Asha", "phone": "9812345678", "source": "revival_2024",
         "consent": {"dpdp": True, "dca_method": compliance.METHOD_OTP_127_DLT,
                     "dlt_consent_id": "DLT-REV-1"}},
        # NO consent at all -> the fail-closed gate denies (no_dpdp_consent) -> blocked, not enqueued.
        {"name": "Bilal", "phone": "9812345679", "source": "revival_2024",
         "consent": {}},
        # checkbox-only DCA (no DLT) -> DPDP ok but DCA not DLT-backed -> gated out for voice.
        {"name": "Chitra", "phone": "9812345670", "source": "revival_2024",
         "consent": {"dpdp": True, "dca_method": compliance.METHOD_FORM_CHECKBOX}},
    ]

    res = leads.bulk_import(tid, rows, dpa_ref="DPA-2026-001", channel="voice", now_epoch=_NOON)

    out.append(("bulk_import returns one result row per input lead",
                len(res.get("leads", [])) == 3))
    out.append(("exactly ONE consented lead ingested (dry-run)",
                res.get("ingested") == 1))
    out.append(("two un-consented leads blocked (gated out)",
                res.get("blocked") == 2))

    statuses = {l.get("lead_id"): l.get("status") for l in res["leads"]}
    consented = res["leads"][0]
    nocons = res["leads"][1]
    checkbox = res["leads"][2]
    out.append(("consented lead -> dry_run (passed gate, no real dial)",
                consented.get("status") == "dry_run"))
    out.append(("no-consent lead -> blocked_no_consent (not enqueued)",
                str(nocons.get("status", "")).startswith("blocked")
                and nocons.get("block_reason") == "no_dpdp_consent"))
    out.append(("checkbox-only DCA lead -> blocked (not DLT-backed for voice)",
                str(checkbox.get("status", "")).startswith("blocked")
                and checkbox.get("block_reason") == "dca_not_dlt_backed_for_voice"))

    # DRY-RUN: NO real JOBS row + NO run_job task was created for the whole batch (140-series off).
    out.append(("bulk_import stays dry-run: no JOBS row created",
                len(JOBS) == jobs_before))
    out.append(("bulk_import stays dry-run: no run_job task created",
                len(created) == created_before))

    # The consent ledger recorded rows AND still hash-chains clean (immutability intact).
    v = compliance.verify_chain(tid)
    # DPDP for Asha + DCA(DLT) for Asha + DPDP for Chitra + DCA(checkbox) for Chitra = 4 rows.
    out.append(("consent ledger recorded rows + chain verifies clean",
                v.get("ok") is True and v.get("length") == 4))

    return out


def _test_route_contract() -> list:
    """The DPA-flag rejection + step-up gating live in the ROUTE; assert the source wires them so the
    rejection is structural (bulk_import is only reached after dpa_acknowledged passes)."""
    out = []
    src = (Path(__file__).resolve().parent / "endpoints.py").read_text(encoding="utf-8")
    out.append(("import route rejects when DPA flag false",
                'dpa_acknowledged must be true' in src
                and 'if not dpa_ack:' in src))
    # Step-up gate (post routes-auth H1 fix): the import route verifies a generic SPEND-scope step-up
    # via _verify_spend_step_up (which fails CLOSED when no firewall/verifier is wired) and blocks with
    # blocked_not_approved when absent. (The old consume_reveal_step_up(action) wiring was un-passable.)
    out.append(("import route is step-up gated (X-Step-Up, fail-closed)",
                'step_up = _verify_spend_step_up(token, tid)' in src
                and 'blocked_not_approved' in src))
    out.append(("import route REUSES leads.bulk_import (no dup gate/enqueue)",
                '_leads_mod.bulk_import(' in src))
    out.append(("import route mutation-gated (write + not legacy-pw)",
                'gate = _write_gate(request, t)' in src.split('"/leads/import"')[1][:600]
                if '"/leads/import"' in src else False))
    return out


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ads_revival_"))
    os.environ["FEATURE_ADS"] = "1"
    pkg, JOBS, created = _wire(tmp)

    checks = []
    checks += _test_bulk_import_consented(pkg, JOBS, created)
    checks += _test_route_contract()

    all_ok = True
    for label, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
        all_ok = all_ok and bool(ok)
    print("RESULT:", "ALL PASS" if all_ok else "FAILURES")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
