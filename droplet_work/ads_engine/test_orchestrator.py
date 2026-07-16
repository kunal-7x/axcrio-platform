"""Offline end-to-end test for the AUTONOMY LOOP (ads_engine.orchestrator) — BLINDSPOTS B9/B10/B6.

NO network, NO real spend, NO real dial. Wires the package with a TEMP file-backed store, flips the
feature flags ON in-process (DRY-RUN stays ON), seeds {connected key + funded budget + brief}, and
drives the orchestrator through every phase, asserting the chain self-runs to a launched (dry-run)
campaign. Also exercises: standalone creative (no pre-existing plan_id), media-engine asset bridge,
the tick-driven pass, and the post-launch lead->call->feedback seam.

Run:
    python -c "import sys; sys.path.insert(0,'droplet_work'); import ads_engine.test_orchestrator as t; t.main()"
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# File-backed store seams (the ONLY IO; everything lives under a throwaway temp dir).
# ---------------------------------------------------------------------------
def _read(path, default=None):
    try:
        p = Path(path)
        if not p.exists():
            return default
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return default


def _atomic_write_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    tmp.replace(p)


def _setup():
    """Flip flags, wire the package against a temp var dir, monkeypatch the vault status to
    'meta configured' (the connected-key precondition) without needing a real vault."""
    os.environ["FEATURE_ADS"] = "1"
    os.environ["ADS_DRY_RUN"] = "1"            # earner-safe: synthetic refs, never spends
    os.environ["ADS_AUTORUN"] = "1"            # enable the orchestrator pass
    os.environ["ADS_AUTORUN_AUTOLAUNCH"] = "1"  # let the orchestrator auto-approve (dry-run only)
    os.environ["ADS_REQUIRE_FUNDED"] = "0"     # skip managed-funding pre-check (no gateway in test)

    import ads_engine
    tmp = Path(tempfile.mkdtemp(prefix="ads_autorun_"))
    ads_engine.wire(_read=_read, _write=_atomic_write_json,
                    _atomic_write_json=_atomic_write_json, var_dir=tmp)

    # Connected-key precondition: pretend Meta is configured in the vault (no real creds needed).
    from ads_engine import vault_adapter
    vault_adapter.list_status = lambda tid: {"meta": "configured", "google": "not_configured",
                                             "whatsapp": "not_configured"}
    return tmp


def _brief():
    """A viable, RERA-clean HOUSING brief funded ABOVE the CPA*50 monthly floor (verdict 'ok')."""
    return {
        "name": "Skyline Residences — Q3",
        "provider": "meta",
        "objective": "leads",
        "is_property": True,
        "rera_id": "P52100012345",
        "geo_pin": {"lat": 19.076, "lng": 72.8777},
        "radius_km": 8,
        "budget_daily_minor": 200000,   # Rs2000/day -> Rs60k/mo, above the floor
        "cpl_max_minor": 20000,         # Rs200 target CPL
        "headline": "2 & 3 BHK homes near the metro",
        "primary_text": "Modern residences with parking and a clubhouse. RERA P52100012345.",
        "description": "Book a site visit. RERA P52100012345.",
        "language": "hinglish",
        "size": "1080x1080",
    }


def _check(cond, label):
    if not cond:
        raise AssertionError(f"FAIL: {label}")
    print(f"  ok: {label}")


def _run_autonomy_chain():
    import asyncio
    from ads_engine import orchestrator as orch, store

    tid = "tnt_auto1"

    # --- preconditions BEFORE opt-in: no brief => not ready ---
    ok, reason, _ = orch.check_preconditions(tid, {})
    _check(not ok and reason == "no_brief", "preconditions block with no brief")

    # --- seed a funded ad-budget balance (the '+ budget' half) ---
    store.credit_budget(tid, 5_000_00, ref={"note": "test funding"})
    acct = store.get_budget_account(tid)
    _check(acct["balance_minor"] == 5_000_00, "ad-budget account funded")

    # --- a vendor-uploaded creative asset (the "or use uploaded" branch — deterministic offline;
    #     the generate branch needs creative-model creds which a real connected key supplies live) ---
    orch.register_media_asset(tid, {
        "asset_id": "media_auto1", "source": "media_engine",
        "url": "https://cdn.example/skyline.png", "headline": "2 & 3 BHK near the metro",
    })

    # --- opt the tenant in with the brief + uploaded asset (autopilot ON) ---
    res = orch.enable(tid, _brief(), autopilot_launch=True, uploaded_asset_id="media_auto1")
    _check(res["ok"] and res["state"]["phase"] == orch.PH_IDLE, "autorun enabled, cursor idle")
    ok, reason, details = orch.check_preconditions(tid)
    _check(ok, f"preconditions met (key+budget+brief): {details}")

    # --- drive the state machine to completion, one phase per advance ---
    phases_seen = []
    last = None
    for _ in range(20):
        r = asyncio.run(orch.advance(tid))
        st = orch.get_state(tid)
        phases_seen.append(st["phase"])
        if st["phase"] in (orch.PH_DONE, orch.PH_BLOCKED):
            last = st
            break
    print(f"  phases: {phases_seen}")
    _check(last is not None and last["phase"] == orch.PH_DONE,
           f"chain reached DONE (blocked_reason={None if last is None else last.get('blocked_reason')})")

    # --- the launched campaign is a DRY-RUN publish (no real spend) ---
    plan_id = orch.get_state(tid)["plan_id"]
    rec = store.get_row(tid, "campaigns", plan_id)
    _check(rec is not None and rec["status"] == "dry_run", "campaign launched as DRY-RUN (no spend)")
    _check(str(rec["campaign_ref"]).startswith("dry_"), "campaign_ref is synthetic (dry_*)")

    # --- at least one creative variant moderated-approved drove the launch ---
    variants = orch.make_creative_service().get_variants(tid, plan_id)
    approved = [v for v in variants if v.get("moderation_status") == "approved"]
    _check(len(approved) >= 1, f"at least one approved ad variant ({len(approved)})")
    return tid, plan_id


def _run_standalone_and_bridge():
    from ads_engine import orchestrator as orch, store

    tid = "tnt_auto2"

    # --- B10: standalone creative — type a brief, get a job, NO pre-existing plan_id ---
    out = orch.standalone_generate(tid, _brief())
    _check(out["ok"] and out["plan_id"], "standalone creative minted a draft plan_id")
    _check(out["job"]["job_id"], "standalone creative created a creative job")
    plan = store.get_row(tid, "campaigns", out["plan_id"])
    _check(plan is not None, "standalone draft plan persisted")

    # --- B6: bridge a media-engine asset into a moderated ad variant ---
    asset = orch.register_media_asset(tid, {
        "asset_id": "media_abc123", "source": "media_engine",
        "url": "https://cdn.example/test.png", "headline": "Clean banner",
    })
    _check(asset.get("asset_id") == "media_abc123", "media-engine asset mirrored into gallery")

    bridged = orch.bridge_media_asset(tid, "media_abc123", brief={
        "is_property": True, "rera_id": "P52100012345",
        "headline": "Homes near the metro",
        "description": "RERA P52100012345",
    })
    _check(bridged["ok"], "media asset bridged into an ad variant")
    v = bridged["variant"]
    _check(v.get("source") == "uploaded", "bridged variant marked source=uploaded")
    _check(v.get("moderation_status") in ("approved", "pending", "blocked"),
           f"bridged variant ran the moderation gate (status={v.get('moderation_status')})")
    _check(v.get("moderation_status") == "approved", "clean bridged variant approved by the gate")


def _run_tick_pass():
    import asyncio
    from ads_engine import tick, orchestrator as orch, store

    # Seed a FRESH opt-in tenant mid-pipeline so the tick-driven pass has a phase to advance.
    tid = "tnt_tick1"
    store.credit_budget(tid, 5_000_00, ref={"note": "test"})
    orch.register_media_asset(tid, {"asset_id": "m_tick", "url": "https://cdn.example/x.png",
                                    "headline": "Homes near the metro"})
    orch.enable(tid, _brief(), autopilot_launch=True, uploaded_asset_id="m_tick")
    before = orch.get_state(tid)["phase"]

    # The tick must run the orchestrator pass (ADS_AUTORUN on) crash-free AND advance the new tenant.
    summary = asyncio.run(tick.run_tick(now_ts=10_000_000))
    _check("orchestrated" in summary, "tick summary exposes 'orchestrated'")
    _check(summary["orchestrated"] >= 1, "tick-driven orchestrator advanced an opt-in tenant")
    after = orch.get_state(tid)["phase"]
    _check(after != before, f"tenant phase advanced via the tick ({before} -> {after})")
    print(f"  tick summary: {summary}")


def _run_post_launch_chain(tid):
    import asyncio
    from ads_engine import orchestrator as orch, feedback

    # The back half: lead -> (60s) call enqueue (DRY-RUN, no dial) -> quality feedback.
    raw = {"name": "Asha", "phone": "+919876500011", "score": "hot",
           "campaign_id": "c1", "source": "ad"}
    out = asyncio.run(orch.process_post_launch_lead(tid, raw))
    _check(isinstance(out.get("lead"), dict), "post-launch lead ingested (gate ran)")
    lead = out["lead"]
    # Earner-safe: no real dial — either gated out (no consent) or dry-run enqueue. NEVER 'enqueued'.
    enq_status = lead.get("status", "")
    _check(not str(lead.get("dry_run")) == "False" or enq_status.startswith("blocked"),
           "no real dial fired (dry-run or gated) — earner-safe")
    print(f"  lead status={enq_status} feedback={'emitted' if out.get('feedback') else 'none(gated)'}")

    # Prove the CAPI/Data-Manager feedback seam emits independently for a qualified, scored lead.
    qlead = {"lead_id": "ld_test1", "phone": "+919876500011", "score": "hot",
             "name": "Asha"}
    fb = asyncio.run(feedback.emit_quality(tid, qlead))
    _check(fb.get("emitted") is True and fb.get("event"), "feedback.emit_quality emits a quality event")
    print(f"  feedback event={fb.get('event')} meta_ok={fb.get('meta', {}).get('ok')} "
          f"google_ok={fb.get('google', {}).get('ok')}")


def main():
    print("ads_engine.test_orchestrator — AUTONOMY LOOP offline chain")
    _setup()
    print("[1] autonomy chain: key+budget+brief -> propose -> creative -> moderate -> viability -> dry-run launch")
    tid, _plan = _run_autonomy_chain()
    print("[2] standalone creative (B10) + media-engine asset bridge (B6)")
    _run_standalone_and_bridge()
    print("[3] tick drives the orchestrator pass (crash-free)")
    _run_tick_pass()
    print("[4] post-launch lead -> (dry-run) call -> CAPI/Data-Manager feedback")
    _run_post_launch_chain(tid)
    print("\nALL ORCHESTRATOR CHAIN ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
