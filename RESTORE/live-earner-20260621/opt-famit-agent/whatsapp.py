"""whatsapp.py — provider-agnostic WhatsApp sender for Famit (WAVE3 Unit5 + WAVE A2 Meta).

Single entry point: send_whatsapp(to, template_or_text, params) -> dict result.
Free-form text inside the 24h customer-service window: send_whatsapp_text(to, text).

------------------------------------------------------------------------------
NATIVE META WHATSAPP CLOUD API (WAVE A2 — the user's actual BSP)
The user's BSP is Meta WhatsApp Cloud API. When these env vars are present the
module talks to Meta natively (graph.facebook.com), preferring them over the
generic WA_* config. ALL are blank today -> module stays a graceful NO-OP and
returns {"status":"not_configured"} (logs "WA not configured"); it NEVER raises.
    META_WA_PHONE_NUMBER_ID    Cloud API phone-number-id (path segment of the send URL)
    META_WA_TOKEN              permanent system-user access token (Bearer)
    META_WA_BUSINESS_ACCOUNT_ID  WABA id (not needed to send; kept for parity/admin)
    META_WA_VERIFY_TOKEN       webhook verification token (used by caller.py GET /whatsapp/inbound)
    META_WA_APP_SECRET         app secret (used by caller.py to verify X-Hub-Signature-256)
Send URL:  https://graph.facebook.com/v21.0/{META_WA_PHONE_NUMBER_ID}/messages
Header:    Authorization: Bearer {META_WA_TOKEN}
Template body: {"messaging_product":"whatsapp","to":..,"type":"template",
                "template":{"name":..,"language":{"code":..},"components":[..]}}
Text body:     {"messaging_product":"whatsapp","to":..,"type":"text",
                "text":{"body":..,"preview_url":false}}
"meta_configured()" -> True when PHONE_NUMBER_ID + TOKEN are set.
------------------------------------------------------------------------------

LEGACY generic BSP fallback (kept intact). CREDS (all OPTIONAL):
    WA_API_URL   full POST endpoint of your BSP (Business Solution Provider)
    WA_API_KEY   bearer/api token for that endpoint
    WA_FROM      sender id / phone-number-id / source number (provider-dependent)
    WA_PROVIDER  one of: meta | gupshup | interakt | generic   (default: generic)

------------------------------------------------------------------------------
PROVIDER FORMATS — this module builds the request body per WA_PROVIDER. Pick the
one matching your BSP by setting WA_PROVIDER; if none fits, use "generic" and
adjust _build_body() below. The shapes assumed:

  meta  (Meta WhatsApp Cloud API)
    POST https://graph.facebook.com/v19.0/<PHONE_NUMBER_ID>/messages
    headers: Authorization: Bearer <WA_API_KEY>
    body (template): {"messaging_product":"whatsapp","to":"<to>",
                      "type":"template","template":{"name":"<tpl>",
                      "language":{"code":"en"},
                      "components":[{"type":"body","parameters":[{"type":"text","text":v}...]}]}}
    -> set WA_API_URL to the full /<PHONE_NUMBER_ID>/messages URL; WA_FROM unused.

  gupshup
    POST https://api.gupshup.io/wa/api/v1/template/msg  (or your configured URL)
    headers: apikey: <WA_API_KEY>
    body (form-ish JSON here): {"source":"<WA_FROM>","destination":"<to>",
                                "template":{"id":"<tpl>","params":[...]}}

  interakt
    POST https://api.interakt.ai/v1/public/message/
    headers: Authorization: Basic <WA_API_KEY>
    body: {"fullPhoneNumber":"<to>","type":"Template",
           "template":{"name":"<tpl>","languageCode":"en",
           "bodyValues":[...]}}

  generic  (default — simple flat JSON; easiest to point any BSP at)
    POST <WA_API_URL>
    headers: Authorization: Bearer <WA_API_KEY>
    body: {"from":"<WA_FROM>","to":"<to>","template":"<tpl-or-text>","params":[...]}
------------------------------------------------------------------------------

Returns a dict: {"ok": bool, "status": "<sent:NNN|skipped_no_config|error:...>",
                 "provider": str, "to": str}. NEVER raises.
"""
from __future__ import annotations

