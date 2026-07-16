"""Offline V2-W4 smoke: the vault-configurable reasoning-model gateway + LLM features + creative AI.

No app boot, no .env, no network, no litellm/langfuse, no caller import. Deterministic. A FAKE
provider_registry seam supplies the per-tenant vault; a MOCK complete_impl supplies the LLM so the
whole resolve -> cap -> route -> meter path is exercised with NO key and NO provider.

Run:
  python -c "import sys; sys.path.insert(0,'droplet_work'); import ads_engine._smoke_v2w4_llm as s; s.main()"

Asserts (the W4 gate):
  1. new modules byte-compile + contain NO `import caller` (voice brain untouched).
  2. gateway fail-CLOSED: no vault config -> not_configured; missing key -> no_credential.
  3. per-tenant config resolves -> provider/model selected -> litellm model string prefixed.
  4. a call routes through the mock provider, cost is metered into month-to-date spend.
  5. per-tenant monthly cap is fail-closed (spend >= cap -> cap_exceeded, impl never called).
  6. save_selection writes a new model into the vault -> next resolve picks it up (real-time).
  7. first LLM feature: ad-copy generation + brief-parse return structured proposals (mock).
  8. auto creative-variants: format adaptation + slideshow go THROUGH the moderation gate;
     discriminatory copy is still BLOCKED (gate not bypassed).
  9. asset bridge: mirror -> get round-trips; a cross-tenant get returns None (isolation).
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

_PKG = Path(__file__).parent
_DROPLET = _PKG.parent


# --------------------------------------------------------------------------- #
# Fake provider_registry seam (in-memory vault) — read + write round-trip.
# --------------------------------------------------------------------------- #
class _FakeDef:
    def __init__(self, _id, named_provider, slug, caps):
        self.id = _id
        self.named_provider = named_provider
        self.slug = slug
        self.capabilities = caps


class _FakeStore:
    def __init__(self):
        self._defs: dict = {}
        self._creds: dict = {}

    def available(self):
        return True

    def add_definition(self, tenant, d):
        self._defs[(tenant, d.id)] = d

    def list_definitions(self, tenant_id, *, capability="", enabled_only=False):
        return [d for (t, _id), d in self._defs.items() if t == tenant_id]

    def get_definition_by_slug(self, tenant_id, slug):
        for (t, _id), d in self._defs.items():
            if t == tenant_id and d.slug == slug:
                return d
        return None

    def get_active_credential(self, tenant_id, provider_def_id):
        return self._creds.get((tenant_id, provider_def_id))

    def upsert_credential(self, tenant_id, provider_def_id, enc, scope="integration"):
        self._creds[(tenant_id, provider_def_id)] = {"def_id": provider_def_id, "ciphertext": enc}


class _FakeCreds:
    @staticmethod
    def decrypt_credential(row):
        return row.get("ciphertext") if isinstance(row, dict) else None

    @staticmethod
    def encrypt_credential(tenant_id, provider_def_id, blob_dict):
        # round-trip: store the JSON string as the "ciphertext" the decrypt returns.
        return json.dumps(blob_dict)


def _wire(store, var_dir):
    import ads_engine as pkg
    registry = SimpleNamespace(store=store, credentials=_FakeCreds())

    def _read(path, default):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return default

    def _awj(path, data):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data), encoding="utf-8")

    # ONE wire call: registry seam + file IO seams + var_dir together (wire() resets omitted
    # params to None, so everything the smoke needs must be passed in a single call).
    pkg.wire(registry=registry, var_dir=var_dir,
             _read=_read, _write=lambda p, d: _awj(p, d), _atomic_write_json=_awj)


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ok: {msg}")


# A mock LLM provider: echoes a deterministic payload, with a cost so metering is exercised.
def _mock_impl(payload_text):
    def _impl(rm, messages, opts):
        return {"text": payload_text, "cost_minor": 100, "usage": {"total_tokens": 42},
                "model": rm.litellm_model}
    return _impl


def main() -> None:
    if "droplet_work" not in ",".join(sys.path):
        sys.path.insert(0, str(_DROPLET))

    # 1) byte-compile + no caller import -------------------------------------------------------
    import py_compile
    mods = ["llm_gateway.py", "llm_copy.py", "creative_variants.py", "asset_bridge.py",
            "routes_llm.py"]
    for m in mods:
        py_compile.compile(str(_PKG / m), doraise=True)
    for m in mods:
        src = (_PKG / m).read_text(encoding="utf-8")
        # real import STATEMENTS only (prose like "No `from caller import ...`" is fine).
        bad = [ln for ln in src.splitlines()
               if ln.strip().startswith(("import caller", "from caller import"))]
        _assert(not bad,
                f"earner-safe: {m} has NO caller import statement (voice brain untouched)")

    from ads_engine import llm_gateway, llm_copy, creative_variants
    from ads_engine.asset_bridge import AssetBridge

    tmp = tempfile.mkdtemp(prefix="adsw4_")
    T = "tenant_w4_smoke"
    T2 = "tenant_w4_other"
    store = _FakeStore()
    _wire(store, tmp)

    # 2) fail-CLOSED: no def at all -> not_configured ------------------------------------------
    r0 = llm_gateway.resolve(T)
    _assert(r0.ok is False and r0.reason == "not_configured",
            "fail-closed: no reasoning_model def -> resolve not_configured")
    c0 = llm_gateway.complete(T, [{"role": "user", "content": "hi"}], complete_impl=_mock_impl("x"))
    _assert(c0["ok"] is False and c0["reason"] == "not_configured",
            "fail-closed: complete with no config -> not_configured (no spend)")

    # def exists but NO key in blob -> no_credential.
    store.add_definition(T, _FakeDef("def_reason", "reasoning_model", "reasoning-model",
                                     ["reasoning"]))
    store.upsert_credential(T, "def_reason", json.dumps({"provider": "openrouter", "model": "x"}))
    r_nokey = llm_gateway.resolve(T)
    _assert(r_nokey.ok is False and r_nokey.reason == "no_credential",
            "fail-closed: def + blob without api_key -> no_credential")

    # 3) config resolves -> provider/model selected, litellm model prefixed --------------------
    store.upsert_credential(T, "def_reason", json.dumps({
        "provider": "openrouter", "model": "deepseek/deepseek-chat",
        "api_key": "sk-or-test", "monthly_cap_minor": 0}))
    r1 = llm_gateway.resolve(T)
    _assert(r1.ok and r1.provider == "openrouter" and r1.model == "deepseek/deepseek-chat",
            "resolve: per-tenant config -> provider+model selected")
    _assert(r1.litellm_model == "openrouter/deepseek/deepseek-chat",
            "resolve: litellm model string is provider-prefixed")
    st = llm_gateway.status(T)
    _assert(st["configured"] is True and "api_key" not in json.dumps(st),
            "status: secret-free + configured")

    # 4) a call routes through the mock provider; cost metered ---------------------------------
    c1 = llm_gateway.complete(T, [{"role": "user", "content": "hi"}],
                              complete_impl=_mock_impl("hello"))
    _assert(c1["ok"] and c1["text"] == "hello" and c1["model"] == "deepseek/deepseek-chat",
            "route: mock provider call returns text via the selected model")
    _assert(c1["cost_minor"] == 100 and c1["month_spend_minor"] == 100,
            "meter: cost recorded into month-to-date spend")
    c2 = llm_gateway.complete(T, [{"role": "user", "content": "hi"}],
                              complete_impl=_mock_impl("again"))
    _assert(c2["month_spend_minor"] == 200, "meter: spend accumulates across calls")

    # 5) per-tenant monthly cap is fail-closed -------------------------------------------------
    store.upsert_credential(T, "def_reason", json.dumps({
        "provider": "openrouter", "model": "deepseek/deepseek-chat",
        "api_key": "sk-or-test", "monthly_cap_minor": 150}))  # below the 200 already spent
    called = {"n": 0}

    def _counting_impl(rm, messages, opts):
        called["n"] += 1
        return {"text": "should-not-run", "cost_minor": 100}
    c_cap = llm_gateway.complete(T, [{"role": "user", "content": "hi"}],
                                 complete_impl=_counting_impl)
    _assert(c_cap["ok"] is False and c_cap["reason"] == "cap_exceeded" and called["n"] == 0,
            "cap: spend>=cap -> cap_exceeded, provider NEVER called (fail-closed)")

    # 6) save_selection writes a new model -> next resolve picks it up (real-time) --------------
    sel = llm_gateway.save_selection(T, provider="groq", model="llama-3.3-70b-versatile",
                                     api_key="gsk-test", monthly_cap_minor=0)
    _assert(sel["ok"] is True, "select: save_selection writes the new config")
    r2 = llm_gateway.resolve(T)
    _assert(r2.provider == "groq" and r2.model == "llama-3.3-70b-versatile"
            and r2.litellm_model == "groq/llama-3.3-70b-versatile",
            "select: next resolve reflects the new model (no redeploy)")
    bad = llm_gateway.save_selection(T, provider="not-a-provider", model="x")
    _assert(bad["ok"] is False and bad["reason"] == "bad_provider",
            "select: an unknown provider is rejected, not stored")

    # 7) first LLM feature: ad-copy + brief-parse (mock) ---------------------------------------
    copy_json = json.dumps({"angles": [
        {"headline": "2BHK in Wakad", "primary_text": "Move-in ready homes",
         "description": "RERA P52100012345 approved", "rationale": "scarcity"},
        {"headline": "Wakad Launch", "primary_text": "Pre-launch prices",
         "description": "Book now", "rationale": "price"}]})
    copy = llm_copy.generate_ad_copy(T, {"product": "2BHK Wakad", "variants": 2,
                                         "rera_id": "P52100012345"},
                                     complete_impl=_mock_impl(copy_json))
    _assert(copy["ok"] and len(copy["angles"]) == 2
            and copy["angles"][0]["headline"] == "2BHK in Wakad",
            "copy: ad-copy generation returns structured angles (proposal-only)")

    brief_json = json.dumps({"product": "Skyline Towers", "headline": "Luxury 3BHK",
                             "language": "hinglish", "rera_id": "", "is_property": True})
    pb = llm_copy.parse_brief(T, {"id": "camp_42", "name": "Skyline Voice Campaign",
                                  "script": "luxury flats"},
                              complete_impl=_mock_impl(brief_json))
    _assert(pb["ok"] and pb["brief"]["product"] == "Skyline Towers"
            and pb["source_campaign_id"] == "camp_42",
            "brief: parse_brief returns an AdsBrief draft bound to source_campaign_id")

    # copy fail-closed when gateway not configured for another tenant.
    copy_nc = llm_copy.generate_ad_copy(T2, {"product": "X"}, complete_impl=_mock_impl("{}"))
    _assert(copy_nc["ok"] is False and copy_nc["reason"] == "not_configured",
            "copy: fail-closed when the tenant has no reasoning model configured")

    # 8) auto creative-variants THROUGH the moderation gate ------------------------------------
    from ads_engine import store as ads_store
    master = {
        "variant_id": "av_master", "tenant_id": T, "plan_id": "plan_1",
        "kind": "headline_image", "headline": "Premium 2BHK", "primary_text": "Live well",
        "description": "RERA P52100099999 approved homes", "rera_id": "P52100099999",
        "is_property": True, "ocr_text": "Premium 2BHK",
        "placements": [{"placement": "native_1x1", "size": "1080x1080", "aspect": "1:1",
                        "url": "https://cdn/x.png", "moderation_status": "pending"}],
        "moderation_status": "approved", "state": "ready", "created_at": 1,
    }
    ads_store.put_row(T, "ad_variants", "av_master", master)
    adapt = creative_variants.adapt_formats(None, T, "av_master")
    _assert(adapt["ok"] and adapt["moderation_status"] == "approved",
            "adapt: format adaptation passes the moderation gate (RERA present)")
    aspects = {p["aspect"] for p in adapt["placements"]}
    _assert({"1:1", "4:5", "9:16", "16:9"}.issubset(aspects),
            "adapt: all four orientation families produced")

    # a second static image so the slideshow has >=2 frames.
    master2 = dict(master, variant_id="av_master2",
                   placements=[{"placement": "native_1x1", "size": "1080x1080", "aspect": "1:1",
                                "url": "https://cdn/y.png", "moderation_status": "pending"}],
                   created_at=2)
    ads_store.put_row(T, "ad_variants", "av_master2", master2)
    show = creative_variants.build_slideshow(None, T, "plan_1",
                                             brief={"headline": "Premium 2BHK",
                                                    "rera_id": "P52100099999"})
    _assert(show["ok"] and len(show["slides"]) >= 2 and show["moderation_status"] == "approved",
            "slideshow: static->slideshow video built + moderated (deferred real-video)")

    # gate NOT bypassed: discriminatory copy is BLOCKED on the slideshow path.
    bad_master = dict(master, variant_id="av_bad", plan_id="plan_bad",
                      description="hindus only, no muslims", rera_id="P52100099999")
    ads_store.put_row(T, "ad_variants", "av_bad", bad_master)
    bad_adapt = creative_variants.adapt_formats(None, T, "av_bad")
    _assert(bad_adapt["ok"] and bad_adapt["moderation_status"] == "blocked",
            "gate: discriminatory copy is BLOCKED in format adaptation (moderation not bypassed)")

    # property creative with NO RERA id is blocked (legal must) even via the variant path.
    norera = dict(master, variant_id="av_norera", plan_id="plan_nr",
                  description="great homes", rera_id="")
    ads_store.put_row(T, "ad_variants", "av_norera", norera)
    nr = creative_variants.adapt_formats(None, T, "av_norera")
    _assert(nr["moderation_status"] == "blocked",
            "gate: property creative with no RERA id is blocked")

    # 9) asset bridge: mirror -> get round-trip + cross-tenant isolation ------------------------
    bridge = AssetBridge()
    row = bridge.mirror_asset(T, {"variant_id": "av_master", "platform": "meta_ads",
                                  "kind": "headline_image", "campaign_id": "plan_1",
                                  "headline": "Premium 2BHK", "moderation_status": "approved",
                                  "outputs": [{"url": "https://cdn/x.png"}]})
    _assert(row is not None and row["asset_id"] == "av_master",
            "bridge: mirror_asset stores an approved variant into the gallery")
    got = bridge.get_asset(T, "av_master")
    _assert(got is not None and got["url"] == "https://cdn/x.png",
            "bridge: get_asset round-trips the mirrored asset (tenant-scoped)")
    cross = bridge.get_asset(T2, "av_master")
    _assert(cross is None, "bridge: cross-tenant get_asset returns None (isolation)")

    print("\nV2-W4 LLM-gateway + creative-AI smoke: ALL GREEN")


if __name__ == "__main__":
    main()
