"""ads_engine.creative_variants — AUTO creative-variants: format adaptation + auto-slideshow.

From ONE master creative (a generated or uploaded ad variant) this derives:
  * FORMAT / ORIENTATION ADAPTATION — the same creative re-targeted to every placement family:
        feed 1:1 + portrait 4:5  ·  Stories/Reels 9:16  ·  landscape 16:9
    Missing families are filled from the master source with a per-family crop strategy; the
    compose-stage placements (Bannerbear multi_size) are reused when already present.
  * AUTO-SLIDESHOW VIDEO (static -> slideshow) — N approved static images stitched into a
    slideshow "video" spec (per-slide duration + transition), in 9:16 and 1:1. This is the
    DEFERRED-video path (founder decision #3): real AI image->video is added later once a
    permitted hosted model + per-clip budget is picked; veo-3.0 / gpt-image-1-mini stay
    EOL-blocked.

EVERYTHING goes THROUGH the moderation gate (RERA / Housing) before it can publish — adapted
variants and the slideshow are moderated identically to a generated variant; nothing reaches a
publishable state without passing. This module owns NO model key and NO spend authority; it
reuses the injected CreativeService for moderation + gallery mirror, and `store` for persistence.
Crash-proof + tenant-scoped; never raises into the tick or the live spine.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Optional

from . import store
from .creative import MOD_PENDING, default_moderation

# The four orientation families the ad engine adapts every master into (design brief 1:1/4:5/9:16/16:9).
ORIENTATION_FAMILIES = [
    {"family": "feed_square",    "placement": "meta_feed_1x1",        "size": "1080x1080", "aspect": "1:1",
     "crop": "center"},
    {"family": "feed_portrait",  "placement": "meta_portrait_4x5",    "size": "1080x1350", "aspect": "4:5",
     "crop": "center"},
    {"family": "story_reel",     "placement": "meta_story_9x16",      "size": "1080x1920", "aspect": "9:16",
     "crop": "smart_vertical"},
    {"family": "landscape",      "placement": "google_landscape_16x9", "size": "1200x675",  "aspect": "16:9",
     "crop": "smart_horizontal"},
]

# Slideshow defaults — deferred-real-video: a deterministic, on-brand static->slideshow build.
_SLIDE_MS = 2500
_TRANSITION = "crossfade"
_SLIDESHOW_ASPECTS = [
    {"placement": "reel_slideshow_9x16", "size": "1080x1920", "aspect": "9:16"},
    {"placement": "feed_slideshow_1x1",  "size": "1080x1080", "aspect": "1:1"},
]


def _now() -> int:
    return int(time.time())


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{hashlib.sha1(str(time.time_ns()).encode()).hexdigest()[:8]}"


def _master_source_url(variant: dict) -> str:
    """The best source image url on a variant (first placement with a url)."""
    for pl in (variant.get("placements") or []):
        if isinstance(pl, dict) and pl.get("url"):
            return str(pl["url"])
    return str(variant.get("url") or "")


def _existing_aspects(variant: dict) -> set:
    out = set()
    for pl in (variant.get("placements") or []):
        if isinstance(pl, dict) and pl.get("aspect"):
            out.add(str(pl["aspect"]))
    return out


def _carry_copy(variant: dict) -> dict:
    """Copy the moderation-relevant copy fields off the master (so RERA/Housing re-check is faithful)."""
    return {
        "headline": variant.get("headline", ""),
        "primary_text": variant.get("primary_text", ""),
        "description": variant.get("description", ""),
        "language": variant.get("language", "hinglish"),
        "rera_id": variant.get("rera_id", ""),
        "is_property": bool(variant.get("is_property", True)),
        "ocr_text": variant.get("ocr_text", variant.get("headline", "")),
    }


def _moderate_and_store(service: Any, tenant_id: str, variant: dict) -> dict:
    """Persist a freshly-built variant, run the publish gate, mirror on approve. Reuses the
    CreativeService when injected (its gate + gallery mirror); else uses default_moderation."""
    store.put_row(tenant_id, "ad_variants", variant["variant_id"], variant)
    if service is not None and hasattr(service, "moderate"):
        try:
            service.moderate(tenant_id, variant["variant_id"])
            return store.get_row(tenant_id, "ad_variants", variant["variant_id"]) or variant
        except Exception:  # noqa: BLE001 — fall through to inline gate (fail-closed)
            pass
    # Inline fallback: fail-closed (an error leaves moderation_status pending, never approved).
    try:
        result = default_moderation(variant, {})
        status = result.get("status", MOD_PENDING)
        checks = result.get("checks", {})
        reason = result.get("reason", "")
    except Exception:  # noqa: BLE001
        status, checks, reason = MOD_PENDING, {}, "moderation_error"
    variant["moderation_status"] = status
    variant["moderation"] = {"checks": checks, "reason": reason, "by": "auto", "ts": _now()}
    for pl in variant.get("placements", []):
        pl["moderation_status"] = status
    variant["state"] = "ready"
    store.put_row(tenant_id, "ad_variants", variant["variant_id"], variant)
    return variant


# ---------------------------------------------------------------------------
# FORMAT / ORIENTATION ADAPTATION.
# ---------------------------------------------------------------------------
def adapt_formats(service: Any, tenant_id: str, master_variant_id: str, *,
                  families: Optional[list] = None) -> dict:
    """Adapt a master variant into every orientation family, then moderate. PROPOSAL/asset-only.

    Returns { ok, variant_id, master_variant_id, placements:[...], moderation_status, reason }.
    Fail-closed: a master with no source url -> {ok:False, reason:"no_source"}. Tenant-scoped.
    """
    master = None
    try:
        master = store.get_row(tenant_id, "ad_variants", master_variant_id)
    except Exception:  # noqa: BLE001
        master = None
    if not isinstance(master, dict):
        return {"ok": False, "reason": "master_not_found", "master_variant_id": master_variant_id}

    src = _master_source_url(master)
    if not src:
        return {"ok": False, "reason": "no_source", "master_variant_id": master_variant_id}

    want = families if isinstance(families, list) and families else \
        [f["aspect"] for f in ORIENTATION_FAMILIES]
    have = _existing_aspects(master)

    placements = list(master.get("placements") or [])  # keep what the compose stage already made
    added = []
    for fam in ORIENTATION_FAMILIES:
        if fam["aspect"] not in want or fam["aspect"] in have:
            continue
        placements.append({
            "placement": fam["placement"], "size": fam["size"], "aspect": fam["aspect"],
            "url": src, "derived_from": master_variant_id, "crop": fam["crop"],
            "moderation_status": MOD_PENDING,
        })
        added.append(fam["aspect"])

    vid = _gen_id("av")
    variant = {
        "variant_id": vid, "tenant_id": tenant_id, "plan_id": master.get("plan_id"),
        "job_id": master.get("job_id", ""), "kind": "format_adaptation",
        "source_model": master.get("source_model", "adapt"),
        "master_variant_id": master_variant_id,
        "placements": placements, "moderation_status": MOD_PENDING, "moderation": {},
        "state": "moderating", "source": "adapted",
        "cost_minor": 0, "created_at": _now(), "updated_at": _now(),
        **_carry_copy(master),
    }
    out = _moderate_and_store(service, tenant_id, variant)
    return {
        "ok": True, "variant_id": vid, "master_variant_id": master_variant_id,
        "families_added": added, "placements": out.get("placements", []),
        "moderation_status": out.get("moderation_status"), "reason": "ok",
    }


# ---------------------------------------------------------------------------
# AUTO-SLIDESHOW VIDEO (static -> slideshow). Real AI image->video is DEFERRED.
# ---------------------------------------------------------------------------
def build_slideshow(service: Any, tenant_id: str, plan_id: str, *,
                    image_urls: Optional[list] = None, brief: Optional[dict] = None,
                    slide_ms: int = _SLIDE_MS, transition: str = _TRANSITION) -> dict:
    """Stitch N approved static images into a slideshow-video variant, then moderate.

    If `image_urls` is omitted, collects the approved static-image placements for the plan. Builds
    a deterministic slideshow spec (slides + per-slide duration + transition) in 9:16 and 1:1.
    Returns { ok, variant_id, slides, duration_ms, placements, moderation_status, reason }.
    Fail-closed: fewer than 2 images -> {ok:False, reason:"need_2_images"}.
    """
    b = dict(brief or {})
    urls = list(image_urls or [])
    if not urls:
        urls = _collect_plan_image_urls(tenant_id, plan_id)
    # dedupe preserving order
    seen, dedup = set(), []
    for u in urls:
        u = str(u or "")
        if u and u not in seen:
            seen.add(u)
            dedup.append(u)
    if len(dedup) < 2:
        return {"ok": False, "reason": "need_2_images", "plan_id": plan_id,
                "have": len(dedup)}

    slides = [{"index": i, "url": u, "duration_ms": int(slide_ms), "transition": transition}
              for i, u in enumerate(dedup)]
    total_ms = sum(s["duration_ms"] for s in slides)

    placements = [{
        "placement": a["placement"], "size": a["size"], "aspect": a["aspect"],
        "media_type": "slideshow_video", "slides": slides, "duration_ms": total_ms,
        "url": dedup[0],  # poster = first frame
        "moderation_status": MOD_PENDING,
    } for a in _SLIDESHOW_ASPECTS]

    vid = _gen_id("av")
    variant = {
        "variant_id": vid, "tenant_id": tenant_id, "plan_id": plan_id,
        "job_id": "", "kind": "slideshow_video", "source_model": "slideshow_builder",
        "media_type": "slideshow_video", "is_video": True,
        "headline": b.get("headline", ""), "primary_text": b.get("primary_text", ""),
        "description": b.get("description", ""), "language": b.get("language", "hinglish"),
        "rera_id": b.get("rera_id", ""), "is_property": bool(b.get("is_property", True)),
        "ocr_text": b.get("headline", ""),
        "placements": placements, "slides": slides, "duration_ms": total_ms,
        "moderation_status": MOD_PENDING, "moderation": {},
        "state": "moderating", "source": "slideshow",
        "cost_minor": 0, "created_at": _now(), "updated_at": _now(),
    }
    out = _moderate_and_store(service, tenant_id, variant)
    return {
        "ok": True, "variant_id": vid, "plan_id": plan_id,
        "slides": slides, "duration_ms": total_ms,
        "placements": out.get("placements", []),
        "moderation_status": out.get("moderation_status"), "reason": "ok",
    }


def _collect_plan_image_urls(tenant_id: str, plan_id: str) -> list:
    """Approved static-image urls across a plan's variants (newest-first), for the slideshow."""
    try:
        rows = list(store.get_collection(tenant_id, "ad_variants").values())
    except Exception:  # noqa: BLE001
        return []
    rows = [r for r in rows if r.get("plan_id") == plan_id
            and not r.get("is_video")
            and r.get("kind") not in ("slideshow_video",)]
    rows.sort(key=lambda r: int(r.get("created_at") or 0), reverse=True)
    urls = []
    for r in rows:
        # prefer approved variants; fall back to any with a url so a fresh plan can still slideshow.
        if r.get("moderation_status") == "blocked":
            continue
        for pl in (r.get("placements") or []):
            if isinstance(pl, dict) and pl.get("url"):
                urls.append(pl["url"])
                break
    return urls


__all__ = ["adapt_formats", "build_slideshow", "ORIENTATION_FAMILIES"]
