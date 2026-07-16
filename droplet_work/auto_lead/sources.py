"""
auto_lead.sources — source-type registry + pull adapters.

SOURCE_TYPES drives the UI (label / icon / connect-mode / credential fields) and the
poller. PUSH sources deliver via the public ingest webhook (real-time). PULL sources
(email inbox, Apollo) are polled on a schedule; poll_source() returns a list of raw
payload dicts that flow through the SAME extract→validate→route pipeline as webhooks.
"""

from __future__ import annotations

import re

# mode: "push" => connect by pasting the ingest webhook URL into the platform.
#       "pull" => Haptica polls the source on a schedule using these credentials.
SOURCE_TYPES: dict[str, dict] = {
    "custom": {
        "label": "Custom Webhook", "mode": "push", "icon": "chain",
        "desc": "Any tool or backend that can POST JSON — point it at the webhook URL.",
        "fields": [],
    },
    "website": {
        "label": "Website Form", "mode": "push", "icon": "earth",
        "desc": "Your site's contact/lead form. POST submissions to the webhook URL.",
        "fields": [],
    },
    "zapier": {
        "label": "Zapier / Make", "mode": "push", "icon": "layers",
        "desc": "Bridge 5000+ apps. Add a Webhooks action pointing at the URL below.",
        "fields": [],
    },
    "meta_ads": {
        "label": "Meta Lead Ads", "mode": "push", "icon": "facebook",
        "desc": "Facebook / Instagram lead forms. Deliver leads to the webhook (field_data is auto-parsed).",
        "fields": [],
    },
    "google_ads": {
        "label": "Google Ads", "mode": "push", "icon": "promote",
        "desc": "Google lead-form extensions. Set the webhook URL as the delivery endpoint.",
        "fields": [],
    },
    "whatsapp": {
        "label": "WhatsApp", "mode": "push", "icon": "chat",
        "desc": "Inbound WhatsApp enquiries. Forward them to the webhook URL.",
        "fields": [],
    },
    "email": {
        "label": "Email Inbox", "mode": "pull", "icon": "envelope",
        "desc": "Watch an inbox (IMAP) for new lead/contact-form emails.",
        "fields": [
            {"key": "host", "label": "IMAP host", "type": "text", "placeholder": "imap.gmail.com", "required": True},
            {"key": "port", "label": "Port", "type": "number", "placeholder": "993", "required": False},
            {"key": "username", "label": "Email / username", "type": "text", "placeholder": "leads@yourco.com", "required": True},
            {"key": "password", "label": "Password / app password", "type": "password", "placeholder": "••••••••", "required": True},
            {"key": "folder", "label": "Folder", "type": "text", "placeholder": "INBOX", "required": False},
        ],
    },
    "apollo": {
        "label": "Apollo", "mode": "pull", "icon": "profile",
        "desc": "Pull new contacts from an Apollo saved search/list.",
        "fields": [
            {"key": "api_key", "label": "Apollo API key", "type": "password", "placeholder": "••••••••", "required": True},
            {"key": "list_id", "label": "Saved-list / label ID", "type": "text", "placeholder": "optional", "required": False},
        ],
    },
}

_PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{8,16}\d)")


def type_meta(t: str) -> dict:
    return SOURCE_TYPES.get(t, SOURCE_TYPES["custom"])


def is_pull(t: str) -> bool:
    return type_meta(t).get("mode") == "pull"


def public_types() -> list[dict]:
    """Browser-safe catalog for the 'add a source' gallery."""
    return [{"type": k, "label": v["label"], "mode": v["mode"], "icon": v["icon"],
             "desc": v["desc"], "fields": v["fields"]} for k, v in SOURCE_TYPES.items()]


# ── pull adapters (run off the event loop via asyncio.to_thread) ─────────────
def poll_source(source: dict, *, limit: int = 25) -> list[dict]:
    """Return new lead payloads from a pull source. Never raises -> [] on any error."""
    t = source.get("type")
    cfg = source.get("config") or {}
    try:
        if t == "email":
            return _poll_email(cfg, limit=limit)
        if t == "apollo":
            return _poll_apollo(cfg, limit=limit)
    except Exception:  # noqa: BLE001
        return []
    return []


def _poll_email(cfg: dict, *, limit: int) -> list[dict]:
    import email as _email
    import imaplib
    from email.header import decode_header, make_header

    host = (cfg.get("host") or "").strip()
    user = (cfg.get("username") or "").strip()
    pw = cfg.get("password") or ""
    if not (host and user and pw):
        return []
    port = int(cfg.get("port") or 993)
    folder = (cfg.get("folder") or "INBOX").strip() or "INBOX"

    out: list[dict] = []
    M = imaplib.IMAP4_SSL(host, port)
    try:
        M.login(user, pw)
        M.select(folder)
        typ, data = M.search(None, "UNSEEN")
        if typ != "OK":
            return []
        ids = (data[0].split() if data and data[0] else [])[:limit]
        for num in ids:
            typ, msg_data = M.fetch(num, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = _email.message_from_bytes(msg_data[0][1])
            from_hdr = str(make_header(decode_header(msg.get("From", ""))))
            subject = str(make_header(decode_header(msg.get("Subject", ""))))
            from_email = ""
            m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", from_hdr)
            if m:
                from_email = m.group(0)
            body = _email_body(msg)
            phone = ""
            pm = _PHONE_RE.search(body) or _PHONE_RE.search(subject)
            if pm:
                phone = pm.group(1)
            name = _scan_label(body, ("name", "full name")) or from_hdr.split("<")[0].strip().strip('"')
            payload = {"name": name, "phone": phone, "email": from_email,
                       "subject": subject, "body": body[:500]}
            out.append(payload)
            try:
                M.store(num, "+FLAGS", "\\Seen")
            except Exception:  # noqa: BLE001
                pass
    finally:
        try:
            M.logout()
        except Exception:  # noqa: BLE001
            pass
    return out


def _email_body(msg) -> str:
    try:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    return part.get_payload(decode=True).decode(errors="ignore")
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    html = part.get_payload(decode=True).decode(errors="ignore")
                    return re.sub(r"<[^>]+>", " ", html)
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(errors="ignore")
    except Exception:  # noqa: BLE001
        pass
    return ""


def _scan_label(text: str, labels) -> str:
    for lab in labels:
        m = re.search(rf"{lab}\s*[:\-]\s*(.+)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip().splitlines()[0][:80]
    return ""


def _poll_apollo(cfg: dict, *, limit: int) -> list[dict]:
    import httpx

    api_key = (cfg.get("api_key") or "").strip()
    if not api_key:
        return []
    body = {"page": 1, "per_page": min(limit, 25)}
    if cfg.get("list_id"):
        body["label_ids"] = [cfg["list_id"]]
    try:
        r = httpx.post("https://api.apollo.io/v1/mixed_people/search",
                       headers={"Cache-Control": "no-cache", "Content-Type": "application/json",
                                "X-Api-Key": api_key},
                       json=body, timeout=20)
        if r.status_code != 200:
            return []
        people = (r.json() or {}).get("people") or []
    except Exception:  # noqa: BLE001
        return []
    out = []
    for p in people[:limit]:
        out.append({
            "name": (f"{p.get('first_name','')} {p.get('last_name','')}").strip(),
            "phone": p.get("sanitized_phone") or p.get("phone") or "",
            "email": p.get("email") or "",
            "company": (p.get("organization") or {}).get("name") if isinstance(p.get("organization"), dict) else "",
        })
    return out
