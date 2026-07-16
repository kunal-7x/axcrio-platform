"""Offline tests for grow.acquisition (L1 capture: Meta/Google/CTWA + consent + verify).
No network, no creds. Run:  cd droplet_work && python -m grow.tests.test_acquisition
"""
from __future__ import annotations

import hashlib
import hmac
import json

from grow.acquisition import (AcquisitionService, parse_ctwa_referral, parse_google_lead,
                              parse_meta_lead, verify_meta_challenge, verify_meta_signature)
from grow.config import GrowConfig
from grow.loop import GrowLoop

CFG = GrowConfig()

META_FETCHED = {"field_data": [
    {"name": "full_name", "values": ["Asha Verma"]},
    {"name": "phone_number", "values": ["+91 98765-43210"]},
    {"name": "email", "values": ["asha@example.com"]},
]}
META_VALUE = {"leadgen_id": "lg_123", "page_id": "P1", "form_id": "F1", "ad_id": "AD_9"}

GOOGLE_PAYLOAD = {"lead_id": "g_1", "campaign_id": "C_7", "gcl_id": "gcl_xyz",
                  "user_column_data": [
                      {"column_id": "FULL_NAME", "string_value": "Asha Verma"},
                      {"column_id": "PHONE_NUMBER", "string_value": "9876543210"},
                      {"column_id": "EMAIL", "string_value": "asha@example.com"}]}

CTWA_VALUE = {"messages": [{"from": "919876543210",
                            "referral": {"source_id": "AD_9", "ctwa_clid": "clid_abc",
                                         "headline": "3BHK riverview"}}],
              "contacts": [{"wa_id": "919876543210", "profile": {"name": "Asha"}}]}


# ---- parsers ----
def test_parse_meta_with_fetched_fields():
    c = parse_meta_lead(META_VALUE, "t1", fetched=META_FETCHED)
    assert c is not None
    assert c.source_platform == "meta" and c.source_ad_id == "AD_9"
    assert c.phone == "+91 98765-43210" and c.email == "asha@example.com"
    assert c.lead_id == "919876543210"  # normalized phone is the stable id
    assert c.consent_basis == "explicit" and c.consent_channel == "web_form"
    assert c.extra["leadgen_id"] == "lg_123"


def test_parse_meta_without_fetch_uses_leadgen_id():
    c = parse_meta_lead(META_VALUE, "t1")
    assert c is not None and c.lead_id == "lg_123" and c.source_ad_id == "AD_9"


def test_parse_google_lead():
    c = parse_google_lead(GOOGLE_PAYLOAD, "t1")
    assert c is not None
    assert c.source_platform == "google" and c.gclid == "gcl_xyz"
    assert c.lead_id == "919876543210" and c.email == "asha@example.com"
    assert c.campaign_id == "C_7"


def test_parse_ctwa_referral():
    c = parse_ctwa_referral(CTWA_VALUE, "t1")
    assert c is not None
    assert c.source_platform == "whatsapp" and c.ctwa_clid == "clid_abc"
    assert c.source_ad_id == "AD_9" and c.name == "Asha"
    assert c.consent_channel == "whatsapp"


def test_parse_empty_is_none():
    assert parse_meta_lead({}, "t1") is None
    assert parse_google_lead({}, "t1") is None
    assert parse_ctwa_referral({}, "t1") is None


# ---- verification ----
def test_meta_signature_verify():
    secret = "app_secret_123"
    body = json.dumps({"hello": "world"}).encode("utf-8")
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_meta_signature(body, sig, secret) is True
    assert verify_meta_signature(body, sig, "wrong_secret") is False
    assert verify_meta_signature(body, "sha256=deadbeef", secret) is False
    assert verify_meta_signature(body, "", secret) is False


def test_meta_challenge_echo():
    params = {"hub.mode": "subscribe", "hub.verify_token": "VT", "hub.challenge": "12345"}
    assert verify_meta_challenge(params, "VT") == "12345"
    assert verify_meta_challenge(params, "WRONG") is None
    assert verify_meta_challenge({}, "VT") is None


# ---- service end-to-end (via loop) ----
def _stub_consent(record):
    return lambda c: record.append(c.lead_id) or True


def test_service_google_end_to_end_records_consent_and_captures():
    loop = GrowLoop(config=CFG)
    recorded = []
    svc = AcquisitionService(loop, consent_recorder=lambda c: (recorded.append(c.lead_id) or True))
    out = svc.ingest_google(GOOGLE_PAYLOAD, "t1")
    assert out["ok"] is True
    assert out["consent_recorded"] is True
    assert recorded == ["919876543210"]
    # journey minted + orchestration recorded (dormant channels -> no_channels)
    assert len(loop.orchestrations.list("t1")) == 1
    j = [jj for jj in loop.journeys.list("t1") if jj.source_platform == "google"]
    assert j and j[0].source_ad_id == "C_7"


def test_service_ctwa_threads_ctwa_clid_into_journey():
    loop = GrowLoop(config=CFG)
    svc = AcquisitionService(loop, consent_recorder=lambda c: True)
    out = svc.ingest_ctwa(CTWA_VALUE, "t1")
    assert out["ok"] is True
    js = loop.journeys.list("t1")
    assert js and js[0].ctwa_clid == "clid_abc"


def test_service_meta_webhook_maps_page_to_tenant():
    loop = GrowLoop(config=CFG)
    svc = AcquisitionService(loop, consent_recorder=lambda c: True,
                             meta_lead_fetcher=lambda lgid: META_FETCHED)
    body = {"entry": [{"changes": [{"field": "leadgen", "value": META_VALUE}]}]}
    out = svc.ingest_meta_webhook(body, tenant_for_page=lambda pid: "t1" if pid == "P1" else "")
    assert out["count"] == 1 and out["captured"][0]["ok"] is True


def test_service_meta_webhook_drops_unmapped_page():
    loop = GrowLoop(config=CFG)
    svc = AcquisitionService(loop, consent_recorder=lambda c: True)
    body = {"entry": [{"changes": [{"field": "leadgen", "value": META_VALUE}]}]}
    out = svc.ingest_meta_webhook(body, tenant_for_page=lambda pid: "")  # no mapping
    assert out["captured"][0]["reason"] == "unmapped_page"


def test_service_unparseable_is_not_ok():
    loop = GrowLoop(config=CFG)
    svc = AcquisitionService(loop, consent_recorder=lambda c: True)
    assert svc.ingest_google({}, "t1")["ok"] is False


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"PASS grow.tests.test_acquisition ({len(fns)} tests)")


if __name__ == "__main__":
    _run()
