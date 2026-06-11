"""whatsapp_builder — AI WhatsApp template-generation brain (PUBLIC API).

Two-layer: the LLM PROPOSES, the deterministic Meta-compliance validator is the
AUTHORITY. Dormant-until-creds, offline-testable, one money path (wallet.py),
FORCE-RLS ai_wa_* schema, immutable audit (channel="whatsapp_builder").

This module is the LIBRARY surface. The HTTP routes live in router.py (a
token-deriving build_router the orchestrator mounts behind FEATURE_WHATSAPP_BUILDER).
The same generation is also registered ONCE as the `whatsapp.generate_templates`
ToolSpec for the AI-Manager / Workflow nodes (orchestrator-wired).
"""
from __future__ import annotations
from typing import Any, Optional

from . import config, store, validate as V, personalize as P
from . import generate as _gen, meta_submit, audit_hook

__all__ = [
    "generate_templates", "list_templates", "get_template", "select_variation",
    "regenerate", "approve", "reject", "submit_to_meta", "attach_banner",
    "meta_status", "status", "ensure_schema",
]


def ensure_schema() -> bool:
    return store.ensure_schema()


# ── generate ───────────────────────────────────────────────────────────────────
def generate_templates(tenant_id: str, campaign_id: str, spec: Optional[dict] = None,
                       performance_summary: Optional[dict] = None,
                       is_admin: bool = False) -> dict:
    return _gen.generate_templates(tenant_id, campaign_id, spec,
                                   performance_summary=performance_summary, is_admin=is_admin)


def regenerate(tenant_id: str, template_id: str, mode: str = "more_like_this",
               n: int = 3, is_admin: bool = False) -> dict:
    """New set in a given mode; originals are kept (versioned by new bundle)."""
    tpl = store.get("ai_wa_templates", tenant_id, template_id, is_admin)
    if not tpl:
        return {"status": "error", "error": "not_found"}
    spec = {"n": n, "mode": mode, "language": tpl.get("language", "en"),
            "angles": [] if mode != "new_angle" else []}
    return _gen.generate_templates(tenant_id, tpl["campaign_id"], spec, is_admin=is_admin)


# ── reads ──────────────────────────────────────────────────────────────────────
def list_templates(tenant_id: str, campaign_id: str, status_filter: str = "",
                   angle: str = "", limit: int = 50, offset: int = 0,
                   is_admin: bool = False) -> dict:
    where: dict[str, Any] = {"campaign_id": campaign_id}
    if status_filter:
        where["status"] = status_filter
    if angle:
        where["angle"] = angle
    rows = store.list_rows("ai_wa_templates", tenant_id, where, limit, offset, is_admin)
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset}


def get_template(tenant_id: str, template_id: str, is_admin: bool = False) -> Optional[dict]:
    tpl = store.get("ai_wa_templates", tenant_id, template_id, is_admin)
    if not tpl:
        return None
    variations = store.list_rows("ai_wa_variations", tenant_id, {"template_id": template_id},
                                 limit=50, is_admin=is_admin)
    plan = store.list_rows("ai_wa_personalization", tenant_id, {"template_id": template_id},
                           limit=50, is_admin=is_admin)
    body_text = (tpl.get("body") or {}).get("text", "")
    return {**tpl, "variations": variations, "personalization": plan,
            "sample_render": P.sample_render(body_text, plan)}


# ── mutators ───────────────────────────────────────────────────────────────────
def select_variation(tenant_id: str, template_id: str, variation_id: str,
                     is_admin: bool = False) -> dict:
    tpl = store.get("ai_wa_templates", tenant_id, template_id, is_admin)
    if not tpl:
        return {"status": "error", "error": "not_found"}
    var = store.get("ai_wa_variations", tenant_id, variation_id, is_admin)
    if not var or var.get("template_id") != template_id:
        return {"status": "error", "error": "variation_not_found"}
    body = dict(tpl.get("body") or {})
    body["text"] = var.get("body_text", body.get("text", ""))
    store.update("ai_wa_templates", tenant_id, template_id,
                 {"selected_variation_id": variation_id, "body": body}, is_admin)
    audit_hook.record(tenant_id, "select", template_id, meta={"variation_id": variation_id})
    return get_template(tenant_id, template_id, is_admin)


def approve(tenant_id: str, template_id: str, is_admin: bool = False) -> dict:
    """The gate: only a Meta-valid, non-fabricated template may leave the builder."""
    tpl = store.get("ai_wa_templates", tenant_id, template_id, is_admin)
    if not tpl:
        return {"status": "error", "error": "not_found"}
    ok, why = V.can_approve(tpl)
    if not ok:
        audit_hook.record(tenant_id, "approve_refused", template_id, meta={"reason": why})
        return {**tpl, "status": "refused", "error": why}
    store.update("ai_wa_templates", tenant_id, template_id, {"status": "approved"}, is_admin)
    audit_hook.record(tenant_id, "approve", template_id, meta={"category": tpl.get("category")})
    return {**tpl, "status": "approved"}


