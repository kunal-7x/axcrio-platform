"""Offline tests for grow.adapters (deep wiring: registration seams + live adapters).
No network/creds. Run:  cd droplet_work && python -m grow.tests.test_adapters
"""
from __future__ import annotations

from grow.adapters import (clear_registrations, graph_whatsapp_send, get_main_loop,
                           live_voice_caller, live_whatsapp_sender, register_voice_caller,
                           register_whatsapp_sender, set_main_loop, status)
from grow.config import GrowConfig
from grow.loop import GrowLoop
from grow.model import CapturedLead, ChannelResult, ChannelStatus, Journey

CFG = GrowConfig()


def _cap():
    return CapturedLead(tenant_id="t1", lead_id="919800000000", phone="+919800000000", name="Asha")


def _journey():
    return Journey(tenant_id="t1", journey_id="j_x")


def test_voice_dormant_without_registration():
    clear_registrations()
    r = live_voice_caller(_cap(), _journey())
    assert r.status == ChannelStatus.SKIPPED_NO_CONFIG and r.channel == "voice"


def test_voice_uses_registered():
    clear_registrations()
    register_voice_caller(lambda c, j: ChannelResult("voice", ChannelStatus.FIRED, ref="call-9"))
    r = live_voice_caller(_cap(), _journey())
    assert r.status == ChannelStatus.FIRED and r.ref == "call-9"
    clear_registrations()


def test_whatsapp_dormant_without_creds_or_registration(monkeypatch=None):
    clear_registrations()
    # no META_WA_* env in CI -> graph sender dormant
    r = live_whatsapp_sender(_cap(), _journey())
    assert r.status == ChannelStatus.SKIPPED_NO_CONFIG


def test_whatsapp_uses_registered():
    clear_registrations()
    register_whatsapp_sender(lambda c, j: ChannelResult("whatsapp", ChannelStatus.FIRED, ref="wamid.1"))
    r = live_whatsapp_sender(_cap(), _journey())
    assert r.status == ChannelStatus.FIRED and r.ref == "wamid.1"
    clear_registrations()


def test_wrap_tolerates_dict_and_str_and_exceptions():
    clear_registrations()
    register_voice_caller(lambda c, j: "call-str")          # plain string ref
    assert live_voice_caller(_cap(), _journey()).ref == "call-str"
    register_voice_caller(lambda c, j: {"status": ChannelStatus.FIRED, "ref": "call-dict"})
    assert live_voice_caller(_cap(), _journey()).ref == "call-dict"
    register_voice_caller(lambda c, j: (_ for _ in ()).throw(RuntimeError("boom")))
    r = live_voice_caller(_cap(), _journey())
    assert r.status == ChannelStatus.FAILED and "reg_err" in r.reason
    clear_registrations()


def test_graph_send_dormant_without_creds():
    r = graph_whatsapp_send(_cap(), _journey())
    assert r.status == ChannelStatus.SKIPPED_NO_CONFIG  # no_wa_creds / no_template


def test_main_loop_set_get():
    sentinel = object()
    set_main_loop(sentinel)
    assert get_main_loop() is sentinel
    set_main_loop(None)


def test_status_shape():
    s = status()
    for k in ("whatsapp_registered", "voice_registered", "graph_wa_creds", "main_loop_bound"):
        assert k in s


def test_growloop_default_seams_are_live_and_pick_up_registration():
    clear_registrations()
    register_voice_caller(lambda c, j: ChannelResult("voice", ChannelStatus.FIRED, ref="rc"))
    register_whatsapp_sender(lambda c, j: ChannelResult("whatsapp", ChannelStatus.FIRED, ref="rw"))
    loop = GrowLoop(config=CFG)  # default seams = live adapters (late-binding)
    out = loop.on_lead_captured("t1", "919800000000", phone="+919800000000", source_platform="meta")
    fired = out["orchestration"]["fired"]
    assert "voice" in fired and "whatsapp" in fired
    clear_registrations()


def test_growloop_default_dormant_without_registration():
    clear_registrations()
    loop = GrowLoop(config=CFG)
    out = loop.on_lead_captured("t1", "919811111111", phone="+919811111111")
    assert out["orchestration"]["status"] == "no_channels"  # live adapters dormant w/o creds/reg


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    clear_registrations()
    print(f"PASS grow.tests.test_adapters ({len(fns)} tests)")


if __name__ == "__main__":
    _run()
