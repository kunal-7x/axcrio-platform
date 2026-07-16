"""ads_engine.creative — the CREATIVE FACTORY: brief -> approved, multi-placement ad assets.

This is the CREATIVE half of the ad engine (design/creative.md, binding). It turns a campaign
brief into moderation-passed ad creatives across ALL placements, OR adopts a vendor's own
upload — and NOTHING reaches `ready`/publish without passing the moderation gate.

THE JOB (async, advanced step-by-step):

    queued -> generating -> composing -> moderating -> ready
                       (any stage error) -> failed   (partial results kept)

`submit()` creates the `ads_jobs` row (queued) — the ONLY request-path write. Every long stage
is advanced by `advance()` (called from the scheduler tick, or run synchronously in tests). No
stage ever blocks a request thread, and a model/connector failure marks the STAGE failed — it
never raises into the tick or the live earner.

EARNER-SAFETY (design §11): pure service module. No caller.py / agent.py / voice edits. Keys
ONLY via the injected `get_secret_json` seam (vault_adapter). Every row is tenant-scoped through
`ads_engine.store` (the one isolation door). The direct-upload path REUSES the existing creative
gallery via the injected `asset_bridge` — it does not fork the gallery. EOL models are refused.

Dependencies are INJECTED (no `from caller import ...`):
  store          -> ads_engine.store (tenant-scoped accessors)
  get_secret_json-> callable(tenant_id, provider_def_id) -> dict|None (vault_adapter)
  resolve_def_id -> callable(tenant_id, model_id) -> provider_def_id|"" (vault def resolve)
  moderation     -> a check(variant, brand_kit) -> {status, checks, reason} callable (default below)
  asset_bridge   -> optional helper: mirror_asset(...) / get_asset(tenant_id, asset_id) (gallery reuse)
  http_factory   -> optional callable() -> httpx.AsyncClient (TESTS inject a mock-transport client)
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import creative_models, store

# Job + variant lifecycle vocab.
JOB_STATES = ("queued", "generating", "composing", "moderating", "ready", "failed")
MOD_PENDING, MOD_APPROVED, MOD_BLOCKED = "pending", "approved", "blocked"

# Default placement matrix: all four aspect families (design brief 1:1/4:5/9:16/16:9).
DEFAULT_PLACEMENTS = [
    {"placement": "meta_feed_1x1", "size": "1080x1080", "aspect": "1:1"},
    {"placement": "meta_portrait_4x5", "size": "1080x1350", "aspect": "4:5"},
    {"placement": "meta_story_9x16", "size": "1080x1920", "aspect": "9:16"},
    {"placement": "google_landscape_16x9", "size": "1200x675", "aspect": "16:9"},
]

# Per-target poll backoff schedule (seconds): 5s -> 30s -> 2m, cap 10 attempts (design §2).
_BACKOFF = [5, 5, 30, 30, 120]
_MAX_ATTEMPTS = 10


# ===========================================================================
# MODERATION GATE (Housing / RERA / brand / broken-text) — design §6.
# A variant is NOT publishable until status == "approved". Four checks, each
# pass|warn|fail. A `fail` -> blocked; a `warn` is allowed but surfaced. Fail-CLOSED:
# on any internal error the variant stays `pending` (NEVER auto-approved).
# ===========================================================================

# India real-estate discriminatory / banned copy terms (HEC-safe housing check). Non-exhaustive
# rule list (v1, no heavy ML); a hardened multimodal moderator is the deferred layer.
_HOUSING_BANNED = {
    "no muslims", "no muslim", "hindus only", "hindu only", "vegetarians only",
    "no bachelors", "family only", "no minorities", "upper caste", "brahmins only",
    "no christians", "muslims not allowed", "for hindus", "non-veg not allowed",
}
# RERA registration id format (state code letter prefix + digits). India RERA numbers vary; this
# is a permissive structural check (must look like a RERA id, not be empty).
_RERA_RE = re.compile(r"\b([A-Z]{1,3}\d{5,}|P\d{6,}|PRM/[A-Z]{2}/[A-Za-z0-9/]+)\b")

# Gibberish detector for broken generative text: a run with no vowels / mostly symbols.
_GIBBERISH_RE = re.compile(r"^[^aeiouAEIOU\s]{6,}$")


def _ratio(a: str, b: str) -> float:
    """Lightweight fuzzy similarity (no stdlib difflib dependency hardcode) in [0,1]."""
    try:
        import difflib
        return difflib.SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()
    except Exception:  # noqa: BLE001
        return 1.0 if (a or "").lower() == (b or "").lower() else 0.0


def default_moderation(variant: dict, brand_kit: Optional[dict] = None) -> dict:
    """The publish gate. Pure + offline. Returns {status, checks, reason}.

    status in {approved, blocked, pending}. A check that `fail`s blocks the variant; a `warn`
    keeps it approvable (surfaced to the approver). Property creatives MUST carry a RERA id and
    HEC-safe copy — a property ad with no RERA id is BLOCKED (legal must, design §6).
    """
    bk = brand_kit or {}
    checks: dict = {}
    reasons: list = []

    headline = str(variant.get("headline", "") or "")
    primary = str(variant.get("primary_text", "") or "")
    desc = str(variant.get("description", "") or "")
    blob = " ".join([headline, primary, desc]).lower()
    is_property = bool(variant.get("is_property", True))  # real-estate default for this product

    # 1) HOUSING — discriminatory copy is a hard fail (HEC).
    housing = "pass"
    for term in _HOUSING_BANNED:
        if term in blob:
            housing = "fail"
            reasons.append(f"housing: discriminatory term '{term}'")
            break
    checks["housing"] = housing

    # 2) RERA — a property ad MUST carry a valid-looking RERA registration id in the copy.
    rera = "pass"
    if is_property:
        rera_id = str(variant.get("rera_id", "") or "")
        present_in_copy = bool(_RERA_RE.search(desc.upper()) or _RERA_RE.search(blob.upper()))
        if not rera_id and not present_in_copy:
            rera = "fail"
            reasons.append("rera: no RERA registration id present (legal requirement)")
        elif rera_id and not _RERA_RE.search(rera_id.upper()):
            rera = "warn"
            reasons.append("rera: rera_id present but format looks off")
    checks["rera"] = rera

    # 3) BRAND — brand-kit do_not_use words must not appear.
    brand = "pass"
    dnu = ((bk.get("do_not_use") or {}).get("words")) or bk.get("banned_words") or []
    for w in dnu:
        if w and str(w).lower() in blob:
            brand = "fail"
            reasons.append(f"brand: do_not_use word '{w}'")
            break
    checks["brand"] = brand

    # 4) BROKEN_TEXT — compare requested headline vs the OCR'd/rendered text (fuzzy). v1 uses the
    # ocr_text the compose stage attached (stubbed to the requested headline when OCR absent).
    broken = "pass"
    if headline:
        ocr = str(variant.get("ocr_text", headline) or "")
        if _GIBBERISH_RE.match(ocr.strip()):
            broken = "fail"
            reasons.append("broken_text: rendered text is gibberish")
        elif _ratio(headline, ocr) < 0.8:
            broken = "warn"
            reasons.append("broken_text: rendered headline diverges from requested")
    checks["broken_text"] = broken

    if "fail" in checks.values():
        status = MOD_BLOCKED
    else:
        status = MOD_APPROVED
    return {"status": status, "checks": checks, "reason": "; ".join(reasons)}


# ===========================================================================
# Small helpers.
# ===========================================================================
def _now() -> int:
    return int(time.time())


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{hashlib.sha1(str(time.time_ns()).encode()).hexdigest()[:8]}"


def _idem_key(tenant_id: str, plan_id: str, brief: dict, kinds, sizes) -> str:
    raw = json.dumps(
        {"t": tenant_id, "p": plan_id, "b": brief, "k": sorted(kinds or []),
         "s": sorted(sizes or [])},
        sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def _aspect_for_size(size: str) -> str:
    try:
        w, h = (int(x) for x in str(size).split("x"))
        if w == h:
            return "1:1"
        r = w / h
        if abs(r - 0.8) < 0.05:
            return "4:5"
        if r < 0.7:
            return "9:16"
        return "16:9"
    except Exception:  # noqa: BLE001
        return "1:1"


# ===========================================================================
# THE SERVICE.
# ===========================================================================
@dataclass
class CreativeService:
    """Orchestrates the creative job machine, model adapters, composition + moderation gate.

    All deps injected; offline-safe. `advance(job)` is the single step function the tick calls
    (and tests call synchronously). `submit/import_upload/moderate/get_variants/list_jobs` are
    the request-path surface.
    """
    store_mod: Any = store
    get_secret_json: Optional[Callable[[str, str], Optional[dict]]] = None
    resolve_def_id: Optional[Callable[[str, str], str]] = None
    moderation: Callable[[dict, Optional[dict]], dict] = default_moderation
    asset_bridge: Any = None
    http_factory: Optional[Callable[[], Any]] = None
    sleep_fn: Optional[Callable] = None
    brand_kit_for: Optional[Callable[[str], dict]] = None
    # default model-override resolver per (tenant, kind) -> model id slug (per-tenant override).
    model_override_for: Optional[Callable[[str, str], str]] = None

    # -- model-adapter construction -----------------------------------------------------------
    def _build_adapter(self, tenant_id: str, kind: str):
        """Resolve + build the FIRST usable adapter for (tenant, kind), honoring a per-tenant
        override and refusing EOL models. Returns (model_id, adapter) or (None, None)."""
        override = ""
        if self.model_override_for is not None:
            try:
                override = self.model_override_for(tenant_id, kind) or ""
            except Exception:  # noqa: BLE001
                override = ""

        def _secret_closure_factory(model_id: str):
            def _get() -> Optional[dict]:
                if self.get_secret_json is None:
                    return None
                def_id = ""
                if self.resolve_def_id is not None:
                    try:
                        def_id = self.resolve_def_id(tenant_id, model_id) or ""
                    except Exception:  # noqa: BLE001
                        def_id = ""
                if not def_id:
                    return None
                try:
                    return self.get_secret_json(tenant_id, def_id)
                except Exception:  # noqa: BLE001
                    return None
            return _get

        http = None
        if self.http_factory is not None:
            try:
                http = self.http_factory()
            except Exception:  # noqa: BLE001
                http = None

        # resolve_model tries the chain; we bind the per-model secret closure lazily by passing a
        # factory through. Because resolve_model builds ONE adapter, bind for each candidate id.
        for mid in creative_models.resolve_chain(kind, override=override):
            builder = creative_models.get_model_class(mid)
            if builder is None:
                continue
            try:
                kw: dict = {
                    "get_secret_json": _secret_closure_factory(mid),
                    "provider_def_id": "via_resolver",
                    "http": http,
                }
                if self.sleep_fn is not None:
                    kw["sleep_fn"] = self.sleep_fn
                if mid in ("gemini-3-pro-image-preview", "gemini-2.5-flash-image",
                           "flux-2-max", "flux-2-pro"):
                    kw["model_id"] = mid
                return mid, builder(**kw)
            except Exception:  # noqa: BLE001
                continue
        return None, None

    # -- SUBMIT (request path) ----------------------------------------------------------------
    def submit(self, tenant_id: str, plan_id: str, brief: dict, *,
               models: Optional[dict] = None, sizes: Optional[list] = None,
               kinds: Optional[list] = None) -> dict:
        """Create a creative job (state=queued). The ONLY request-path write. Idempotent: a
        duplicate submit (same tenant|plan|brief|kinds|sizes) returns the existing job."""
        kinds = kinds or ["headline_image"]
        sizes = sizes or [p["size"] for p in DEFAULT_PLACEMENTS]
        idem = _idem_key(tenant_id, plan_id, brief or {}, kinds, sizes)

        # idempotency: scan existing jobs for the key.
        for j in self.store_mod.get_tenant_file(tenant_id, "ads_jobs"):
            if j.get("idem") == idem and j.get("state") not in ("failed",):
                return j

        job_id = _gen_id("cj")
        targets = []
        for kind in kinds:
            if kind == "multi_size":
                continue  # multi_size is the compose stage, derived from a generated source.
            mid = (models or {}).get(kind) or creative_models.MODEL_REGISTRY.get(kind, [""])[0]
            targets.append({
                "kind": kind, "model": mid, "capability": "image_gen",
                "state": "queued", "job_ref": "", "attempts": 0, "next_poll_ts": 0,
                "src_url": "", "src_b64": "", "cost_minor": 0,
            })
        # always add the multi_size compose target (advanced after a source lands).
        targets.append({
            "kind": "multi_size", "model": "bannerbear", "capability": "image_compose",
            "state": "queued", "job_ref": "", "attempts": 0, "next_poll_ts": 0,
            "sizes": list(sizes), "sizes_done": {}, "cost_minor": 0,
        })

        job = {
            "job_id": job_id, "tenant_id": tenant_id, "plan_id": plan_id, "idem": idem,
            "state": "queued", "brief": dict(brief or {}),
            "targets": targets, "variant_ids": [],
            "est_cost_minor": 0, "actual_cost_minor": 0, "error": None,
            "created_at": _now(), "updated_at": _now(),
        }
        job["est_cost_minor"] = self._estimate_cost(tenant_id, job)
        self._save_job(tenant_id, job)
        return job

    def _estimate_cost(self, tenant_id: str, job: dict) -> int:
        total = 0
        for t in job.get("targets", []):
            mid, adapter = self._build_adapter(tenant_id, t["kind"])
            if adapter is None:
                continue
            req = self._gen_request(t, job)
            try:
                total += int(adapter.cost_minor(req))
            except Exception:  # noqa: BLE001
                pass
        return total

    # -- the per-job step function (tick + tests) ---------------------------------------------
    async def advance(self, tenant_id: str, job: dict) -> dict:
        """Advance ONE job by exactly one logical stage. Returns the updated job row.

        Pure step-by-step machine: queued -> generating -> composing -> moderating -> ready.
        Never raises; a stage error marks the job (or a target) failed and keeps partial work.
        Call repeatedly (tick loop / test loop) until state in {ready, failed}.
        """
        try:
            state = job.get("state")
            if state == "queued":
                job["state"] = "generating"
            elif state == "generating":
                await self._stage_generating(tenant_id, job)
            elif state == "composing":
                await self._stage_composing(tenant_id, job)
            elif state == "moderating":
                self._stage_moderating(tenant_id, job)
            # ready / failed are terminal.
            job["updated_at"] = _now()
            self._save_job(tenant_id, job)
        except Exception as exc:  # noqa: BLE001 — a job error never escapes into the tick
            job["state"] = "failed"
            job["error"] = type(exc).__name__
            job["updated_at"] = _now()
            self._save_job(tenant_id, job)
        return job

    def advance_sync(self, tenant_id: str, job: dict) -> dict:
        """Synchronous driver for tests: run advance() to completion on a fresh loop."""
        import asyncio
        guard = 0
        while job.get("state") not in ("ready", "failed") and guard < 50:
            job = asyncio.run(self.advance(tenant_id, job))
            guard += 1
        return job

    # -- stage: GENERATING --------------------------------------------------------------------
    async def _stage_generating(self, tenant_id: str, job: dict) -> None:
        """Fire/poll each generation target. When all source targets are done -> composing."""
        now = _now()
        pending = False
        failed_all = True
        for t in job.get("targets", []):
            if t["kind"] == "multi_size":
                continue
            if t["state"] in ("done", "failed"):
                failed_all = failed_all and t["state"] == "failed"
                continue
            failed_all = False
            mid, adapter = self._build_adapter(tenant_id, t["kind"])
            if adapter is None:
                t["state"] = "failed"
                t["error"] = "not_configured"
                continue
            t["model"] = mid
            req = self._gen_request(t, job)
            if t["state"] == "queued":
                sub = await adapter.submit(req)
                t["attempts"] = int(t.get("attempts", 0)) + 1
                if not sub.ok:
                    t["error"] = sub.error
                    t["state"] = "failed"
                    continue
                t["cost_minor"] = int(sub.cost_minor or 0)
                if sub.inline:
                    t["src_url"] = sub.url
                    t["src_b64"] = sub.bytes_b64
                    t["state"] = "done"
                else:
                    t["job_ref"] = sub.job_ref
                    t["state"] = "polling"
                    t["next_poll_ts"] = now + _BACKOFF[0]
                    pending = True
            elif t["state"] == "polling":
                if now < int(t.get("next_poll_ts", 0)):
                    pending = True
                    continue
                pr = await adapter.poll(t["job_ref"], req)
                t["attempts"] = int(t.get("attempts", 0)) + 1
                if pr.state == "done":
                    t["src_url"] = pr.url
                    t["src_b64"] = pr.bytes_b64
                    t["cost_minor"] = int(pr.cost_minor or t.get("cost_minor", 0))
                    t["state"] = "done"
                elif pr.state == "failed" or t["attempts"] >= _MAX_ATTEMPTS:
                    t["error"] = pr.error or "max_attempts"
                    t["state"] = "failed"
                else:
                    idx = min(t["attempts"], len(_BACKOFF) - 1)
                    t["next_poll_ts"] = now + _BACKOFF[idx]
                    pending = True

        if pending:
            return  # stay in generating; the tick will re-enter after backoff.

        src_targets = [t for t in job["targets"] if t["kind"] != "multi_size"]
        if failed_all or all(t["state"] == "failed" for t in src_targets):
            job["state"] = "failed"
            job["error"] = "all_generation_targets_failed"
            return
        job["state"] = "composing"

    # -- stage: COMPOSING (Bannerbear -> all placements) --------------------------------------
    async def _stage_composing(self, tenant_id: str, job: dict) -> None:
        """Feed the first done source into Bannerbear -> every placement size. Then -> moderating."""
        now = _now()
        ms = next((t for t in job["targets"] if t["kind"] == "multi_size"), None)
        source = next((t for t in job["targets"]
                       if t["kind"] != "multi_size" and t["state"] == "done"), None)
        if ms is None or source is None:
            # nothing to compose; build variants straight from the source(s) at native size.
            self._build_variants_from_sources(tenant_id, job)
            job["state"] = "moderating"
            return

        _mid, adapter = self._build_adapter(tenant_id, "multi_size")
        if adapter is None:
            # compose unavailable -> degrade to native-size variant only (still moderated).
            self._build_variants_from_sources(tenant_id, job)
            job["state"] = "moderating"
            return

        req = creative_models.GenRequest(
            kind="multi_size",
            headline=job.get("brief", {}).get("headline", ""),
            source_url=source.get("src_url", ""),
            sizes=ms.get("sizes", []),
            template_set=job.get("brief", {}).get("template_set", "ts_real_estate_v1"),
        )
        if ms["state"] in ("queued", ""):
            sub = await adapter.submit(req)
            ms["attempts"] = int(ms.get("attempts", 0)) + 1
            if not sub.ok:
                ms["error"] = sub.error
                # degrade gracefully to native-size variant.
                self._build_variants_from_sources(tenant_id, job)
                job["state"] = "moderating"
                return
            ms["job_ref"] = sub.job_ref
            ms["cost_minor"] = int(sub.cost_minor or 0)
            ms["state"] = "polling"
            ms["next_poll_ts"] = now + _BACKOFF[0]
            return
        if ms["state"] == "polling":
            if now < int(ms.get("next_poll_ts", 0)):
                return
            pr = await adapter.poll(ms["job_ref"], req)
            ms["attempts"] = int(ms.get("attempts", 0)) + 1
            if pr.state == "done":
                ms["sizes_done"] = pr.sizes
                ms["cost_minor"] = int(pr.cost_minor or ms.get("cost_minor", 0))
                ms["state"] = "done"
                self._build_variant_from_compose(tenant_id, job, source, pr.sizes)
                job["state"] = "moderating"
            elif pr.state == "failed" or ms["attempts"] >= _MAX_ATTEMPTS:
                ms["error"] = pr.error or "max_attempts"
                self._build_variants_from_sources(tenant_id, job)
                job["state"] = "moderating"
            else:
                idx = min(ms["attempts"], len(_BACKOFF) - 1)
                ms["next_poll_ts"] = now + _BACKOFF[idx]

    # -- stage: MODERATING (the publish gate) -------------------------------------------------
    def _stage_moderating(self, tenant_id: str, job: dict) -> None:
        """Run the moderation gate on every variant; mirror approved ones into the gallery.
        Then -> ready. Fail-CLOSED: a moderation error leaves the variant pending (not approved)."""
        brand_kit = self._brand_kit(tenant_id)
        all_costs = sum(int(t.get("cost_minor", 0)) for t in job.get("targets", []))
        for vid in job.get("variant_ids", []):
            variant = self.store_mod.get_row(tenant_id, "ad_variants", vid)
            if not variant:
                continue
            self._moderate_variant(tenant_id, variant, brand_kit)
        job["actual_cost_minor"] = all_costs
        job["state"] = "ready"

    def _moderate_variant(self, tenant_id: str, variant: dict, brand_kit: dict) -> dict:
        try:
            result = self.moderation(variant, brand_kit)
            status = result.get("status", MOD_PENDING)
        except Exception:  # noqa: BLE001 — fail-CLOSED: never auto-approve on a gate error
            result = {"status": MOD_PENDING, "checks": {}, "reason": "moderation_error"}
            status = MOD_PENDING
        variant["moderation_status"] = status
        variant["moderation"] = {
            "checks": result.get("checks", {}), "reason": result.get("reason", ""),
            "by": "auto", "ts": _now(),
        }
        # propagate per-placement moderation status.
        for pl in variant.get("placements", []):
            pl["moderation_status"] = status
        variant["state"] = "ready"
        self.store_mod.put_row(tenant_id, "ad_variants", variant["variant_id"], variant)
        if status == MOD_APPROVED:
            self._mirror_to_gallery(tenant_id, variant)
        return variant

    # -- variant builders ---------------------------------------------------------------------
    def _gen_request(self, target: dict, job: dict) -> "creative_models.GenRequest":
        brief = job.get("brief", {})
        return creative_models.GenRequest(
            kind=target["kind"],
            prompt=brief.get("prompt", "") or brief.get("product", ""),
            headline=brief.get("headline", ""),
            width=int(brief.get("width", 1080)),
            height=int(brief.get("height", 1080)),
            n=int(brief.get("variants", 1)),
            aspect=brief.get("aspect", "1:1"),
        )

    def _new_variant(self, tenant_id: str, job: dict, kind: str, model: str) -> dict:
        brief = job.get("brief", {})
        vid = _gen_id("av")
        variant = {
            "variant_id": vid, "tenant_id": tenant_id, "plan_id": job.get("plan_id"),
            "job_id": job.get("job_id"), "kind": kind, "source_model": model,
            "headline": brief.get("headline", ""),
            "primary_text": brief.get("primary_text", ""),
            "description": brief.get("description", ""),
            "language": brief.get("language", "hinglish"),
            "rera_id": brief.get("rera_id", ""),
            "is_property": bool(brief.get("is_property", True)),
            "ocr_text": brief.get("headline", ""),  # v1 stub: requested == rendered until real OCR
            "placements": [], "moderation_status": MOD_PENDING, "moderation": {},
            "state": "moderating", "source": "generated",
            "cost_minor": 0, "created_at": _now(), "updated_at": _now(),
        }
        return variant

    def _build_variant_from_compose(self, tenant_id: str, job: dict, source: dict,
                                    sizes: dict) -> None:
        variant = self._new_variant(tenant_id, job, source["kind"], source.get("model", ""))
        for name, url in (sizes or {}).items():
            size_label = name if "x" in str(name) else "1080x1080"
            variant["placements"].append({
                "placement": name, "size": size_label, "aspect": _aspect_for_size(size_label),
                "url": url, "moderation_status": MOD_PENDING,
            })
        self.store_mod.put_row(tenant_id, "ad_variants", variant["variant_id"], variant)
        job.setdefault("variant_ids", []).append(variant["variant_id"])

    def _build_variants_from_sources(self, tenant_id: str, job: dict) -> None:
        """Fallback when compose is unavailable: one variant per done source at native size."""
        for t in job.get("targets", []):
            if t["kind"] == "multi_size" or t.get("state") != "done":
                continue
            if not (t.get("src_url") or t.get("src_b64")):
                continue
            variant = self._new_variant(tenant_id, job, t["kind"], t.get("model", ""))
            variant["placements"].append({
                "placement": "native_1x1", "size": "1080x1080", "aspect": "1:1",
                "url": t.get("src_url", ""), "bytes_b64": t.get("src_b64", ""),
                "moderation_status": MOD_PENDING,
            })
            self.store_mod.put_row(tenant_id, "ad_variants", variant["variant_id"], variant)
            job.setdefault("variant_ids", []).append(variant["variant_id"])

    # -- DIRECT-UPLOAD path (vendor brings their own image/video) — design §7 -----------------
    def import_upload(self, tenant_id: str, plan_id: str, asset_id: str, *,
                      kind: str = "uploaded_image", brief: Optional[dict] = None) -> dict:
        """Adopt an existing creative-gallery asset as an ad variant (REUSE, no new upload code).

        Verifies tenant ownership via the asset_bridge, creates a `source:"uploaded"` variant
        linked to the gallery asset, and runs the SAME moderation gate (RERA/Housing still apply!).
        Returns the stored variant row.
        """
        asset = self._get_gallery_asset(tenant_id, asset_id)
        if asset is None:
            return {"ok": False, "error": "asset_not_found_or_cross_tenant"}

        b = dict(brief or {})
        vid = _gen_id("av")
        url = asset.get("url") or asset.get("output_url") or ""
        variant = {
            "variant_id": vid, "tenant_id": tenant_id, "plan_id": plan_id,
            "job_id": "", "kind": kind, "source_model": "upload",
            "asset_id": asset_id, "gallery_asset_id": asset_id,
            "headline": b.get("headline", asset.get("headline", "")),
            "primary_text": b.get("primary_text", ""),
            "description": b.get("description", ""),
            "language": b.get("language", "hinglish"),
            "rera_id": b.get("rera_id", ""),
            "is_property": bool(b.get("is_property", True)),
            "ocr_text": b.get("headline", asset.get("headline", "")),
            "placements": [{
                "placement": "upload_native", "size": b.get("size", "1080x1080"),
                "aspect": _aspect_for_size(b.get("size", "1080x1080")),
                "url": url, "moderation_status": MOD_PENDING,
            }],
            "moderation_status": MOD_PENDING, "moderation": {},
            "state": "moderating", "source": "uploaded",
            "cost_minor": 0, "created_at": _now(), "updated_at": _now(),
        }
        self.store_mod.put_row(tenant_id, "ad_variants", vid, variant)
        # run the publish gate immediately (uploaded creatives are moderated identically).
        return self._moderate_variant(tenant_id, variant, self._brand_kit(tenant_id))

    # -- re-run moderation (after an edit) ----------------------------------------------------
    def moderate(self, tenant_id: str, variant_id: str) -> dict:
        """Re-run the publish gate on one variant (after a copy edit / regenerate)."""
        variant = self.store_mod.get_row(tenant_id, "ad_variants", variant_id)
        if not variant:
            return {"ok": False, "error": "not_found"}
        v = self._moderate_variant(tenant_id, variant, self._brand_kit(tenant_id))
        return {"ok": True, "status": v.get("moderation_status"),
                "checks": v.get("moderation", {}).get("checks", {})}

    # -- read-side ----------------------------------------------------------------------------
    def list_jobs(self, tenant_id: str, *, plan_id: Optional[str] = None) -> list:
        rows = self.store_mod.get_tenant_file(tenant_id, "ads_jobs")
        if plan_id is not None:
            rows = [r for r in rows if r.get("plan_id") == plan_id]
        return rows

    def get_job(self, tenant_id: str, job_id: str) -> Optional[dict]:
        for r in self.store_mod.get_tenant_file(tenant_id, "ads_jobs"):
            if r.get("job_id") == job_id:
                return r
        return None

    def get_variants(self, tenant_id: str, plan_id: str) -> list:
        rows = self.store_mod.get_collection(tenant_id, "ad_variants").values()
        return [r for r in rows if r.get("plan_id") == plan_id]

    def list_variants(self, tenant_id: str, *, plan_id: Optional[str] = None,
                      moderation_status: Optional[str] = None) -> list:
        """Tenant-wide variant list for the moderation feed (BLINDSPOTS B5). Optional plan +
        moderation_status filters. Returns the stored variant rows (tenant-scoped by the store)."""
        rows = list(self.store_mod.get_collection(tenant_id, "ad_variants").values())
        if plan_id is not None:
            rows = [r for r in rows if r.get("plan_id") == plan_id]
        if moderation_status is not None:
            rows = [r for r in rows if r.get("moderation_status") == moderation_status]
        return rows

    def set_moderation(self, tenant_id: str, variant_id: str, decision: str, *,
                       by: str = "human") -> dict:
        """Apply a HUMAN moderation verdict to one variant (BLINDSPOTS B5 — the moderation feed's
        approve/block buttons). `decision` ∈ {approved, blocked}. An approved variant is mirrored
        into the gallery; the per-placement status is propagated. Fail-safe: an unknown decision is
        rejected (no silent auto-approve)."""
        decision = str(decision or "").lower()
        if decision not in (MOD_APPROVED, MOD_BLOCKED):
            return {"ok": False, "error": "bad_decision"}
        variant = self.store_mod.get_row(tenant_id, "ad_variants", variant_id)
        if not variant:
            return {"ok": False, "error": "not_found"}
        variant["moderation_status"] = decision
        prior = variant.get("moderation") if isinstance(variant.get("moderation"), dict) else {}
        variant["moderation"] = {
            "checks": prior.get("checks", {}),
            "reason": prior.get("reason", ""),
            "by": by, "decision": decision, "ts": _now(),
        }
        for pl in variant.get("placements", []):
            pl["moderation_status"] = decision
        variant["state"] = "ready"
        variant["updated_at"] = _now()
        self.store_mod.put_row(tenant_id, "ad_variants", variant["variant_id"], variant)
        if decision == MOD_APPROVED:
            self._mirror_to_gallery(tenant_id, variant)
        return {"ok": True, "variant_id": variant_id, "moderation_status": decision}

    async def tick(self, now_ts: Optional[float] = None) -> None:
        """Advance every in-flight job for every tenant by one stage (called by ads_engine.tick)."""
        for tenant_id in self.store_mod.list_tenant_ids("campaigns") or []:
            try:
                jobs = self.store_mod.get_tenant_file(tenant_id, "ads_jobs")
            except Exception:  # noqa: BLE001
                continue
            for job in jobs:
                if job.get("state") in ("ready", "failed"):
                    continue
                await self.advance(tenant_id, job)

    # -- persistence + bridges ----------------------------------------------------------------
    def _save_job(self, tenant_id: str, job: dict) -> None:
        rows = self.store_mod.get_tenant_file(tenant_id, "ads_jobs")
        replaced = False
        for i, r in enumerate(rows):
            if r.get("job_id") == job.get("job_id"):
                rows[i] = job
                replaced = True
                break
        if not replaced:
            rows.append(job)
        self.store_mod.put_tenant_file(tenant_id, "ads_jobs", rows)

    def _brand_kit(self, tenant_id: str) -> dict:
        if self.brand_kit_for is not None:
            try:
                return self.brand_kit_for(tenant_id) or {}
            except Exception:  # noqa: BLE001
                return {}
        return {}

    def _get_gallery_asset(self, tenant_id: str, asset_id: str) -> Optional[dict]:
        """Tenant-scoped fetch of a gallery asset via the bridge (cross-tenant -> None)."""
        if self.asset_bridge is None:
            return None
        fn = getattr(self.asset_bridge, "get_asset", None)
        if fn is None:
            return None
        try:
            return fn(tenant_id, asset_id)
        except Exception:  # noqa: BLE001
            return None

    def _mirror_to_gallery(self, tenant_id: str, variant: dict) -> None:
        """Best-effort mirror of an approved variant into the Creative Studio gallery (design §5).
        Dormant-safe: if the asset service is absent, this is a no-op (ad_variants stays truth)."""
        if self.asset_bridge is None:
            return
        fn = getattr(self.asset_bridge, "mirror_asset", None)
        if fn is None:
            return
        try:
            fn(tenant_id, {
                "source": "generated", "platform": "meta_ads",
                "kind": variant.get("kind"), "campaign_id": variant.get("plan_id"),
                "headline": variant.get("headline"),
                "moderation_status": variant.get("moderation_status"),
                "outputs": variant.get("placements", []),
                "variant_id": variant.get("variant_id"),
            })
        except Exception:  # noqa: BLE001 — mirror is best-effort, never blocks ready.
            pass


__all__ = [
    "CreativeService", "default_moderation",
    "JOB_STATES", "MOD_PENDING", "MOD_APPROVED", "MOD_BLOCKED", "DEFAULT_PLACEMENTS",
]
