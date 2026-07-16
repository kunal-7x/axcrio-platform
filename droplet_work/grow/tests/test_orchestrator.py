"""Offline tests for grow.orchestrator (L3 speed-to-lead) + GrowLoop.on_lead_captured.
No network, no creds. Run:  cd droplet_work && python -m grow.tests.test_orchestrator
"""
from __future__ import annotations

import datetime as _dt

from grow.config import GrowConfig
from grow.loop import GrowLoop
from grow.model import (CapturedLead, ChannelResult, ChannelStatus, OrchStatus)
from grow.orchestrator import Orchestrator
from grow.store import JourneyStore

CFG = GrowConfig()


def _cap(**kw):
    base = dict(tenant_id="t1", lead_id="lead-1", phone="+919876543210", name="Asha",
                source_platform="meta", ctwa_clid="ctwa_1")
    base.update(kw)
    return CapturedLead(**base)


def _fire_wa(_c, _j):
    return ChannelResult("whatsapp", ChannelStatus.FIRED, ref="wamid.123")


def _fire_call(_c, _j):
    return ChannelResult("voice", ChannelStatus.FIRED, ref="call-abc")


def test_dormant_no_channels():
    o = Orchestrator(CFG, JourneyStore())  # default dormant senders
    r = o.orchestrate(_cap())
    assert r.status == OrchStatus.NO_CHANNELS
    assert all(c.status == ChannelStatus.SKIPPED_NO_CONFIG for c in r.channels)
    assert r.compliance_decision == "unenforced"  # engine not wired


def test_channels_fire_when_wired():
    o = Orchestrator(CFG, JourneyStore(), whatsapp_sender=_fire_wa, voice_caller=_fire_call)
    r = o.orchestrate(_cap())
    assert r.status == OrchStatus.DONE
    assert set(c.channel for c in r.fired) == {"whatsapp", "voice"}


def test_compliance_block_stops_outreach():
    def _block(_c, _j):
        return "block", ["dnd_listed"]
    o = Orchestrator(CFG, JourneyStore(), compliance_gate=_block,
                     whatsapp_sender=_fire_wa, voice_caller=_fire_call)
    r = o.orchestrate(_cap())
    assert r.status == OrchStatus.BLOCKED
    assert r.compliance_decision == "block"
    assert all(c.status == ChannelStatus.BLOCKED for c in r.channels)


def test_journey_threaded_and_persisted():
    js = JourneyStore()
    o = Orchestrator(CFG, js, whatsapp_sender=_fire_wa, voice_caller=_fire_call)
    r = o.orchestrate(_cap())
    j = js.get("t1", r.journey_id)
    assert j is not None
    assert j.ctwa_clid == "ctwa_1" and j.source_platform == "meta"


def test_journey_id_stable_per_lead():
    o = Orchestrator(CFG, JourneyStore())
    a = o.orchestrate(_cap()).journey_id
    b = o.orchestrate(_cap()).journey_id
    assert a == b and a.startswith("j_")


def test_sla_met_for_fresh_capture():
    o = Orchestrator(CFG, JourneyStore(), whatsapp_sender=_fire_wa)
    r = o.orchestrate(_cap())
    assert r.sla_met is True
    assert r.latency_ms >= 0


def test_sla_missed_for_stale_capture():
    o = Orchestrator(CFG, JourneyStore(), whatsapp_sender=_fire_wa, sla_seconds=60)
    stale = _now_minus(120)
    r = o.orchestrate(_cap(captured_at=stale))
    assert r.sla_met is False
    assert r.latency_ms >= 60000


def test_bad_sender_does_not_crash():
    def _boom(_c, _j):
        raise RuntimeError("provider down")
    o = Orchestrator(CFG, JourneyStore(), whatsapp_sender=_boom, voice_caller=_fire_call)
    r = o.orchestrate(_cap())
    # voice still fired; whatsapp recorded as failed; run completes
    assert r.status == OrchStatus.DONE
    wa = [c for c in r.channels if c.channel == "whatsapp"][0]
    assert wa.status == ChannelStatus.FAILED


def test_missing_ids_is_error():
    o = Orchestrator(CFG, JourneyStore())
    r = o.orchestrate(CapturedLead(tenant_id="", lead_id=""))
    assert r.status == OrchStatus.ERROR


# ---- loop end-to-end ----
def test_loop_on_lead_captured_dormant():
    loop = GrowLoop(config=CFG)
    out = loop.on_lead_captured("t1", "lead-xyz", phone="+919811111111", source_platform="meta")
    assert out["ok"] is True
    assert out["orchestration"]["status"] in ("no_channels", "done")
    # persisted + retrievable
    assert len(loop.orchestrations.list("t1")) == 1


def test_loop_on_lead_captured_fires_when_wired():
    loop = GrowLoop(config=CFG, whatsapp_sender=_fire_wa, voice_caller=_fire_call)
    out = loop.on_lead_captured("t1", "lead-fire", phone="+919822222222")
    assert out["ok"] is True
    assert out["orchestration"]["status"] == "done"
    assert "whatsapp" in out["orchestration"]["fired"]


def test_loop_lead_capture_swallows_bad_input():
    loop = GrowLoop(config=CFG)
    assert loop.on_lead_captured("", "")["ok"] is False


def _now_minus(seconds: int) -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(seconds=seconds)


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"PASS grow.tests.test_orchestrator ({len(fns)} tests)")


if __name__ == "__main__":
    _run()