import os
from typing import Any

try:
    import httpx
except Exception:  # noqa: BLE001
    httpx = None  # type: ignore


def _cfg() -> dict:
    return {
        "url": os.getenv("WA_API_URL", "").strip(),
        "key": os.getenv("WA_API_KEY", "").strip(),
        "frm": os.getenv("WA_FROM", "").strip(),
        "provider": (os.getenv("WA_PROVIDER", "generic") or "generic").strip().lower(),
        "lang": (os.getenv("WA_LANG", "en") or "en").strip(),
    }


def _meta_cfg() -> dict:
    return {
        "phone_id": os.getenv("META_WA_PHONE_NUMBER_ID", "").strip(),
        "token": os.getenv("META_WA_TOKEN", "").strip(),
        "waba_id": os.getenv("META_WA_BUSINESS_ACCOUNT_ID", "").strip(),
        "verify_token": os.getenv("META_WA_VERIFY_TOKEN", "").strip(),
        "app_secret": os.getenv("META_WA_APP_SECRET", "").strip(),
        "lang": (os.getenv("WA_LANG", "en") or "en").strip(),
        "version": (os.getenv("META_WA_API_VERSION", "v21.0") or "v21.0").strip(),
    }


def meta_configured() -> bool:
    """True when the native Meta Cloud API send path is usable."""
    m = _meta_cfg()
    return bool(m["phone_id"] and m["token"])


def is_configured() -> bool:
    """True when EITHER the native Meta path OR the legacy generic BSP is set."""
    if meta_configured():
        return True
    c = _cfg()
    return bool(c["url"] and c["key"])


def _meta_url() -> str:
    m = _meta_cfg()
    return f"https://graph.facebook.com/{m['version']}/{m['phone_id']}/messages"


def _meta_to(to: str) -> str:
    """Meta Cloud API wants the recipient as bare E.164 digits (no leading '+').
    Upstream callers normalise to '+<cc><number>' (caller.py norm()); Graph 404s on the
    '+'-prefixed value. Strip the '+' here, at the single Meta-body boundary. Never raises."""
    return (to or "").strip().lstrip("+")


def _meta_template_body(to: str, template: str, params: Any, lang: str) -> dict:
    plist = _params_list(params)
    comps = []
    if plist:
        comps = [{"type": "body",
                  "parameters": [{"type": "text", "text": p} for p in plist]}]
    return {"messaging_product": "whatsapp", "to": _meta_to(to), "type": "template",
            "template": {"name": template, "language": {"code": lang},
                         "components": comps}}


def _meta_text_body(to: str, text: str) -> dict:
    return {"messaging_product": "whatsapp", "to": _meta_to(to), "type": "text",
            "text": {"body": text, "preview_url": False}}


def _meta_document_body(to: str, link: str, filename: str = "", caption: str = "") -> dict:
    """Meta Cloud API DOCUMENT message. ``link`` MUST be a publicly fetchable URL that
    Meta can download at send time (e.g. a presigned Spaces GET URL). ``filename`` is the
    name shown to the recipient; ``caption`` is optional accompanying text."""
    doc: dict[str, Any] = {"link": link}
    if filename:
        doc["filename"] = filename
    if caption:
        doc["caption"] = caption
    return {"messaging_product": "whatsapp", "to": _meta_to(to),
            "type": "document", "document": doc}


def _params_list(params: Any) -> list[str]:
    if params is None:
        return []
    if isinstance(params, dict):
        return [str(v) for v in params.values()]
    if isinstance(params, (list, tuple)):
        return [str(v) for v in params]
    return [str(params)]


def _build_body(provider: str, frm: str, to: str, template_or_text: str,
                params: Any, lang: str) -> tuple[str, dict | None, dict | None]:
    """Return (url_suffix_unused, headers, json_body) for the given provider.
    headers None means use the default bearer header set by caller."""
    plist = _params_list(params)
    if provider == "meta":
        comps = []
        if plist:
            comps = [{"type": "body",
                      "parameters": [{"type": "text", "text": p} for p in plist]}]
        body = {"messaging_product": "whatsapp", "to": to, "type": "template",
                "template": {"name": template_or_text, "language": {"code": lang},
                             "components": comps}}
        return "", None, body
    if provider == "gupshup":
        headers = {"apikey": "", "Content-Type": "application/json"}  # apikey filled by caller
        body = {"source": frm, "destination": to,
                "template": {"id": template_or_text, "params": plist}}
        return "", headers, body
    if provider == "interakt":
        body = {"fullPhoneNumber": to, "type": "Template",
                "template": {"name": template_or_text, "languageCode": lang,
                             "bodyValues": plist}}
        return "", None, body
    # generic
    body = {"from": frm, "to": to, "template": template_or_text, "params": plist}
    return "", None, body


