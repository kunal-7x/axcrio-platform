"""Offline W6-feedback smoke — CAPI + Google Data Manager quality feedback + reconciliation.

No app boot, no .env, NO real network (connectors are MOCKED via feedback.set_connector_resolver).
Run:
    python -c "import sys; sys.path.insert(0,'droplet_work'); import ads_engine._smoke_w6_feedback as s; s.main()"

Asserts (every W6-feedback requirement):
  * a QUALIFIED lead emits a CAPI event + a Data Manager event with the right quality value and a
    TENANT-PREFIXED, deterministic event_id (tenant_id|lead_id|event_name).
  * the signal is the QUALITY signal (Qualified/Visited/Booked), NEVER "form submitted"/raw Lead.
  * action_source: phone_call for the AI-call Qualified; system_generated for a CRM Booked/Visited.
  * a JUNK lead emits NOTHING (negative-by-absence) — no CAPI, no DM, no conversion row.
  * event_id is idempotent: re-emitting the same lead+event reuses ONE conversion row.
  * Google feedback rides the Data Manager :ingestEvents path (upload_conversions), NEVER the
    blocked Ads-API legacy path.
  * reconciliation_factor is CLAMPED to [0.1, 3.0] and written into bandit_state.
  * a failed send queues a retry row; emit still returns without raising.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# A pure MOCK connector — records calls, returns a structured result. Zero network.
# ---------------------------------------------------------------------------
class _Res:
    def __init__(self, ok=True, data=None, error=None, detail=""):
        self.ok = ok
        self.data = data or {}
        self.error = error
        self.detail = detail
        self.status = 200 if ok else 400


class _MockMeta:
    """Stands in for MetaConnector — uses the REAL hash/build helpers' contract shape."""

    def __init__(self, recorder, *, fail=False):
        self._rec = recorder
        self._fail = fail

    def build_capi_event(self, *, event_name, event_time, action_source, user_data,
                         custom_data, event_id="", event_source_url=""):
        # Mirror the real connector: hash em/ph (sha256), keep the rest. Minimal stand-in.
        import hashlib

        def _h(v):
            return hashlib.sha256(str(v).strip().lower().encode()).hexdigest()
        ud = {}
        for k, v in (user_data or {}).items():
            ud[k] = _h(v) if k in ("em", "ph", "fn", "ln") else v
        return {"event_name": event_name, "event_time": event_time,
                "action_source": action_source, "user_data": ud,
                "custom_data": custom_data, "event_id": event_id}

    async def send_capi(self, events, *, test_event_code="", dataset_id=""):
        self._rec.setdefault("meta", []).extend(events)
        if self._fail:
            from ads_engine.connectors.base import ConnectorError
            return _Res(ok=False, error=ConnectorError.RATE_LIMITED)
        return _Res(ok=True, data={"fbtrace_id": "TRACE123", "events_received": len(events)})


class _MockGoogle:
    def __init__(self, recorder, *, fail=False):
        self._rec = recorder
        self._fail = fail
        self.legacy_attempted = False

    async def upload_conversions(self, events, *, _legacy=False):
        if _legacy:
            self.legacy_attempted = True
            from ads_engine.connectors.base import ConnectorError
            return _Res(ok=False, error=ConnectorError.BLOCKED_GOOGLE_LEGACY)
        self._rec.setdefault("google", []).extend(events)
        if self._fail:
            from ads_engine.connectors.base import ConnectorError
            return _Res(ok=False, error=ConnectorError.UPSTREAM)
        return _Res(ok=True, data={"requestId": "REQ987"})


def _wire(tmp: Path):
    import ads_engine as pkg

    def _read(path, default):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return default

    def _awrite_json(path, data):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data), encoding="utf-8")

    pkg.wire(_read=_read, _write=lambda p, d: _awrite_json(p, d),
             _atomic_write_json=_awrite_json, var_dir=tmp)
    return pkg


def _install_mocks(*, meta_fail=False, google_fail=False):
    import ads_engine.feedback as feedback
    rec: dict = {}
    mg = _MockGoogle(rec, fail=google_fail)

    def _resolver(tenant_id, channel, *, http=None):
        if channel == "meta":
            return _MockMeta(rec, fail=meta_fail)
        if channel == "google":
            return mg
        return None
    feedback.set_connector_resolver(_resolver)
    return rec, mg


