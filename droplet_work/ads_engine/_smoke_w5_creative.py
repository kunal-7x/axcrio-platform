"""Offline W5 CREATIVE smoke for ads_engine — job state machine, moderation gate, adapters,
direct-upload, EOL refusal. NO app boot, NO .env, NO real network, NO keys, NO caller.

Run:
  python -c "import sys; sys.path.insert(0,'droplet_work'); import ads_engine._smoke_w5_creative as s; s.main()"

Asserts (the W5 CREATIVE OFFLINE TESTS list):
  * job state machine advances queued->generating->composing->moderating->ready
  * moderation gate BLOCKS a policy-violating creative (never reaches ready as approved)
  * moderation gate BLOCKS a missing-RERA property creative
  * moderation gate BLOCKS a broken/gibberish-text creative
  * mocked adapters produce the expected request payloads (inline + async poll)
  * direct-upload path stores an asset variant + moderates it
  * EOL model is REFUSED (never instantiated / submit returns eol_model)
  * EOL chain resolution drops the EOL id
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Store wiring (tmp dir, no caller). Mirrors _smoke_w3._t_store_isolation.
# ---------------------------------------------------------------------------
def _wire_store(tmp: Path):
    import ads_engine as pkg

    def _read(path, default):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return default

    def _awj(path, data):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data), encoding="utf-8")

    pkg.wire(_read=_read, _write=lambda p, d: _awj(p, d),
             _atomic_write_json=_awj, var_dir=tmp)


# A fake httpx-like client for adapter payload tests: records the last request + returns scripted.
class _FakeResp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.headers = {}
        self.text = json.dumps(body)

    def json(self):
        return self._body


class _FakeClient:
    """Minimal stand-in for httpx.AsyncClient.request — records calls, serves a queue."""
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def request(self, method, url, params=None, json=None, data=None, headers=None):
        self.calls.append({"method": method, "url": url, "params": params,
                           "json": json, "headers": headers})
        if self.script:
            status, body = self.script.pop(0)
            return _FakeResp(status, body)
        return _FakeResp(599, {"_exhausted": True})

    async def aclose(self):
        pass


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------
def _t_eol_refused():
    from ads_engine import creative_models as cm
    # EOL detection.
    ok_detect = cm.is_eol("gpt-image-1") and cm.is_eol("veo-3.0") and not cm.is_eol("ideogram-v3")
    # Resolve chain drops an EOL override + EOL fallback.
    chain = cm.resolve_chain("bulk_image", override="gpt-image-1")
    ok_chain = "gpt-image-1" not in chain and "gemini-2.5-flash-image" in chain
    # get_model_class refuses an EOL id.
    ok_cls = cm.get_model_class("gpt-image-1") is None
    ok = ok_detect and ok_chain and ok_cls
    return (f"EOL model refused (detect={ok_detect}, chain={ok_chain}, cls={ok_cls})", ok)


def _t_eol_submit_refused():
    from ads_engine.creative_models import nano_banana
    # Force the adapter's model_id to an EOL id; submit must refuse before any network.
    adapter = nano_banana.build(get_secret_json=lambda: {"api_key": "k"})
    adapter.model_id = "gpt-image-1"
    from ads_engine.creative_models.base import GenRequest
    res = asyncio.run(adapter.submit(GenRequest(kind="bulk_image", prompt="x")))
    ok = (not res.ok) and res.error == "eol_model"
    return (f"EOL submit refused before network (error={res.error})", ok)


def _t_adapter_payloads():
    from ads_engine.creative_models import ideogram, flux
    from ads_engine.creative_models.base import GenRequest

    # Ideogram inline: returns a url, records Api-Key auth + the v3 endpoint.
    client = _FakeClient([(200, {"data": [{"url": "https://cdn/img1.png"}]})])
    ad = ideogram.build(get_secret_json=lambda: {"api_key": "IDEO_KEY"}, http=client)
    res = asyncio.run(ad.submit(GenRequest(kind="headline_image", headline="2BHK Wakad",
                                           aspect="9:16")))
    ideo_ok = (res.ok and res.inline and res.url == "https://cdn/img1.png"
               and client.calls[0]["url"].endswith("/v1/ideogram-v3/generate")
               and client.calls[0]["headers"].get("Api-Key") == "IDEO_KEY"
               and client.calls[0]["json"]["aspect_ratio"] == "ASPECT_9_16")

    # FLUX async: submit returns a job_ref, poll returns done with a url; x-key auth.
    fclient = _FakeClient([
        (200, {"id": "bfl_job_1"}),
        (200, {"status": "Ready", "result": {"sample": "https://cdn/flux.png"}}),
    ])
    fad = flux.build(get_secret_json=lambda: {"api_key": "BFL"}, http=fclient,
                     sleep_fn=_nosleep)
    sub = asyncio.run(fad.submit(GenRequest(kind="property_shot", prompt="villa", width=1024,
                                            height=1024)))
    pol = asyncio.run(fad.poll(sub.job_ref))
    flux_ok = (sub.ok and sub.job_ref == "bfl_job_1" and not sub.inline
               and pol.state == "done" and pol.url == "https://cdn/flux.png"
               and fclient.calls[0]["headers"].get("x-key") == "BFL")

    ok = ideo_ok and flux_ok
    return (f"adapters produce expected payloads (ideogram={ideo_ok}, flux={flux_ok})", ok)


async def _nosleep(_):
    return None


def _t_bannerbear_compose_payload():
    from ads_engine.creative_models import bannerbear
    from ads_engine.creative_models.base import GenRequest
    client = _FakeClient([
        (200, {"uid": "col_1"}),
        (200, {"status": "completed",
               "image_urls": {"feed_1x1": "https://cdn/1x1.png",
                              "story_9x16": "https://cdn/9x16.png"}}),
    ])
    ad = bannerbear.build(get_secret_json=lambda: {"api_key": "BB"}, http=client, sleep_fn=_nosleep)
    sub = asyncio.run(ad.submit(GenRequest(kind="multi_size", headline="Hi",
                                           source_url="https://cdn/src.png",
                                           sizes=["1080x1080", "1080x1920"])))
    pol = asyncio.run(ad.poll(sub.job_ref))
    ok = (sub.ok and sub.job_ref == "col_1"
          and pol.state == "done" and len(pol.sizes) == 2
          and client.calls[0]["url"].endswith("/v2/collections")
          and client.calls[0]["headers"].get("Authorization") == "Bearer BB")
    return (f"bannerbear compose -> all sizes (sizes={len(pol.sizes)})", ok)


def _make_service(tmp: Path, *, model_http_script=None):
    """Build a CreativeService whose adapters use scripted fake clients (no network)."""
    from ads_engine import creative
    # http_factory yields a fresh fake client per build, scripted to return inline images.

    def _http_factory():
        # Each generation adapter call returns one inline image; bannerbear gets a collection.
        return _FakeClient([
            (200, {"data": [{"url": "https://cdn/gen.png"}]}),         # ideogram inline
            (200, {"uid": "col_x"}),                                    # bannerbear submit
            (200, {"status": "completed",
                   "image_urls": {"feed_1x1": "https://cdn/a.png",
                                  "story_9x16": "https://cdn/b.png"}}),  # bannerbear poll
        ])

    def _resolve_def_id(tenant_id, model_id):
        return f"def_{model_id}"  # any non-empty so the secret closure proceeds

    def _get_secret_json(tenant_id, def_id):
        return {"api_key": "TESTKEY"}

    svc = creative.CreativeService(
        get_secret_json=_get_secret_json,
        resolve_def_id=_resolve_def_id,
        http_factory=_http_factory,
        sleep_fn=_nosleep,
    )
    return svc


def _t_job_state_machine(tmp: Path):
    from ads_engine import creative
    svc = _make_service(tmp)
    brief = {
        "product": "2BHK Wakad", "headline": "2BHK in Wakad ready to move",
        "primary_text": "Premium homes near IT park", "description": "RERA P52100012345",
        "rera_id": "P52100012345", "is_property": True, "language": "hinglish",
        "objective": "leads", "aspect": "1:1",
    }
    job = svc.submit("t_demo", "cmp_77", brief, kinds=["headline_image"])
    states = [job["state"]]
    guard = 0
    while job["state"] not in ("ready", "failed") and guard < 30:
        job = asyncio.run(svc.advance("t_demo", job))
        states.append(job["state"])
        guard += 1
    variants = svc.get_variants("t_demo", "cmp_77")
    approved = [v for v in variants if v.get("moderation_status") == "approved"]
    # Saw the full progression + ended ready + at least one approved variant with placements.
    saw_compose = "composing" in states
    saw_moderate = "moderating" in states
    ok = (job["state"] == "ready" and saw_compose and saw_moderate
          and len(approved) >= 1 and len(approved[0]["placements"]) >= 1)
    return (f"job machine queued->ready (states seen: {set(states)}, approved={len(approved)})", ok)


def _t_moderation_blocks_policy(tmp: Path):
    from ads_engine.creative import default_moderation, MOD_BLOCKED, MOD_APPROVED
    # 1) discriminatory housing copy -> BLOCKED.
    v_bad = {"variant_id": "v1", "headline": "2BHK", "primary_text": "Hindus only, no muslims",
             "description": "RERA P52100012345", "rera_id": "P52100012345", "is_property": True}
    r1 = default_moderation(v_bad, {})
    # 2) clean property ad with RERA -> APPROVED.
    v_ok = {"variant_id": "v2", "headline": "2BHK ready", "primary_text": "Premium homes",
            "description": "RERA P52100012345", "rera_id": "P52100012345", "is_property": True}
    r2 = default_moderation(v_ok, {})
    ok = (r1["status"] == MOD_BLOCKED and r1["checks"]["housing"] == "fail"
          and r2["status"] == MOD_APPROVED)
    return (f"moderation blocks discriminatory copy (bad={r1['status']}, ok={r2['status']})", ok)


def _t_moderation_blocks_no_rera(tmp: Path):
    from ads_engine.creative import default_moderation, MOD_BLOCKED
    v = {"variant_id": "v3", "headline": "Buy now", "primary_text": "Great flats",
         "description": "Zero brokerage", "rera_id": "", "is_property": True}
    r = default_moderation(v, {})
    ok = (r["status"] == MOD_BLOCKED and r["checks"]["rera"] == "fail")
    return (f"moderation blocks property ad with no RERA id (status={r['status']})", ok)


def _t_moderation_blocks_broken_text(tmp: Path):
    from ads_engine.creative import default_moderation, MOD_BLOCKED
    # Requested headline is a real phrase but the rendered/OCR'd text is gibberish -> fail.
    v = {"variant_id": "v4", "headline": "Book a site visit",
         "ocr_text": "Bxxkkstvshhtdf",  # gibberish (no vowels run)
         "description": "RERA P52100012345", "rera_id": "P52100012345", "is_property": True}
    r = default_moderation(v, {})
    ok = (r["status"] == MOD_BLOCKED and r["checks"]["broken_text"] == "fail")
    return (f"moderation blocks broken/gibberish text (status={r['status']})", ok)


def _t_blocked_never_publishable(tmp: Path):
    """A job whose variant is policy-violating ends with the variant BLOCKED, never approved."""
    from ads_engine import creative
    svc = _make_service(tmp)
    brief = {
        "product": "2BHK", "headline": "2BHK ready",
        "primary_text": "Family only, no bachelors",  # discriminatory -> must block
        "description": "RERA P52100012345", "rera_id": "P52100012345", "is_property": True,
    }
    job = svc.submit("t_block", "cmp_block", brief, kinds=["headline_image"])
    job = svc.advance_sync("t_block", job)
    variants = svc.get_variants("t_block", "cmp_block")
    blocked = [v for v in variants if v.get("moderation_status") == "blocked"]
    none_approved = all(v.get("moderation_status") != "approved" for v in variants)
    ok = (job["state"] == "ready" and len(blocked) >= 1 and none_approved)
    return (f"policy-violating variant BLOCKED, never approved (blocked={len(blocked)})", ok)


def _t_direct_upload(tmp: Path):
    from ads_engine import creative

    class _Bridge:
        def __init__(self):
            self.mirrored = []

        def get_asset(self, tenant_id, asset_id):
            if tenant_id != "t_up" or asset_id != "as_99":
                return None  # cross-tenant / unknown -> None
            return {"url": "https://cdn/upload.png", "headline": "My own ad"}

        def mirror_asset(self, tenant_id, payload):
            self.mirrored.append(payload)

    bridge = _Bridge()
    svc = creative.CreativeService(asset_bridge=bridge)
    # Clean upload with RERA -> stored + approved + mirrored.
    v = svc.import_upload("t_up", "cmp_up", "as_99",
                          brief={"headline": "2BHK ready", "rera_id": "P52100012345",
                                 "description": "RERA P52100012345", "is_property": True})
    stored = svc.store_mod.get_row("t_up", "ad_variants", v["variant_id"])
    # Cross-tenant fetch is refused.
    bad = svc.import_upload("t_other", "cmp_x", "as_99", brief={"is_property": False})
    ok = (v.get("source") == "uploaded" and v.get("moderation_status") == "approved"
          and stored is not None and stored.get("gallery_asset_id") == "as_99"
          and len(bridge.mirrored) == 1
          and bad.get("ok") is False)
    return (f"direct-upload stores+moderates asset (status={v.get('moderation_status')}, "
            f"mirrored={len(bridge.mirrored)}, cross_tenant_refused={bad.get('ok') is False})", ok)


def _t_per_tenant_override(tmp: Path):
    """A per-tenant model override slug is honored (tried first) at adapter resolve time."""
    from ads_engine import creative

    picked = {}

    def _override(tenant_id, kind):
        return "recraft-v3" if tenant_id == "t_ov" else ""

    def _resolve_def_id(tenant_id, model_id):
        picked["model"] = model_id
        return f"def_{model_id}"

    svc = creative.CreativeService(
        get_secret_json=lambda t, d: {"api_key": "K"},
        resolve_def_id=_resolve_def_id,
        model_override_for=_override,
        http_factory=lambda: _FakeClient([(200, {"data": [{"url": "https://cdn/x.png"}]})]),
        sleep_fn=_nosleep,
    )
    mid, adapter = svc._build_adapter("t_ov", "headline_image")
    ok = (mid == "recraft-v3" and adapter is not None)
    return (f"per-tenant override honored (model={mid})", ok)


# ---------------------------------------------------------------------------
# Runner.
# ---------------------------------------------------------------------------
def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ads_w5_creative_"))
    _wire_store(tmp)

    failures = []

    def check(name, cond):
        print(f"  {'PASS' if cond else 'FAIL'} — {name}")
        if not cond:
            failures.append(name)

    tests = [
        _t_eol_refused(),
        _t_eol_submit_refused(),
        _t_adapter_payloads(),
        _t_bannerbear_compose_payload(),
        _t_job_state_machine(tmp),
        _t_moderation_blocks_policy(tmp),
        _t_moderation_blocks_no_rera(tmp),
        _t_moderation_blocks_broken_text(tmp),
        _t_blocked_never_publishable(tmp),
        _t_direct_upload(tmp),
        _t_per_tenant_override(tmp),
    ]
    for msg, ok in tests:
        check(msg, ok)

    print(f"\nW5 creative smoke: {'ALL PASS' if not failures else 'FAILURES: ' + repr(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
