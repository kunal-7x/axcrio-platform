"""whatsapp_builder.meta_submit — DORMANT submit-to-Meta seam.

Builds the correct POST /{waba_id}/message_templates body shape and (only when creds
are present) submits an APPROVED template for Meta's review. No creds -> returns
{status:"not_configured"} and touches NO network. Never raises.
"""
from __future__ import annotations
from typing import Any

from . import config


def to_meta_payload(tpl: dict, personalization: list[dict] | None = None) -> dict:
    """Translate an ai_wa_templates row into the Meta message_templates create body."""
    components: list[dict] = []
    header = tpl.get("header") or {}
    if header.get("format") == "TEXT" and header.get("text"):
        comp: dict[str, Any] = {"type": "HEADER", "format": "TEXT", "text": header["text"]}
        components.append(comp)
    elif header.get("format") in ("IMAGE", "VIDEO", "DOCUMENT"):
        # media header. Meta's message_templates CREATE accepts an
        # example.header_handle produced by the Resumable Upload API. (example.header_url
        # is NOT reliably accepted here — it 500s — so the handle is the supported path.)
        # submit_to_meta resolves the banner bytes -> Spaces -> resumable upload and
        # injects ``_header_handle``. header_url is kept ONLY as a last-resort fallback.
        handle = (tpl.get("_header_handle") or "").strip()
        if handle:
            components.append({"type": "HEADER", "format": header["format"],
                               "example": {"header_handle": [handle]}})
        elif (tpl.get("_header_url") or header.get("url") or "").strip():
            components.append({"type": "HEADER", "format": header["format"],
                               "example": {"header_url": [(tpl.get("_header_url") or header.get("url")).strip()]}})
        else:
            components.append({"type": "HEADER", "format": header["format"],
                               "example": {"header_handle": [""]}})

    body = tpl.get("body") or {}
    body_comp: dict[str, Any] = {"type": "BODY", "text": body.get("text", "")}
    examples = body.get("example") or []
    if examples:
        body_comp["example"] = {"body_text": [examples]}
    components.append(body_comp)

    footer = tpl.get("footer") or {}
    if footer.get("text"):
        components.append({"type": "FOOTER", "text": footer["text"]})

    buttons = tpl.get("buttons") or []
    if buttons:
        btns = []
        for b in buttons:
            bt = (b.get("type") or "").upper()
            if bt == "URL":
                btns.append({"type": "URL", "text": b.get("text", ""), "url": b.get("url", "")})
            elif bt == "PHONE_NUMBER":
                btns.append({"type": "PHONE_NUMBER", "text": b.get("text", ""),
                             "phone_number": b.get("phone", "")})
            elif bt == "COPY_CODE":
                btns.append({"type": "COPY_CODE", "example": b.get("text", "")})
            else:
                btns.append({"type": "QUICK_REPLY", "text": b.get("text", "")})
        components.append({"type": "BUTTONS", "buttons": btns})

    return {
        "name": tpl.get("name", ""),
        "language": tpl.get("language", "en"),
        "category": tpl.get("category", "MARKETING"),
        "components": components,
    }


_EXT_BY_CTYPE = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
                 "video/mp4": "mp4", "application/pdf": "pdf"}


def _spaces_put_bytes(data: bytes, content_type: str) -> dict:
    """Persist banner bytes to DO Spaces (provenance / re-use). Reuses the shared
    media_gen.spaces boto3 client/creds. Uploads WITHOUT an object ACL because the
    live ``capsy-recordings`` bucket has object-ACLs disabled (``public-read`` raises
    UnsupportedAclConfigurationException). Returns ``{"ok","key","status"}``. Never
    raises; Spaces is optional — the Meta handle (below) is what actually matters."""
    try:
        from media_gen import spaces
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "key": "", "status": f"error:spaces_import:{type(e).__name__}"}
    cli = spaces._client()
    if cli is None:
        return {"ok": False, "key": "", "status": "not_configured"}
    import os
    import uuid
    bucket = (os.getenv("SPACES_BUCKET") or "").strip()
    ext = _EXT_BY_CTYPE.get(content_type, "bin")
    key = f"wa_template_headers/{uuid.uuid4().hex}.{ext}"
    try:
        cli.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
        return {"ok": True, "key": key, "status": "stored"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "key": "", "status": f"error:put:{type(exc).__name__}"}