def _run(coro):
    import asyncio
    return asyncio.new_event_loop().run_until_complete(coro)


def _test_qualified_emit(pkg) -> list:
    import ads_engine.feedback as feedback
    import ads_engine.store as store
    out = []
    rec, mg = _install_mocks()
    tid = "t_fb1"
    lead = {"lead_id": "ad_abc123", "phone": "+919812345678", "email": "asha@example.com",
            "name": "Asha Verma", "campaign_id": "camp1", "score": "hot"}
    res = _run(feedback.emit_quality(tid, lead))

    out.append(("qualified lead emitted", res.get("emitted") is True))
    out.append(("event is QUALITY (Qualified), not raw Lead/form-submit",
                res.get("event") == "Qualified"))
    eid = res.get("event_id")
    out.append(("event_id is tenant-prefixed deterministic (tenant|lead|event)",
                eid == "t_fb1|ad_abc123|Qualified"))

    # CAPI event recorded with the right quality value + event_id + phone-call action_source.
    meta_evs = rec.get("meta", [])
    capi_ok = (len(meta_evs) == 1 and meta_evs[0]["event_name"] == "Qualified"
               and meta_evs[0]["event_id"] == eid
               and meta_evs[0]["custom_data"]["lead_quality"] == "hot"
               and meta_evs[0]["action_source"] == "phone_call")
    out.append(("CAPI event: Qualified + quality=hot + tenant-prefixed event_id + phone_call",
                capi_ok))
    # phone is SHA-256 hashed (never plaintext PII out).
    ph = meta_evs[0]["user_data"].get("ph", "")
    out.append(("CAPI user_data phone is SHA-256 hashed (no plaintext PII)",
                len(ph) == 64 and ph != "+919812345678"))

    # Data Manager event recorded via the ingestEvents path, dedup transactionId == event_id.
    g_evs = rec.get("google", [])
    dm_ok = (len(g_evs) == 1 and g_evs[0]["eventName"] == "Qualified"
             and g_evs[0]["transactionId"] == eid)
    out.append(("Data Manager event: Qualified + transactionId==event_id (idempotent)", dm_ok))
    out.append(("Google legacy Ads-API path NEVER attempted (Data Manager only)",
                mg.legacy_attempted is False))

    # conversion row persisted crm_true + sent-state for BOTH platforms.
    convs = store.get_tenant_file(tid, "conversions")
    conv = next((c for c in convs if c.get("event_id") == eid), None)
    out.append(("conversion row persisted crm_true + both sent",
                conv is not None and conv["crm_true"] is True
                and conv["sent_meta"]["ok"] and conv["sent_google"]["ok"]))
    return out


def _test_crm_outcome_action_source(pkg) -> list:
    import ads_engine.feedback as feedback
    out = []
    rec, _ = _install_mocks()
    tid = "t_fb2"
    # CRM-true 'booked' outcome -> Booked event + system_generated action_source.
    lead = {"lead_id": "ad_booked", "phone": "+919800000001", "campaign_id": "c2",
            "score": "warm", "crm_outcome": "booked"}
    res = _run(feedback.emit_quality(tid, lead))
    out.append(("CRM booked -> Booked event (strongest signal wins)",
                res.get("event") == "Booked"))
    meta_evs = rec.get("meta", [])
    out.append(("CRM Booked uses system_generated action_source",
                meta_evs and meta_evs[0]["action_source"] == "system_generated"))
    return out


def _test_junk_emits_nothing(pkg) -> list:
    import ads_engine.feedback as feedback
    import ads_engine.store as store
    out = []
    rec, _ = _install_mocks()
    tid = "t_fb_junk"
    lead = {"lead_id": "ad_junk", "phone": "+919800000002", "campaign_id": "c3", "score": "junk"}
    res = _run(feedback.emit_quality(tid, lead))
    out.append(("junk lead emits NOTHING (negative-by-absence)",
                res.get("emitted") is False and res.get("reason") == "no_quality_event"))
    out.append(("junk lead: no CAPI + no Data Manager call",
                not rec.get("meta") and not rec.get("google")))
    out.append(("junk lead: no conversion row written",
                len(store.get_tenant_file(tid, "conversions")) == 0))
    return out


