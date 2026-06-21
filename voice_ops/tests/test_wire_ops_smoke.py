"""W-WIRE-OPS smoke: prove the SEAM contracts the wired caller.py depends on.

Runs against the real modules (voice_kernel/, voice_ops/) exactly as caller.py
calls them — NOT against caller.py itself (which pulls livekit/fastapi/.env). It
mirrors each wired call site 1:1 so a contract drift would fail here.
"""
import ast
import asyncio
import os
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]   # repo root (caps/)
sys.path.insert(0, str(ROOT))

# The wired caller.py lives in the local build dir during the build wave; the
# STATIC seam-presence check runs only when it is present (portable in CI).
WIRED = ROOT / ".wireops_work" / "caller.py.WIRED"


# ── 1. STATIC: the wired source has every new function + route + flag ─────────────
def test_wired_source_has_seams():
    if not WIRED.exists():
        import pytest
        pytest.skip("wired caller.py.WIRED not present (build-dir only)")
    src = WIRED.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    # new functions
    for fn in ("_ev", "_get_event_bus", "_w9_transcript_provider", "_w9_summary_provider",
               "_w7_lifecycle_after_call", "_w14_filters",
               "report_query", "report_funnel", "report_timeline", "report_agents",
               "report_sources", "report_campaigns", "report_followups", "report_hot_leads",
               "report_metric", "ai_manager_report"):
        assert fn in names, f"missing wired function: {fn}"
    # flags present (real env-var names the configs read)
    for flag in ("EVENTBUS_ENABLED", "RECORDING_FINALIZE_ENABLED", "REPORTING_ENABLED",
                 "LEAD_LIFECYCLE_ENABLED", "CALLBACK_CADENCE_ENABLED"):
        assert flag in src, f"flag not referenced: {flag}"
    # routes
    for route in ('@app.get("/report")', '@app.get("/report/funnel")',
                  '@app.get("/report/hot-leads")', '@app.post("/ai-manager/report")'):
        assert route in src, f"route not mounted: {route}"
    # the legacy callback path is GATED, not deleted (reversible by flag)
    assert "_cb_owned" in src and "fire_due" in src
    print("STATIC OK: all seams present")


# ── 2. W8: the exact emits caller.py fires actually land on the bus ───────────────
def test_w8_emits_fire():
    from voice_kernel.events import InMemoryEventBus, EventBusConfig
    import voice_kernel.events as vke
    cfg = EventBusConfig(enabled=True)
    bus = InMemoryEventBus(cfg)

    async def _ev(ev):  # mirror caller.py::_ev
        try:
            await bus.emit(ev)
        except Exception:
            pass

    async def run():
        tid, cid = "tenantA", "call123"
        # the 7 wired call sites, with the SAME kwargs caller.py passes:
        await _ev(vke.call_started(cid, tid, campaign_id="camp1"))
        await _ev(vke.lead_classified(cid, tid, "dead"))
        await _ev(vke.call_ended(cid, tid, duration_s=42))
        await _ev(vke.callback_scheduled(cid, tid, preferred_ts="2026-06-19T17:00:00Z"))
        await _ev(vke.whatsapp_sent(cid, tid, template="no_answer"))
        await _ev(vke.summary_ready(cid, tid, lifecycle="interested", conversion_prob=0.8,
                                    summary="wants a demo", next_action="send brochure",
                                    lead_name="Riya", campaign_id="camp1"))
        await _ev(vke.lead_classified(cid, tid, "hot", conversion_prob=0.8))
        await _ev(vke.handoff_requested(cid, tid, reason="hot_lead"))
        events = bus.all_events(tid)
        return events
    events = asyncio.run(run())
    names = [e.name.value if hasattr(e.name, "value") else str(e.name) for e in events]
    assert len(events) == 8, f"expected 8 emits, got {len(events)}: {names}"
    print(f"W8 OK: 8 emits landed -> {names}")