def _apply_meta_response(result: dict, resp) -> dict:
    """WAFX fix#4: classify a Meta /messages response. On success -> ok + sent:<code>.
    On a Graph error -> ok=False, an HONEST status (NOT "sent:") and the REAL Meta error
    surfaced (code / error_subcode / error_user_title / error_user_msg / fbtrace_id) so the
    panel/logs show the true reason (e.g. 141006 payment method) instead of a generic
    'try again'. Never raises."""
    ok = resp.status_code < 300
    result["ok"] = ok
    try:
        result["response"] = resp.text[:300]
    except Exception:  # noqa: BLE001
        pass
    if ok:
        result["status"] = f"sent:{resp.status_code}"
        return result
    err = {}
    try:
        err = ((resp.json() or {}).get("error")) or {}
    except Exception:  # noqa: BLE001
        err = {}
    code = err.get("code", "")
    subcode = err.get("error_subcode", "")
    result["meta_error"] = {
        "http_status": resp.status_code, "code": code, "subcode": subcode,
        "type": err.get("type", ""), "message": err.get("message", ""),
        "error_user_title": err.get("error_user_title", ""),
        "error_user_msg": err.get("error_user_msg", ""),
        "fbtrace_id": err.get("fbtrace_id", ""),
        "is_transient": err.get("is_transient", False),
    }
    # An honest, machine-grep-able status string. e.g. "meta_error:141006" or
    # "meta_error:131009/2388xxx". This REPLACES the misleading "sent:400".
    tag = str(code) + ("/" + str(subcode) if subcode else "")
    result["status"] = "meta_error:" + (tag or str(resp.status_code))
    return result


def _post_meta(body: dict) -> dict:
    """Blocking POST to Meta Cloud API. Returns a result dict; never raises."""
    m = _meta_cfg()
    result = {"ok": False, "status": "not_configured", "provider": "meta",
              "to": body.get("to", "")}
    if not meta_configured():
        return result
    if httpx is None:
        result["status"] = "error:httpx_unavailable"
        return result
    try:
        headers = {"Authorization": "Bearer " + m["token"],
                   "Content-Type": "application/json"}
        with httpx.Client(timeout=12) as cli:
            resp = cli.post(_meta_url(), headers=headers, json=body)
        _apply_meta_response(result, resp)
    except Exception as exc:  # noqa: BLE001
        result["status"] = f"error:{repr(exc)[:120]}"
    return result