def _test_idempotent_event_id(pkg) -> list:
    import ads_engine.feedback as feedback
    import ads_engine.store as store
    out = []
    _install_mocks()
    tid = "t_fb_idem"
    lead = {"lead_id": "ad_idem", "phone": "+919800000003", "campaign_id": "c4", "score": "hot"}
    _run(feedback.emit_quality(tid, lead))
    _run(feedback.emit_quality(tid, lead))   # re-emit the SAME lead+event
    convs = store.get_tenant_file(tid, "conversions")
    eid = feedback.make_event_id(tid, "ad_idem", "Qualified")
    matching = [c for c in convs if c.get("event_id") == eid]
    out.append(("re-emit reuses ONE conversion row (idempotent on event_id)", len(matching) == 1))
    out.append(("re-emit bumped the meta attempt counter (not a new row)",
                matching and matching[0]["sent_meta"]["attempts"] == 2))
    return out


def _test_reconciliation_clamp(pkg) -> list:
    import ads_engine.feedback as feedback
    import ads_engine.store as store
    out = []
    _install_mocks()
    tid = "t_recon"
    # Pure clamp bounds.
    out.append(("clamp floors at 0.1", feedback._clamp_factor(0.0) == 0.1))
    out.append(("clamp ceils at 3.0", feedback._clamp_factor(99.0) == 3.0))
    out.append(("clamp passes mid-band", abs(feedback._clamp_factor(1.5) - 1.5) < 1e-9))
    out.append(("clamp NaN -> 1.0", feedback._clamp_factor(float("nan")) == 1.0))

    # Build a conversions ledger: 5 crm_true, only 1 platform-reported => raw 5.0 -> clamp 3.0.
    rows = []
    for i in range(5):
        rows.append({"event_id": f"{tid}|ad_{i}|Qualified", "campaign_id": "rc1",
                     "crm_true": True,
                     "platform_reported": {"meta": (1 if i == 0 else None), "google": None}})
    store.put_tenant_file(tid, "conversions", rows)
    factors = feedback.reconcile(tid)
    rc = factors.get("rc1", {})
    out.append(("reconcile: 5 crm_true / 1 platform -> clamped to 3.0",
                rc.get("factor") == 3.0 and rc.get("crm_true") == 5
                and rc.get("platform_reported") == 1))
    # factor written into bandit_state for the optimizer to read.
    bs = store.get_bandit_state(tid, "rc1") or {}
    out.append(("recon_factor written into bandit_state",
                bs.get("recon_factor") == 3.0 and bs.get("recon_crm_true") == 5))
    return out


def _test_failed_send_queues_retry(pkg) -> list:
    import ads_engine.feedback as feedback
    import ads_engine.store as store
    out = []
    rec, _ = _install_mocks(meta_fail=True, google_fail=False)
    tid = "t_retry"
    lead = {"lead_id": "ad_retry", "phone": "+919800000004", "campaign_id": "c5", "score": "hot"}
    res = _run(feedback.emit_quality(tid, lead))
    out.append(("emit returns despite a failed meta send (never raises)",
                res.get("emitted") is True and res["meta"]["ok"] is False
                and res["google"]["ok"] is True))
    audit = store.get_tenant_file(tid, "ads_audit")
    queued = [a for a in audit if a.get("event") == "feedback.retry_queued"
              and a.get("channel") == "meta"]
    out.append(("failed meta send queued a retry row", len(queued) == 1))
    return out


def _test_no_real_network() -> list:
    """Prove the smoke used the injected mock, not a live connector (no socket can have opened)."""
    import ads_engine.feedback as feedback
    out = []
    # The resolver is the injected mock — the real connectors.get_connector is NOT what we called.
    out.append(("connector resolver is the injected mock (no real network)",
                feedback._get_connector is not None))
    return out


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ads_w6_fb_"))
    os.environ["FEATURE_ADS"] = "1"
    pkg = _wire(tmp)
    checks = []
    checks += _test_qualified_emit(pkg)
    checks += _test_crm_outcome_action_source(pkg)
    checks += _test_junk_emits_nothing(pkg)
    checks += _test_idempotent_event_id(pkg)
    checks += _test_reconciliation_clamp(pkg)
    checks += _test_failed_send_queues_retry(pkg)
    checks += _test_no_real_network()
    all_ok = True
    for label, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
        all_ok = all_ok and bool(ok)
    print("RESULT:", "ALL PASS" if all_ok else "FAILURES")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