def reject(tenant_id: str, template_id: str, reason: str = "", is_admin: bool = False) -> dict:
    tpl = store.get("ai_wa_templates", tenant_id, template_id, is_admin)
    if not tpl:
        return {"status": "error", "error": "not_found"}
    store.update("ai_wa_templates", tenant_id, template_id, {"status": "rejected"}, is_admin)
    audit_hook.record(tenant_id, "reject", template_id,
                      meta={"reason": reason, "angle": tpl.get("angle")})
    return {**tpl, "status": "rejected"}


def attach_banner(tenant_id: str, template_id: str, asset_id: str, is_admin: bool = False) -> dict:
    """Bind an APPROVED Creative-Studio asset as the header media. Tenant-checked.
    Banners are NEVER generated here; this only references an approved AssetRef."""
    tpl = store.get("ai_wa_templates", tenant_id, template_id, is_admin)
    if not tpl:
        return {"status": "error", "error": "not_found"}
    asset = _resolve_asset(tenant_id, asset_id)
    if asset is None:
        audit_hook.record(tenant_id, "attach_refused", template_id, meta={"asset_id": asset_id})
        return {**tpl, "status": "refused", "error": "asset_not_found_or_cross_tenant"}
    if asset.get("tenant_id") not in (tenant_id, None) and not is_admin:
        return {**tpl, "status": "refused", "error": "cross_tenant_asset"}
    if (asset.get("status") or "").lower() not in ("approved", "ready", ""):
        return {**tpl, "status": "refused", "error": "asset_not_approved"}
    header = dict(tpl.get("header") or {})
    header["format"] = "IMAGE"
    store.update("ai_wa_templates", tenant_id, template_id,
                 {"attached_asset_id": asset_id, "header": header}, is_admin)
    audit_hook.record(tenant_id, "attach", template_id, meta={"asset_id": asset_id})
    return {**tpl, "attached_asset_id": asset_id, "header": header}


# pluggable asset resolver (the offline test injects a fake; live uses creative.*)
_ASSET_RESOLVER = None


def set_asset_resolver(fn) -> None:
    global _ASSET_RESOLVER
    _ASSET_RESOLVER = fn


def _resolve_asset(tenant_id: str, asset_id: str) -> Optional[dict]:
    if _ASSET_RESOLVER is not None:
        try:
            return _ASSET_RESOLVER(tenant_id, asset_id)
        except Exception:
            return None
    # live: the creative.* contract (tenant-checked). Absent -> None (dormant).
    try:
        import creative  # type: ignore
        return creative.get(tenant_id, asset_id)  # type: ignore
    except Exception:
        return None


# ── Meta submit (dormant) ──────────────────────────────────────────────────────
def submit_to_meta(tenant_id: str, template_id: str, is_admin: bool = False) -> dict:
    tpl = store.get("ai_wa_templates", tenant_id, template_id, is_admin)
    if not tpl:
        return {"status": "error", "error": "not_found"}
    if tpl.get("status") != "approved":
        return {"status": "refused", "error": "template_not_approved"}
    plan = store.list_rows("ai_wa_personalization", tenant_id, {"template_id": template_id},
                           limit=50, is_admin=is_admin)
    # Media header: a banner needs a Meta header_handle (from the Resumable Upload
    # API) for example.header_handle — an empty handle is rejected. Resolve the banner
    # bytes from the attached Creative asset's URL (stored to Spaces for provenance),
    # run the resumable upload, and inject _header_handle. Never raises; on any failure
    # the submit proceeds with no media example (and Meta returns a clear error).
    header = tpl.get("header") or {}
    if header.get("format") in ("IMAGE", "VIDEO", "DOCUMENT") and not tpl.get("_header_handle"):
        src = (header.get("url") or "").strip()
        if not src:
            asset = _resolve_asset(tenant_id, tpl.get("attached_asset_id") or "")
            if isinstance(asset, dict):
                src = (asset.get("url") or asset.get("preview_url") or "").strip()
        if src:
            up = meta_submit.resolve_header_handle_from_src(src)
            if up.get("handle"):
                tpl = {**tpl, "_header_handle": up["handle"]}
    res = meta_submit.submit(tpl, plan)
    patch: dict[str, Any] = {}
    if res.get("status") == "submitted":
        patch = {"status": "submitted", "meta_template_id": res.get("meta_template_id", ""),
                 "meta_review": res.get("review_status", "PENDING")}
        store.update("ai_wa_templates", tenant_id, template_id, patch, is_admin)
    audit_hook.record(tenant_id, "submit", template_id, meta={"result": res.get("status")})
    return res


def meta_status(tenant_id: str, template_id: str, is_admin: bool = False) -> dict:
    tpl = store.get("ai_wa_templates", tenant_id, template_id, is_admin)
    if not tpl:
        return {"status": "error", "error": "not_found"}
    if not config.meta_ready():
        return {"review_status": tpl.get("meta_review", ""), "rejection_reason": "",
                "status": "not_configured"}
    return {"review_status": tpl.get("meta_review", "PENDING"), "rejection_reason": ""}


# ── status ─────────────────────────────────────────────────────────────────────
def status() -> dict:
    from . import llm as llm_mod
    return {
        "llm": llm_mod.status(),
        "whatsapp": "ready" if config.meta_ready() else "not_configured",
        "meta_submit": "ready" if config.meta_ready() else "not_configured",
        "credits_required": True,
        "require_approval": config.require_approval(),
        "feature_enabled": config.feature_enabled(),
    }