# ── 3. W14: reporting returns date-range data fed by the SAME W8 events ───────────
def test_w14_reporting_roundtrip():
    from voice_kernel.events import InMemoryEventBus, EventBusConfig
    import voice_kernel.events as vke
    from voice_ops.reporting import (ReportingStore, ReportingConfig, ReportingService,
                                     build_consumer_handler)
    cfg = EventBusConfig(enabled=True)
    bus = InMemoryEventBus(cfg)
    store = ReportingStore()
    svc = ReportingService(store, ReportingConfig(enabled=True))
    handler = build_consumer_handler(store)
    tid = "tenantR"

    async def run():
        # emit a call's lifecycle, then drive the reporting reducer with those events
        evs = [
            vke.call_started("c1", tid, campaign_id="camp1"),
            vke.call_ended("c1", tid, duration_s=55),
            vke.summary_ready("c1", tid, lifecycle="interested", conversion_prob=0.9,
                              summary="hot lead", lead_name="Asha", campaign_id="camp1"),
            vke.lead_classified("c1", tid, "hot", conversion_prob=0.9),
        ]
        for e in evs:
            await bus.emit(e)
        for e in bus.all_events(tid):
            await handler(e)
        rep = svc.report(tid, "today")
        hot = svc.hot_leads(tid, "today")
        return rep, hot
    rep, hot = asyncio.run(run())
    assert "range" in rep and rep["range"].get("preset") == "today", rep.get("range")
    totals = rep.get("totals", {})
    assert totals.get("calls", 0) >= 1, f"expected >=1 call in report, got {totals}"
    # tenant isolation: a DIFFERENT tenant sees nothing
    empty = svc.report("tenantZ", "today")
    assert empty.get("totals", {}).get("calls", 0) == 0, "tenant isolation breach"
    print(f"W14 OK: report.totals.calls={totals.get('calls')} hot={len(hot.get('leads', hot) if isinstance(hot, dict) else hot)} ; isolation holds")


# ── 4. W7: post-call lifecycle classify (the FSM caller.py uses) ──────────────────
def test_w7_lifecycle_classifies():
    from voice_kernel.memory.lifecycle import classify_lifecycle
    from voice_kernel.packet import Lifecycle
    # booked -> HOT
    assert classify_lifecycle(prior=Lifecycle.NEW, booked=True) == Lifecycle.HOT
    # engaged + commitment -> WARM
    assert classify_lifecycle(prior=Lifecycle.NEW, engaged=True, had_commitment=True) == Lifecycle.WARM
    # opt-out -> DEAD, and DEAD is sticky without a fresh booking
    assert classify_lifecycle(prior=Lifecycle.NEW, dead=True) == Lifecycle.DEAD
    assert classify_lifecycle(prior=Lifecycle.DEAD, engaged=True) == Lifecycle.DEAD
    # engaged + objection, no commitment -> COLD
    assert classify_lifecycle(prior=Lifecycle.NEW, engaged=True, had_objection=True) == Lifecycle.COLD
    print("W7 OK: lifecycle FSM hot/warm/cold/dead correct + DEAD sticky")


# ── 5. W10: callback cadence cannot runaway (the founder's #1 fear) ───────────────
def test_w10_cannot_runaway():
    from voice_ops.callback import (CallbackConfig, InMemoryCallbackStore,
                                    enqueue_smart, fire_due)
    cfg = CallbackConfig(enabled=True, dnd_start_hour=0, dnd_end_hour=0)  # DND off for the test
    store = InMemoryCallbackStore()
    tid, cid, phone = "tenantC", "camp1", "+919999000011"

    async def run():
        rec = {"id": "c1", "phone": phone, "name": "Test"}
        # A) a PICKUP (answered) must schedule NOTHING and stick
        await enqueue_smart(tid, cid, rec, {"summary": "spoke"}, "answered", 0, {},
                            store=store, config=cfg, bus=None)
        due_after_pickup = await fire_due(store=store, config=cfg, bus=None)
        # B) 100 reconcile ticks on a no-answer must stay monotonic + EXPIRE, never infinite
        rec2 = {"id": "c2", "phone": "+919999000022", "name": "NoAns"}
        for _ in range(100):
            await enqueue_smart(tid, cid, rec2, {}, "no_answer", 0, {},
                                store=store, config=cfg, bus=None, from_reconcile=True)
        # drain due jobs repeatedly; attempts must cap at max_retries then EXPIRE
        fired = 0
        for _ in range(50):
            jobs = await fire_due(store=store, config=cfg, bus=None, now=None)
            for j in jobs:
                fired += 1
            if not jobs:
                pass
        return due_after_pickup, fired
    due_after_pickup, fired = asyncio.run(run())
    # a picked-up lead is never redialed
    assert all(j.phone != phone for j in due_after_pickup), "answered lead was queued for redial!"
    # the no-answer lead fired at most max_retries times across all ticks (anti-runaway)
    assert fired <= 5, f"runaway! fired {fired} dials (cap is max_retries)"
    print(f"W10 OK: pickup never redialed; no-answer capped (fired={fired}, no runaway)")


if __name__ == "__main__":
    test_wired_source_has_seams()
    test_w8_emits_fire()
    test_w14_reporting_roundtrip()
    test_w7_lifecycle_classifies()
    test_w10_cannot_runaway()
    print("\nALL W-WIRE-OPS SMOKE TESTS PASSED")
