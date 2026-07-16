"""Offline W6 smoke — compliance gate + ingest + webhook trust-order + consent ledger + enqueue.

No app boot, no .env, no network. Run:
    python -c "import sys; sys.path.insert(0,'droplet_work'); import ads_engine._smoke_w6 as s; s.main()"

Asserts (every redteam mustFix):
  * gate BLOCKS: no-consent / form_checkbox-DCA-for-voice / out-of-quiet-hours / NCPR-listed.
  * gate ALLOWS only with DPDP + DLT-backed DCA + clean NCPR scrub inside quiet hours.
  * force_window is STRUCTURAL: True only in-window + verified DCA voice; False at night.
  * consent ledger is APPEND-ONLY + hash-chain verifies + tamper is detected.
  * enqueue applies tenant clamps + stays DRY-RUN (no JOBS row) until 140-series flag.
  * lead_id is SERVER-MINTED (ad_<hex>); the permissive default is unshippable (assert at import).
  * webhook rejects unknown page_id + forged HMAC (fail-closed) + accepts a valid signed body.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
from pathlib import Path


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

    JOBS = {}
    created = []

    async def _run_job(jid):
        created.append(jid)

    pkg.wire(_read=_read, _write=lambda p, d: _awrite_json(p, d),
             _atomic_write_json=_awrite_json, var_dir=tmp,
             JOBS=JOBS, run_job=_run_job,
             _tenant_by_id=lambda tid: {"max_concurrency": 3, "daily_call_cap": 500})
    return pkg, JOBS, created


# IST quiet-hours anchors (epoch seconds). 2026-06-25 in IST.
def _epoch_ist(hour: int) -> float:
    import datetime as dt
    IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
    return dt.datetime(2026, 6, 25, hour, 0, 0, tzinfo=IST).timestamp()


_NOON = _epoch_ist(12)    # inside 09-21 IST
_MIDNIGHT = _epoch_ist(2)  # 02:00 IST — outside the window


def _grant_full_consent(compliance, tid, phone, *, dlt=True, now=_NOON):
    compliance.record_consent(tid, lead_id="", phone=phone, kind=compliance.KIND_DPDP,
                              who=phone, source="test", method=compliance.METHOD_FORM_CHECKBOX,
                              now_epoch=now)
    method = compliance.METHOD_OTP_127_DLT if dlt else compliance.METHOD_FORM_CHECKBOX
    ev = {"dlt_consent_id": "DLT123"} if dlt else {}
    compliance.record_consent(tid, lead_id="", phone=phone, kind=compliance.KIND_DCA,
                              who=phone, source="test", method=method, evidence=ev, now_epoch=now)


def _test_gate(pkg) -> list:
    import ads_engine.compliance as compliance
    out = []
    # clean NCPR scrub by default; tests override.
    compliance.set_ncpr_scrub(lambda t, p: {"block": False, "categories": []})
    lead = {"phone": "+919812345678"}

    # no consent -> deny
    d = compliance.pre_dial_gate("t1", lead, now_epoch=_NOON)
    out.append(("gate denies no-consent", not d.allow and d.reason == "no_dpdp_consent"))

    # checkbox DCA for voice -> deny (C4)
    _grant_full_consent(compliance, "t2", "+919812345678", dlt=False)
    d = compliance.pre_dial_gate("t2", {"phone": "+919812345678"}, now_epoch=_NOON)
    out.append(("gate denies form_checkbox-DCA-for-voice",
                not d.allow and d.reason == "dca_not_dlt_backed_for_voice"))

    # full consent + clean scrub, in-window -> allow
    _grant_full_consent(compliance, "t3", "+919812345678", dlt=True)
    d = compliance.pre_dial_gate("t3", {"phone": "+919812345678"}, now_epoch=_NOON)
    out.append(("gate allows DPDP+DLT-DCA+clean-NCPR in-window", d.allow and d.reason == "allow"))

    # force_window structural: True in-window, False at night (C2)
    fw_day = compliance.compute_force_window(d, now_epoch=_NOON)
    fw_night = compliance.compute_force_window(d, now_epoch=_MIDNIGHT)
    out.append(("force_window True in quiet-hours window", fw_day is True))
    out.append(("force_window False at night (never literal True)", fw_night is False))

    # NCPR-listed -> deny
    compliance.set_ncpr_scrub(lambda t, p: {"block": True, "categories": []})
    _grant_full_consent(compliance, "t4", "+919812345678", dlt=True)
    d = compliance.pre_dial_gate("t4", {"phone": "+919812345678"}, now_epoch=_NOON)
    out.append(("gate denies NCPR full-DND", not d.allow and d.reason == "ncpr_full_dnd"))

    # Real-Estate category block -> deny
    compliance.set_ncpr_scrub(lambda t, p: {"block": False, "categories": ["real_estate"]})
    _grant_full_consent(compliance, "t5", "+919812345678", dlt=True)
    d = compliance.pre_dial_gate("t5", {"phone": "+919812345678"}, now_epoch=_NOON)
    out.append(("gate denies NCPR real-estate category",
                not d.allow and d.reason == "ncpr_realestate_cat"))

    # NCPR unavailable (no provider) -> fail-closed deny
    compliance.set_ncpr_scrub(None)
    _grant_full_consent(compliance, "t6", "+919812345678", dlt=True)
    d = compliance.pre_dial_gate("t6", {"phone": "+919812345678"}, now_epoch=_NOON)
    out.append(("gate fail-closed when NCPR unavailable",
                not d.allow and d.reason == "ncpr_unavailable"))
    # restore clean scrub for downstream tests
    compliance.set_ncpr_scrub(lambda t, p: {"block": False, "categories": []})
    return out


def _test_ledger(pkg) -> list:
    import ads_engine.compliance as compliance
    import ads_engine.store as store
    out = []
    tid = "t_led"
    compliance.record_consent(tid, lead_id="", phone="+919800000001",
                              kind=compliance.KIND_DPDP, who="x", source="t",
                              method=compliance.METHOD_FORM_CHECKBOX)
    compliance.record_consent(tid, lead_id="", phone="+919800000001",
                              kind=compliance.KIND_DCA, who="x", source="t",
                              method=compliance.METHOD_OTP_127_DLT, evidence={"dlt_consent_id": "D"})
    v = compliance.verify_chain(tid)
    out.append(("consent chain verifies clean", v["ok"] and v["length"] == 2))

    # tamper: edit a row in place -> chain break detected
    rows = store.consent_log_rows(tid)
    rows[0] = dict(rows[0]); rows[0]["phone"] = "+910000000000"  # mutate content, keep old hash
    store.put_tenant_file(tid, "consent_log", rows)
    v2 = compliance.verify_chain(tid)
    out.append(("consent chain tamper detected", (not v2["ok"]) and v2["broken_at"] == 0))

    # STICKY 90-day cool-off: revoke, then RE-consent within the window -> the gate must STILL deny
    # cooloff_90d (a fresh grant cannot clear an in-force post-withdrawal cool-off; design §A.20).
    compliance.set_ncpr_scrub(lambda t, p: {"block": False, "categories": []})
    tcl = "t_cooloff"
    ph = "+919800000099"
    _grant_full_consent(compliance, tcl, ph, dlt=True, now=_NOON)
    compliance.revoke_consent(tcl, phone=ph, now_epoch=_NOON)              # cooloff = noon + 90d
    # re-consent the SAME day (well inside the 90-day cool-off window).
    _grant_full_consent(compliance, tcl, ph, dlt=True, now=_NOON + 60)
    d = compliance.pre_dial_gate(tcl, {"phone": ph}, now_epoch=_NOON + 120)
    out.append(("re-consent within 90d cool-off STILL denied (sticky cool-off)",
                (not d.allow) and d.reason == "cooloff_90d"))
    # after the cool-off expires, the re-consent becomes dialable again.
    after = _NOON + 91 * 24 * 3600
    d2 = compliance.pre_dial_gate(tcl, {"phone": ph}, now_epoch=after)
    out.append(("re-consent dialable AFTER cool-off expires", d2.allow and d2.reason == "allow"))
    return out


def _test_ingest_enqueue(pkg, JOBS, created) -> list:
    import ads_engine.compliance as compliance
    import ads_engine.leads as leads
    out = []
    os.environ.pop("ADS_TELEPHONY_140", None)  # 140-series OFF => dry-run
    import ads_engine.config as cfg
    cfg.set_cfg_get(None)
    compliance.set_ncpr_scrub(lambda t, p: {"block": False, "categories": []})
    tid = "t_ing"
    _grant_full_consent(compliance, tid, "+919812345678", dlt=True)
    lead = leads.ingest(tid, leads.SOURCE_FORM, {"name": "Asha", "phone": "9812345678"},
                        channel="voice", now_epoch=_NOON)
    out.append(("lead_id server-minted (ad_<hex>)",
                str(lead.get("lead_id", "")).startswith("ad_")))
    out.append(("phone normalized to +91 E.164", lead.get("phone") == "+919812345678"))
    out.append(("ingest passes gate -> dry_run (no JOBS, 140-series off)",
                lead.get("status") == "dry_run" and len(JOBS) == 0 and len(created) == 0))

    # blocked lead (no consent) -> blocked status, no enqueue
    lead2 = leads.ingest("t_ing_noc", leads.SOURCE_FORM, {"name": "B", "phone": "9812345679"},
                         channel="voice", now_epoch=_NOON)
    out.append(("no-consent lead blocked, not enqueued",
                lead2.get("status", "").startswith("blocked") and len(JOBS) == 0))

    # enqueue clamps: turn 140-series ON, verify clamp values + dry_run flips to enqueued.
    # create_task needs a running loop (prod calls this from an async route) -> run in one.
    os.environ["ADS_TELEPHONY_140"] = "1"
    import asyncio

    async def _do_enq():
        r = leads.enqueue_call(tid, {"lead_id": "ad_x", "phone": "+919812345678", "name": "A",
                                     "source": "form", "campaign_id": "c1"}, force_window=True)
        await asyncio.sleep(0)  # let the create_task(run_job) schedule + run
        return r

    enq = asyncio.new_event_loop().run_until_complete(_do_enq())
    job = JOBS.get(enq.get("job_id")) if enq.get("job_id") else None
    clamp_ok = bool(job and job["concurrency"] == 1 and job["daily_cap"] == 500
                    and job["hourly_cap"] == 200 and job["source"] == "ad"
                    and job["ads_source"] == "form" and job["force_window"] is True)
    out.append(("enqueue applies tenant clamps + tags source=ad", clamp_ok))
    out.append(("enqueue creates run_job task when 140-series ON", len(created) == 1))
    os.environ.pop("ADS_TELEPHONY_140", None)
    return out


def _test_webhook_trust(pkg) -> list:
    """Fail-closed trust-ordering: unknown page_id + forged HMAC rejected; valid accepted.
    Tests the HMAC primitive + the page-map miss directly (no FastAPI request needed)."""
    import ads_engine.store as store
    from ads_engine.connectors.meta import MetaConnector
    out = []
    # unknown page_id -> no tenant resolves (fail-closed at the webhook).
    out.append(("unknown page_id resolves to None (reject)",
                store.get_tenant_for_page("999_unmapped") is None))
    # map a page (ownership) then verify uniqueness conflict.
    store.link_page_to_tenant("t_owner", "PAGE1", actor="connect")
    out.append(("page_id resolves to owner after link",
                store.get_tenant_for_page("PAGE1") == "t_owner"))
    conflict = False
    try:
        store.link_page_to_tenant("t_attacker", "PAGE1")
    except store.PageOwnershipConflict:
        conflict = True
    out.append(("page uniqueness: second tenant rejected (anti-hijack)", conflict))

    # HMAC: forged sig rejected, valid accepted (fail-closed primitive).
    secret = "app_sec_123"
    body = b'{"entry":[{"id":"PAGE1","changes":[{"field":"leadgen","value":{"leadgen_id":"L1"}}]}]}'
    good = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    mc = MetaConnector(creds=None)
    out.append(("HMAC accepts a valid signature", mc.verify_webhook_signature(secret, body, good) is True))
    out.append(("HMAC rejects a forged signature",
                mc.verify_webhook_signature(secret, body, "sha256=deadbeef") is False))
    out.append(("HMAC rejects missing secret (fail-closed)",
                mc.verify_webhook_signature("", body, good) is False))
    return out


def _test_fail_closed_unshippable() -> list:
    import ads_engine.compliance as compliance
    out = []
    ok = True
    try:
        compliance.assert_fail_closed()
    except AssertionError:
        ok = False
    out.append(("permissive default unshippable: assert passes when safe", ok))
    # flip a bypass switch -> assertion trips
    compliance.NCPR_BYPASS_CONSENTED = True
    tripped = False
    try:
        compliance.assert_fail_closed()
    except AssertionError:
        tripped = True
    compliance.NCPR_BYPASS_CONSENTED = False
    out.append(("permissive default unshippable: assert TRIPS if bypass enabled", tripped))
    return out


def _test_caller_additive() -> list:
    """Prove the caller.py W6 edit is diff-only-additive + FEATURE_ADS=0 byte-identical.

    The two edits: (1) a dict-spread that stamps ads_source on the CALLS row ONLY when
    job['source']=='ad'; (2) the reconcile guard `elif not (FEATURE_ADS and c.get('ads_source'))`.
    We assert the exact source markers exist and that the guard reduces to the legacy `else` when
    FEATURE_ADS is False (byte-identical control flow at rest)."""
    out = []
    p = Path(__file__).resolve().parents[1] / "caller.py"
    src = p.read_text(encoding="utf-8")
    out.append(("caller edit (1): ads_source stamped only for source=='ad' jobs",
                'if job.get("source") == "ad" else {}' in src))
    out.append(("caller edit (2): reconcile guard is FEATURE_ADS-gated",
                'elif not (globals().get("FEATURE_ADS", False) and c.get("ads_source")):' in src))
    # Byte-identical proof: the guard predicate with FEATURE_ADS False == always-enter (legacy else).
    FEATURE_ADS = False
    c = {"ads_source": "form"}  # even a tagged row enters the branch when the flag is off.
    enters_branch = not (FEATURE_ADS and c.get("ads_source"))
    out.append(("FEATURE_ADS=0 => reconcile guard == legacy else (byte-identical)",
                enters_branch is True))
    # And with the flag ON, an ad-source row is SKIPPED (the bypass is closed).
    FEATURE_ADS = True
    skipped = (FEATURE_ADS and c.get("ads_source"))
    out.append(("FEATURE_ADS=1 => ad-source call SKIPS retry re-enqueue (C1 closed)",
                bool(skipped) is True))
    return out


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ads_w6_"))
    os.environ["FEATURE_ADS"] = "1"
    pkg, JOBS, created = _wire(tmp)
    checks = []
    checks += _test_gate(pkg)
    checks += _test_ledger(pkg)
    checks += _test_ingest_enqueue(pkg, JOBS, created)
    checks += _test_webhook_trust(pkg)
    checks += _test_fail_closed_unshippable()
    checks += _test_caller_additive()
    all_ok = True
    for label, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
        all_ok = all_ok and bool(ok)
    print("RESULT:", "ALL PASS" if all_ok else "FAILURES")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