def _resumable_upload_handle(data: bytes, content_type: str) -> dict:
    """Run Meta's Resumable Upload API and return ``{"ok","handle","status"}``.

    This is the SUPPORTED mechanism for a media template header: start a session at
    POST /{app_id}/uploads, stream the bytes, get back ``{"h": <handle>}``, then put
    that handle into example.header_handle. (example.header_url is NOT accepted by the
    message_templates CREATE endpoint — it 500s.) Never raises; missing app_id / token
    / boto-less box -> ``ok=False`` and the caller falls back to the empty-handle path.
    """
    if not data:
        return {"ok": False, "handle": "", "status": "error:empty"}
    app_id = config.meta_app_id()
    token = config.meta_token()
    if not (app_id and token):
        return {"ok": False, "handle": "", "status": "error:no_app_id_or_token"}
    base = config.graph_base()
    try:
        import httpx
        with httpx.Client(timeout=60.0) as c:
            start = c.post(f"{base}/{app_id}/uploads", params={
                "file_length": len(data), "file_type": content_type, "access_token": token})
            if start.status_code != 200:
                return {"ok": False, "handle": "",
                        "status": f"error:start_http_{start.status_code}"}
            session_id = (start.json() or {}).get("id", "")
            if not session_id:
                return {"ok": False, "handle": "", "status": "error:no_session"}
            up = c.post(f"{base}/{session_id}",
                        headers={"Authorization": "OAuth " + token, "file_offset": "0"},
                        content=data)
            if up.status_code != 200:
                return {"ok": False, "handle": "",
                        "status": f"error:upload_http_{up.status_code}"}
            handle = (up.json() or {}).get("h", "")
            if not handle:
                return {"ok": False, "handle": "", "status": "error:no_handle"}
            return {"ok": True, "handle": handle, "status": "uploaded"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "handle": "", "status": f"error:{type(e).__name__}"}


def upload_header_image(data: bytes, *, content_type: str = "image/png") -> dict:
    """Banner bytes -> (1) stored in DO Spaces for provenance, (2) Meta Resumable
    Upload -> header_handle. Returns ``{"ok","handle","spaces_key","status"}``.

    The ``handle`` is what goes into the template's ``_header_handle`` (then
    example.header_handle). Dormant-safe: any failure -> ``ok=False``, no exception;
    the caller then submits with no media example."""
    if not data:
        return {"ok": False, "handle": "", "spaces_key": "", "status": "error:empty"}
    spaces_res = _spaces_put_bytes(data, content_type)   # best-effort provenance
    up = _resumable_upload_handle(data, content_type)    # the part Meta needs
    return {"ok": bool(up.get("ok")), "handle": up.get("handle", ""),
            "spaces_key": spaces_res.get("key", ""), "status": up.get("status", "")}


def resolve_header_handle_from_src(src_url: str) -> dict:
    """Given a provider/CDN/Spaces banner URL, download the bytes and run
    upload_header_image to obtain a Meta header_handle. Returns
    ``{"ok","handle","status"}``. Dormant-safe; never raises."""
    if not src_url:
        return {"ok": False, "handle": "", "status": "error:empty"}
    try:
        import httpx
        with httpx.Client(timeout=60.0, follow_redirects=True) as c:
            resp = c.get(src_url)
        if resp.status_code >= 400:
            return {"ok": False, "handle": "",
                    "status": f"error:download_http_{resp.status_code}"}
        ctype = (resp.headers.get("content-type") or "image/png").split(";")[0].strip()
        return upload_header_image(resp.content, content_type=ctype)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "handle": "", "status": f"error:{type(e).__name__}"}


def submit(tpl: dict, personalization: list[dict] | None = None) -> dict:
    """Submit an approved template to Meta. Dormant w/o creds. Never raises."""
    if not config.meta_ready():
        return {"status": "not_configured", "meta_template_id": ""}
    payload = to_meta_payload(tpl, personalization)
    url = f"{config.graph_base()}/{config.meta_waba_id()}/message_templates"
    try:
        import httpx
        r = httpx.post(url, headers={"Authorization": "Bearer " + config.meta_token()},
                       json=payload, timeout=20)
        data = r.json() if r.status_code == 200 else {}
        if r.status_code == 200 and data.get("id"):
            return {"status": "submitted", "meta_template_id": data.get("id", ""),
                    "review_status": data.get("status", "PENDING")}
        return {"status": "error", "meta_template_id": "",
                "detail": f"http_{r.status_code}"}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "meta_template_id": "", "detail": type(e).__name__}