async def _post_meta_async(body: dict) -> dict:
    m = _meta_cfg()
    result = {"ok": False, "status": "not_configured", "provider": "meta",
              "to": body.get("to", "")}
    if not meta_configured():
        return result
    if httpx is None:
        result["status"] = "error:httpx_unavailable"
        return result
    try:
        headers = {"Authorization": "Bearer " + m["token"],
                   "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=12) as cli:
            resp = await cli.post(_meta_url(), headers=headers, json=body)
        _apply_meta_response(result, resp)
    except Exception as exc:  # noqa: BLE001
        result["status"] = f"error:{repr(exc)[:120]}"
    return result


def send_whatsapp_text(to: str, text: str) -> dict:
    """Free-form text message (valid only INSIDE the 24h customer-service window).
    Native Meta path only; no-ops gracefully when Meta isn't configured. Never raises."""
    if meta_configured():
        return _post_meta(_meta_text_body(to, text))
    # Generic fallback: treat the text as the message body via the generic provider.
    return send_whatsapp(to, text, None)


async def send_whatsapp_text_async(to: str, text: str) -> dict:
    if meta_configured():
        return await _post_meta_async(_meta_text_body(to, text))
    return await send_whatsapp_async(to, text, None)


def send_whatsapp_document(to: str, url: str, filename: str = "",
                           caption: str = "") -> dict:
    """Send a DOCUMENT (e.g. a brochure PDF) via the native Meta Cloud API.
    ``url`` must be a publicly fetchable link Meta downloads at send time (a presigned
    Spaces GET URL works). Native Meta path only; documents are NOT a generic-BSP feature
    here, so when Meta isn't configured this no-ops gracefully. Never raises."""
    if not (url or "").strip():
        return {"ok": False, "status": "error:no_url", "provider": "meta", "to": to}
    if not meta_configured():
        return {"ok": False, "status": "skipped_no_config", "provider": "meta", "to": to}
    return _post_meta(_meta_document_body(to, url, filename, caption))


async def send_whatsapp_document_async(to: str, url: str, filename: str = "",
                                       caption: str = "") -> dict:
    if not (url or "").strip():
        return {"ok": False, "status": "error:no_url", "provider": "meta", "to": to}
    if not meta_configured():
        return {"ok": False, "status": "skipped_no_config", "provider": "meta", "to": to}
    return await _post_meta_async(_meta_document_body(to, url, filename, caption))


def send_whatsapp(to: str, template_or_text: str, params: Any = None) -> dict:
    """Send a WhatsApp message via the configured BSP (template message).
    - to: destination phone (E.164-ish, e.g. +9198...)
    - template_or_text: template name (or raw text for generic providers)
    - params: list/dict/scalar of template body variables
    No-ops (logs nothing, raises nothing) when creds are absent.
    Native Meta Cloud API is preferred when META_WA_* env is present."""
    # WAVE A2: native Meta path wins when configured.
    if meta_configured():
        return _post_meta(_meta_template_body(to, template_or_text, params,
                                              _meta_cfg()["lang"]))
    c = _cfg()
    provider = c["provider"]
    result = {"ok": False, "status": "not_configured", "provider": provider, "to": to}
    if not (c["url"] and c["key"]):
        # WA not configured — graceful no-op (caller logs "WA not configured").
        return result
    if httpx is None:
        result["status"] = "error:httpx_unavailable"
        return result
    try:
        _, custom_headers, body = _build_body(provider, c["frm"], to,
                                              template_or_text, params, c["lang"])
        if custom_headers is not None:
            headers = dict(custom_headers)
            if provider == "gupshup":
                headers["apikey"] = c["key"]
        else:
            headers = {"Authorization": "Bearer " + c["key"],
                       "Content-Type": "application/json"}
        with httpx.Client(timeout=12) as cli:
            resp = cli.post(c["url"], headers=headers, json=body)
        result["ok"] = resp.status_code < 300
        result["status"] = f"sent:{resp.status_code}"
        try:
            result["response"] = resp.text[:300]
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        result["status"] = f"error:{repr(exc)[:120]}"
    return result


async def send_whatsapp_async(to: str, template_or_text: str, params: Any = None) -> dict:
    """Async variant for use inside the FastAPI event loop (non-blocking).
    Native Meta Cloud API is preferred when META_WA_* env is present."""
    # WAVE A2: native Meta path wins when configured.
    if meta_configured():
        return await _post_meta_async(_meta_template_body(to, template_or_text, params,
                                                          _meta_cfg()["lang"]))
    c = _cfg()
    provider = c["provider"]
    result = {"ok": False, "status": "not_configured", "provider": provider, "to": to}
    if not (c["url"] and c["key"]):
        return result
    if httpx is None:
        result["status"] = "error:httpx_unavailable"
        return result
    try:
        _, custom_headers, body = _build_body(provider, c["frm"], to,
                                              template_or_text, params, c["lang"])
        if custom_headers is not None:
            headers = dict(custom_headers)
            if provider == "gupshup":
                headers["apikey"] = c["key"]
        else:
            headers = {"Authorization": "Bearer " + c["key"],
                       "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=12) as cli:
            resp = await cli.post(c["url"], headers=headers, json=body)
        result["ok"] = resp.status_code < 300
        result["status"] = f"sent:{resp.status_code}"
        try:
            result["response"] = resp.text[:300]
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        result["status"] = f"error:{repr(exc)[:120]}"
    return result
