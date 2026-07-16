"""grow.acquisition — L1 consented capture (Meta/Google Lead Ads + CTWA referral).

The ONLY high-yield, *legal* B2C source (ElevateX §1/§2): an ad → instant form pre-filled
from the user's profile → they consent + submit → the leadgen webhook fires in <2s. This
module turns each provider's payload into a canonical `CapturedLead`, RECORDS the consent
(the form opt-in is the legal shield under TCCPR + DPDP), mints the journey at first touch
(correlation_id), and hands off to the L3 orchestrator (`on_lead_captured`) — the <60s
speed-to-lead fire.

Parsers + signature verification + consent recording are all here and OFFLINE-TESTABLE;
the live Graph fetch (Meta gives only a leadgen_id) and the page→tenant map are INJECTED
seams (founder-gated on Meta app review / Ads OAuth). stdlib at import; never raises into
the webhook path. No coupling to the shared auto_lead/caller — Grow-native ingress.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Callable, Optional

from .model import CapturedLead, normalize_email, normalize_phone, principal_ref

log = logging.getLogger("grow.acquisition")


# =========================================================================== #
# Signature / token verification (fail-closed)
# =========================================================================== #
def verify_meta_signature(raw_body: bytes, header_sig: str, app_secret: str) -> bool:
    """Meta X-Hub-Signature-256: 'sha256=<hex hmac of the raw body with the app secret>'.
    Fail-closed: empty secret/sig/body => False. Constant-time compare."""
    if not app_secret or not header_sig or raw_body is None:
        return False
    try:
        expected = "sha256=" + hmac.new(app_secret.encode("utf-8"), raw_body,
                                        hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, header_sig.strip())
    except Exception:  # noqa: BLE001
        return False


def verify_meta_challenge(params: dict, verify_token: str) -> Optional[str]:
    """Meta webhook GET handshake: echo hub.challenge iff hub.verify_token matches."""
    if not verify_token:
        return None
    if (params.get("hub.mode") == "subscribe"
            and params.get("hub.verify_token") == verify_token):
        return params.get("hub.challenge")
    return None


# =========================================================================== #
# Parsers — provider payload -> canonical CapturedLead
# =========================================================================== #
def _from_field_data(field_data: list) -> dict:
    """Meta/Google forms deliver answers as [{name/column_id, values/string_value}]. Map the
    common real-estate fields to {phone,email,name} tolerant of label drift."""
    out: dict = {}
    for f in field_data or []:
        key = str(f.get("name") or f.get("column_id") or "").strip().lower()
        val = ""
        if "values" in f and isinstance(f["values"], list) and f["values"]:
            val = str(f["values"][0])
        else:
            val = str(f.get("string_value") or f.get("value") or "")
        if not val:
            continue
        if key in ("phone_number", "phone", "phone_number_", "mobile", "contact_number"):
            out["phone"] = val
        elif key in ("email", "email_address", "work_email"):
            out["email"] = val
        elif key in ("full_name", "name", "first_name", "your_name"):
            out["name"] = (out.get("name", "") + " " + val).strip() if key == "last_name" else val
        elif key == "last_name":
            out["name"] = (out.get("name", "") + " " + val).strip()
    return out


def parse_meta_lead(value: dict, tenant_id: str, *, fetched: Optional[dict] = None) -> Optional[CapturedLead]:
    """A Meta `leadgen` change value: {leadgen_id, page_id, form_id, ad_id, created_time}.
    The webhook carries only the id — the actual answers come from a Graph fetch
    (`fetched` = the /{leadgen_id} response with field_data). If `fetched` is absent we
    still mint a CapturedLead with the attribution (phone resolved later) so the journey +
    ad mapping start immediately."""
    if not value:
        return None
    leadgen_id = str(value.get("leadgen_id") or value.get("id") or "")
    ad_id = str(value.get("ad_id") or "")
    fields = _from_field_data((fetched or {}).get("field_data", [])) if fetched else {}
    lead_id = (normalize_phone(fields.get("phone", "")) or leadgen_id)
    if not lead_id:
        return None
    return CapturedLead(
        tenant_id=tenant_id, lead_id=lead_id, phone=fields.get("phone", ""),
        name=fields.get("name", ""), email=fields.get("email", ""),
        source_platform="meta", source_ad_id=ad_id,
        consent_basis="explicit", consent_channel="web_form",
        extra={"leadgen_id": leadgen_id, "form_id": str(value.get("form_id") or "")})


def parse_google_lead(payload: dict, tenant_id: str) -> Optional[CapturedLead]:
    """Google Lead Form webhook: {lead_id, campaign_id, gcl_id, user_column_data:[...]}."""
    if not payload:
        return None
    fields = _from_field_data(payload.get("user_column_data", []))
    lead_id = (normalize_phone(fields.get("phone", "")) or str(payload.get("lead_id") or ""))
    if not lead_id:
        return None
    return CapturedLead(
        tenant_id=tenant_id, lead_id=lead_id, phone=fields.get("phone", ""),
        name=fields.get("name", ""), email=fields.get("email", ""),
        source_platform="google", source_ad_id=str(payload.get("campaign_id") or ""),
        gclid=str(payload.get("gcl_id") or payload.get("gclid") or ""),
        campaign_id=str(payload.get("campaign_id") or ""),
        consent_basis="explicit", consent_channel="web_form",
        extra={"google_lead_id": str(payload.get("lead_id") or "")})


def parse_ctwa_referral(wa_value: dict, tenant_id: str) -> Optional[CapturedLead]:
    """A WhatsApp inbound message that came from a Click-to-WhatsApp ad. The referral
    object keys the conversion to the exact ad even with zero pixels (§11.2):
    messages[0].referral = {source_id: ad_id, ctwa_clid, headline, ...}; contacts[0] =
    {wa_id, profile.name}. The CTWA conversation opens a free 72h service window."""
    if not wa_value:
        return None
    msgs = wa_value.get("messages") or []
    contacts = wa_value.get("contacts") or []
    if not msgs:
        return None
    msg = msgs[0]
    ref = msg.get("referral") or {}
    wa_id = str(msg.get("from") or (contacts[0].get("wa_id") if contacts else "") or "")
    if not wa_id:
        return None
    name = ""
    if contacts:
        name = str((contacts[0].get("profile") or {}).get("name") or "")
    return CapturedLead(
        tenant_id=tenant_id, lead_id=normalize_phone(wa_id) or wa_id, phone=wa_id, name=name,
        source_platform="whatsapp", source_ad_id=str(ref.get("source_id") or ""),
        ctwa_clid=str(ref.get("ctwa_clid") or ""),
        consent_basis="explicit", consent_channel="whatsapp",
        extra={"referral_headline": str(ref.get("headline") or ""),
               "source_type": str(ref.get("source_type") or "ad")})


# =========================================================================== #
# Consent recording seam (the legal shield)
# =========================================================================== #
ConsentRecorder = Callable[[CapturedLead], bool]


def make_consent_recorder(hash_salt: str) -> Optional[ConsentRecorder]:
    """Bind to voice_ops.compliance.ConsentLedger if importable, recording the lead-form
    opt-in as TCCPR place-call consent (explicit basis, PII-min principal_ref). Returns
    None if the compliance module is absent (caller falls back to a logging no-op)."""
    try:
        from voice_ops.compliance.consent import (ConsentLedger, TCCCPR_PLACE_CALL,  # type: ignore  # noqa: PLC0415
                                                  BASIS_EXPLICIT)
    except Exception:  # noqa: BLE001
        return None
    ledger = ConsentLedger()

    def _record(c: CapturedLead) -> bool:
        try:
            ref = principal_ref(hash_salt, c.phone, lead_id=c.lead_id)
            if not ref:
                return False
            ledger.grant(c.tenant_id, ref, TCCCPR_PLACE_CALL, basis=BASIS_EXPLICIT,
                         channel=c.consent_channel, scope=c.campaign_id,
                         evidence_ref=str(c.extra.get("leadgen_id")
                                          or c.extra.get("google_lead_id") or c.ctwa_clid or ""))
            return True
        except Exception as exc:  # noqa: BLE001
            log.info("grow consent grant failed: %r", exc)
            return False

    return _record


# =========================================================================== #
# Acquisition service — parse -> consent -> capture (-> orchestrator)
# =========================================================================== #
class AcquisitionService:
    """Construct with the GrowLoop + (optional) injected consent recorder + Meta lead
    fetcher. `ingest(provider, payload, tenant_id)` parses, records consent, and drives
    the L3 orchestrator. NEVER raises into the webhook path."""

    def __init__(self, loop, *, consent_recorder: Optional[ConsentRecorder] = None,
                 meta_lead_fetcher: Optional[Callable[[str], dict]] = None):
        self.loop = loop
        self.consent = consent_recorder or make_consent_recorder(loop.cfg.hash_salt)
        self.meta_lead_fetcher = meta_lead_fetcher

    def _capture(self, captured: Optional[CapturedLead]) -> dict:
        if captured is None:
            return {"ok": False, "reason": "unparseable_or_empty"}
        consented = False
        if self.consent is not None:
            consented = bool(self.consent(captured))
        # fire the <60s speed-to-lead orchestration (journey minted inside)
        res = self.loop.on_lead_captured(
            captured.tenant_id, captured.lead_id, phone=captured.phone, name=captured.name,
            email=captured.email, source_platform=captured.source_platform,
            source_ad_id=captured.source_ad_id, ctwa_clid=captured.ctwa_clid,
            fbclid=captured.fbclid, gclid=captured.gclid, campaign_id=captured.campaign_id,
            consent_basis=captured.consent_basis, consent_channel=captured.consent_channel)
        res["consent_recorded"] = consented
        res["source_platform"] = captured.source_platform
        return res

    def ingest_meta_value(self, value: dict, tenant_id: str) -> dict:
        fetched = None
        leadgen_id = str((value or {}).get("leadgen_id") or "")
        if self.meta_lead_fetcher and leadgen_id:
            try:
                fetched = self.meta_lead_fetcher(leadgen_id)
            except Exception as exc:  # noqa: BLE001
                log.info("meta lead fetch failed: %r", exc)
        return self._capture(parse_meta_lead(value, tenant_id, fetched=fetched))

    def ingest_meta_webhook(self, body: dict, tenant_for_page: Callable[[str], str]) -> dict:
        """Full Meta webhook body -> per-entry leadgen changes -> captures. `tenant_for_page`
        maps page_id -> tenant_id (the app-level webhook isn't tenant-scoped); unmapped
        pages are dropped (no cross-tenant capture)."""
        results = []
        for entry in (body or {}).get("entry", []):
            for ch in entry.get("changes", []):
                if ch.get("field") != "leadgen":
                    continue
                value = ch.get("value") or {}
                tenant_id = tenant_for_page(str(value.get("page_id") or ""))
                if not tenant_id:
                    results.append({"ok": False, "reason": "unmapped_page"})
                    continue
                results.append(self.ingest_meta_value(value, tenant_id))
        return {"ok": True, "captured": results, "count": len(results)}

    def ingest_google(self, payload: dict, tenant_id: str) -> dict:
        return self._capture(parse_google_lead(payload, tenant_id))

    def ingest_ctwa(self, wa_value: dict, tenant_id: str) -> dict:
        return self._capture(parse_ctwa_referral(wa_value, tenant_id))
