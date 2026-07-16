"""Offline smoke for the V2-W3 PARITY OPTIMIZATION LOOP. No app boot, no .env, no network, no
connector, no caller. Deterministic. Wires the store seams to a tmp dir like _smoke_w3.

Run:
  python -c "import sys; sys.path.insert(0,'droplet_work'); import ads_engine._smoke_w3_loop as s; s.main()"

Asserts:
  * ad_events ingest is idempotent (same event_id dedups)
  * live signal feeds the bandit -> the genuinely-better variant wins (quality, not form-fill)
  * same-day CAPI drain stamps sent/pending (dormant connector => pending, never error)
  * creative fatigue: CTR decay AND >70% delivery-share both flag; rotation move is spend-decreasing
  * autonomous audience expansion: a better-converting non-seed segment is proposed (sign +1, gated)
  * learning-phase: below threshold within window => do-not-edit; threshold met => active
  * continuous daemon dry-run: signal -> reallocate-to-winners decisions logged with reversal payloads,
    nothing spends (dry_run), all gated through guardrails
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path


def _wire(tmp: Path):
    import ads_engine as pkg

    def _read(path, default):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return default

    def _awj(path, data):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data), encoding="utf-8")

    pkg.wire(_read=_read, _write=lambda p, d: _awj(p, d), _atomic_write_json=_awj, var_dir=tmp)


def _t_ad_events_idempotent():
    from ads_engine import ad_events as ev, store
    tid = "t_idem"
    e = {"type": ev.EV_LEAD_QUALIFIED, "lead_id": "L1", "ad_id": "V1", "campaign_id": "C1"}
    r1 = ev.ingest_event(tid, dict(e))
    r2 = ev.ingest_event(tid, dict(e))   # same -> same deterministic event_id -> dedup
    rows = store.get_ad_events(tid)
    ok = r1.get("ingested") and (not r2.get("ingested")) and r2.get("deduped") and len(rows) == 1
    return (f"ad_events idempotent (ingest1={r1.get('ingested')}, dedup2={r2.get('deduped')}, "
            f"rows={len(rows)})", ok)


def _t_signal_feeds_bandit():
    from ads_engine import ad_events as ev, store
    tid = "t_feed"; cid = "C_feed"
    # Variant A: real buyers (clicks + bookings). Variant B: traffic, no conversions.
    for i in range(40):
        ev.ingest_event(tid, {"type": ev.EV_PAGE_VIEW, "ad_id": "A", "campaign_id": cid, "lead_id": f"a{i}"})
        ev.ingest_event(tid, {"type": ev.EV_PAGE_VIEW, "ad_id": "B", "campaign_id": cid, "lead_id": f"b{i}"})
    for i in range(20):
        ev.ingest_event(tid, {"type": ev.EV_CLICK, "ad_id": "A", "campaign_id": cid, "lead_id": f"ac{i}"})
    for i in range(10):
        ev.ingest_event(tid, {"type": ev.EV_BOOKING, "ad_id": "A", "campaign_id": cid, "lead_id": f"abk{i}",
                              "value_minor": 100000})
    for i in range(2):
        ev.ingest_event(tid, {"type": ev.EV_CLICK, "ad_id": "B", "campaign_id": cid, "lead_id": f"bc{i}"})
    res = ev.feed_optimizer(tid, cid)
    st = store.get_bandit_state(tid, cid)
    arms = st.get("arms", {})
    mean_a = arms["A"]["alpha"] / (arms["A"]["alpha"] + arms["A"]["beta"])
    mean_b = arms["B"]["alpha"] / (arms["B"]["alpha"] + arms["B"]["beta"])
    ok = res.get("ok") and st.get("best_arm_id") == "A" and mean_a > mean_b
    return (f"live signal feeds bandit, quality wins (best={st.get('best_arm_id')}, "
            f"meanA={mean_a:.3f}>meanB={mean_b:.3f})", ok)


def _t_same_day_capi():
    from ads_engine import ad_events as ev, store
    tid = "t_capi"; cid = "C_capi"
    ev.ingest_event(tid, {"type": ev.EV_BOOKING, "ad_id": "A", "campaign_id": cid, "lead_id": "L_ok",
                          "phone": "+919999999999"})
    ev.ingest_event(tid, {"type": ev.EV_LEAD_QUALIFIED, "ad_id": "A", "campaign_id": cid, "lead_id": "L_pend"})

    async def emit_ok(t, lead, **kw):
        # The booking lead "sends"; the qualified lead "fails" (dormant dest) -> pending.
        if lead.get("crm_outcome") == "booked":
            return {"emitted": True, "meta": {"ok": True}, "google": {"ok": False}}
        return {"emitted": False, "reason": "not_configured", "meta": {"ok": False}, "google": {"ok": False}}

    out = asyncio.run(ev.same_day_capi_drain(tid, emit_fn=emit_ok, now_epoch=1000.0))
    rows = {r["lead_id"]: r for r in store.get_ad_events(tid)}
    sent = rows["L_ok"]
    pend = rows["L_pend"]
    ok = (out["sent"] == 1 and out["pending"] == 1
          and sent["capi_status"] == "sent" and sent["capi_sent_at"] == 1000.0
          and pend["capi_status"] == "pending" and pend["capi_sent_at"] is None)
    return (f"same-day CAPI stamps sent/pending (sent={out['sent']}, pending={out['pending']})", ok)


def _t_fatigue_decay_and_share():
    from ads_engine import fatigue as fat
    # CTR declining from 5% -> 2% over 4 daily buckets, plenty of delivery -> fatigued (ctr_decay).
    decay_series = [
        {"impressions": 5000, "clicks": 250},   # 5.0%
        {"impressions": 5000, "clicks": 200},   # 4.0%
        {"impressions": 5000, "clicks": 150},   # 3.0%
        {"impressions": 5000, "clicks": 100},   # 2.0% -> 60% below peak
    ]
    v_decay = fat.detect_fatigue(decay_series, delivery_share=0.4)
    # Healthy CTR but hoarding 85% of delivery -> concentration guard flags it.
    flat = [{"impressions": 4000, "clicks": 200}] * 3
    v_share = fat.detect_fatigue(flat, delivery_share=0.85)
    moves = fat.propose_rotation({"variants": {"V1": v_decay}}, campaign_id="C1")
    rot = moves[0] if moves else {}
    ok = (v_decay["fatigued"] and v_decay["reason"] == "ctr_decay"
          and v_share["fatigued"] and v_share["reason"] == "delivery_share_over_guard"
          and rot.get("move") == "rotate_creative" and rot.get("spend_delta_sign") == -1)
    return (f"fatigue: ctr-decay + >70% share flagged; rotate is spend-decreasing "
            f"(decay={v_decay['fatigued']}, share={v_share['fatigued']})", ok)


def _t_audience_expansion():
    from ads_engine import ad_events as ev, audience as aud
    events = []
    # Seed segment converts at ~1/10. A non-seed "investors" segment converts at ~5/10 -> expand.
    for i in range(10):
        events.append({"type": ev.EV_PAGE_VIEW, "campaign_id": "C1", "segment": "seed_seg"})
    events.append({"type": ev.EV_LEAD_QUALIFIED, "campaign_id": "C1", "segment": "seed_seg"})
    for i in range(10):
        events.append({"type": ev.EV_PAGE_VIEW, "campaign_id": "C1", "segment": "investors"})
    for i in range(5):
        events.append({"type": ev.EV_BOOKING, "campaign_id": "C1", "segment": "investors"})
    disc = aud.discover_segments(events, ["seed_seg"], campaign_id="C1")
    moves = aud.propose_expansion(disc, campaign_id="C1", budget_daily_minor=100000)
    cand = disc["candidates"][0] if disc["candidates"] else {}
    mv = moves[0] if moves else {}
    ok = (cand.get("segment") == "investors" and mv.get("move") == "audience_expand"
          and mv.get("spend_delta_sign") == +1
          and mv.get("expand_budget_minor") == int(100000 * aud.EXPANSION_BUDGET_SHARE))
    return (f"audience expansion proposes a better non-seed segment, gated + soft-ceiling "
            f"(cand={cand.get('segment')}, share_cap={mv.get('expand_budget_minor')})", ok)


def _t_learning_phase():
    from ads_engine import learning_phase as lp
    now = 1_000_000.0
    v_learn = lp.evaluate(10, provider="meta", started_ts=now - 2 * 86400, now_ts=now)   # 2d in, 10/50
    v_active = lp.evaluate(60, provider="meta", started_ts=now - 2 * 86400, now_ts=now)  # threshold met
    v_limited = lp.evaluate(10, provider="meta", started_ts=now - 30 * 86400, now_ts=now)  # past window
    ok = (v_learn["phase"] == lp.PHASE_LEARNING and v_learn["do_not_edit"]
          and v_active["phase"] == lp.PHASE_ACTIVE and not v_active["do_not_edit"]
          and v_limited["phase"] == lp.PHASE_LIMITED and v_limited["do_not_edit"])
    return (f"learning-phase awareness (learn={v_learn['phase']}, active={v_active['phase']}, "
            f"limited={v_limited['phase']})", ok)


def _t_continuous_reallocate_dry_run():
    from ads_engine import ad_events as ev, store, feedback, config
    tid = "t_cont"; cid = "C_cont"; acct = "acct_1"
    # Make sure CAPI is fully dormant (no connector) so the drain is a clean no-op.
    feedback.set_connector_resolver(lambda *a, **k: None)
    os.environ["FEATURE_ADS"] = "1"
    os.environ["ADS_DRY_RUN"] = "1"

    # A live, active campaign + an allocation with two channels: c1 strong curve, c2 weak; current split
    # is even, so reallocate-to-winners must MOVE budget toward c1 (=> reallocate decisions).
    store.put_row(tid, "campaigns", cid, {"plan_id": cid, "provider": "meta", "status": "active",
                                          "created_ts": 1_000_000})
    store.put_allocation(tid, acct, {
        "account_id": acct, "total_budget_minor": 1000000, "step_minor": 100000,
        "channels": {
            "meta:c1": {"history": [[100000, 2.0], [300000, 9.0], [500000, 11.0]], "theta": 0.6,
                        "alloc_minor": 200000},
            "meta:c2": {"history": [[100000, 1.0], [300000, 2.0], [500000, 2.5]], "theta": 0.5,
                        "alloc_minor": 200000},
        },
    })
    # Some live signal so the daemon has something to chew (platform meta reward refresh).
    for i in range(30):
        ev.ingest_event(tid, {"type": ev.EV_PAGE_VIEW, "ad_id": "V1", "campaign_id": cid, "lead_id": f"v{i}"})
    for i in range(8):
        ev.ingest_event(tid, {"type": ev.EV_BOOKING, "ad_id": "V1", "campaign_id": cid, "lead_id": f"bk{i}"})

    res = asyncio.run(__import__("ads_engine.continuous", fromlist=["optimize_pass"]).optimize_pass([tid]))
    decs = store.get_decisions(tid, limit=200)
    realloc = [d for d in decs if d.get("decision") == "reallocate"]
    has_reversal = any(isinstance(d.get("reversal_payload"), dict)
                       and d["reversal_payload"].get("move") == "reallocate" for d in realloc)
    all_dry = all(d.get("inputs", {}).get("dry_run") is True for d in decs) if decs else False
    # Nothing actually spent: the budget account stays at zero balance (no debit).
    bal = store.get_budget_account(tid).get("balance_minor", 0)
    ok = (res.get("ran") and len(realloc) >= 1 and has_reversal and all_dry and bal == 0)
    return (f"continuous reallocate-to-winners dry-run (ran={res.get('ran')}, "
            f"reallocate_decisions={len(realloc)}, reversal={has_reversal}, dry={all_dry}, bal={bal})", ok)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ads_w3_loop_"))
    _wire(tmp)
    checks = [
        _t_ad_events_idempotent(),
        _t_signal_feeds_bandit(),
        _t_same_day_capi(),
        _t_fatigue_decay_and_share(),
        _t_audience_expansion(),
        _t_learning_phase(),
        _t_continuous_reallocate_dry_run(),
    ]
    all_ok = True
    for label, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
        all_ok = all_ok and ok
    print("RESULT:", "ALL PASS" if all_ok else "FAILURES")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
