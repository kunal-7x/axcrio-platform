"""voice_ops.config.profile — the Vendor Control Center model (W13).

ONE central, per-vendor config object that workers / schedulers / agents read in real time WITHOUT a
redeploy. Today these settings are scattered (env-global, or buried in the Business-Brain JSON with
no schema); this is the founder's single source of truth:

  - human_handoff_number      where hot/high-ticket leads transfer to a real human
  - ai_manager_number         the inbound DID the AI-Manager answers on
  - whatsapp_report_number    where the daily/end-of-call WhatsApp report is sent
  - plan                      plan tier (drives the provider triple in router.py)
  - phone_numbers             the vendor's owned/verified caller-IDs / DIDs
  - provider_cred_refs        which provider keys are *preferred* (fingerprints, not secrets)
  - retention                 per-tenant recording vs transcript TTLs (W9 is env-GLOBAL; this is the
                              per-vendor override the founder asked for) + storage-usage knobs
  - compliance                consent/DNC/recording-disclosure/region flags
  - whatsapp                  FUTURE-READY: blank-but-present fields that ACTIVATE when creds added

It is persisted as a single JSON doc in the versioned, FORCE-RLS `config_state` store under the
`vendor_profile` namespace, so an edit bumps the version + emits config_changed → live everywhere.

NO SECRETS live here — provider secrets stay in the encrypted key store (config.keys); this profile
only references their fingerprints. Importing this pulls ZERO droplet/agent code.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Optional

from . import events as _events
from .store import ConfigStore

log = logging.getLogger("voice_ops.config.profile")

NAMESPACE = "vendor_profile"

_E164 = re.compile(r"^\+?[1-9]\d{6,14}$")


def _norm_phone(v: str) -> str:
    """Light E.164-ish normalization; empty stays empty (a blank field is valid = 'not set yet')."""
    s = (v or "").strip().replace(" ", "").replace("-", "")
    return s


# --------------------------------------------------------------------------- #
# sub-models
# --------------------------------------------------------------------------- #
@dataclass
class RetentionPolicy:
    """Per-tenant retention — INDEPENDENT recording vs transcript TTLs (the layer W9's env-global
    RECORDING_RETENTION_DAYS does NOT provide). Read by the W9 retention sweep + the cleanup audit.

    A value of 0 means 'keep forever' for that artifact (e.g. transcripts often kept forever for lead
    intelligence; raw recordings expire). recording_retention_days defaults to W9's 30."""

    recording_retention_days: int = 30
    transcript_retention_days: int = 0          # 0 = keep forever (business intelligence)
    summary_retention_days: int = 0             # 0 = keep forever
    archive_after_days: int = 30                # move hot->cold tier
    storage_quota_mb: int = 0                   # 0 = unlimited; else cleanup pressure threshold
    delete_audio_after_archive: bool = True


@dataclass
class ComplianceSettings:
    """Consent / DNC / disclosure / region knobs the call + WhatsApp paths honor."""

    recording_disclosure: bool = True          # announce "this call is recorded"
    consent_required: bool = False
    honor_dnc: bool = True                      # skip Do-Not-Call numbers
    data_region: str = "in"                     # data-residency hint
    pii_redaction: bool = True
    quiet_hours_start: str = ""                 # "21:00" local; blank = none
    quiet_hours_end: str = ""                   # "09:00"


@dataclass
class WhatsAppConfig:
    """FUTURE-READY WhatsApp config — blank-but-present now, ACTIVATES when creds are added later.
    The secrets (access token / app secret) live ENCRYPTED in the key store under provider
    'whatsapp'; this holds only the non-secret routing fields + the activation flag. `active` is
    derived (True only once the required non-secret fields are filled AND a 'whatsapp' key exists),
    so the rest of the system can check `profile.whatsapp.active` and stay dormant until then."""

    phone_number_id: str = ""
    business_account_id: str = ""
    waba_display_number: str = ""
    verify_token_ref: str = ""                  # fingerprint of the verify token in the key store
    app_secret_ref: str = ""                    # fingerprint of the app secret in the key store
    template_namespace: str = ""
    default_template: str = ""
    enabled: bool = False                       # founder toggle; activation also needs creds present

    def is_active(self, has_whatsapp_key: bool) -> bool:
        return bool(self.enabled and self.phone_number_id and has_whatsapp_key)


@dataclass
class VendorProfile:
    """The full Vendor Control Center record."""

    tenant_id: str = ""
    human_handoff_number: str = ""
    ai_manager_number: str = ""
    whatsapp_report_number: str = ""
    plan: str = "lean"                          # lean|standard|growth|premium|enterprise
    phone_numbers: list = field(default_factory=list)   # owned caller-IDs / DIDs
    provider_cred_refs: dict = field(default_factory=dict)  # provider -> preferred fingerprint
    retention: RetentionPolicy = field(default_factory=RetentionPolicy)
    compliance: ComplianceSettings = field(default_factory=ComplianceSettings)
    whatsapp: WhatsAppConfig = field(default_factory=WhatsAppConfig)
    version: int = 0
    updated_by: str = ""

    # --------------------------------------------------------- (de)serialize -- #
    def to_doc(self) -> dict:
        d = asdict(self)
        d.pop("version", None)  # version is owned by the store, not the doc body
        return d

    @classmethod
    def from_doc(cls, tenant_id: str, doc: dict, version: int = 0) -> "VendorProfile":
        doc = dict(doc or {})
        ret = doc.get("retention") or {}
        comp = doc.get("compliance") or {}
        wa = doc.get("whatsapp") or {}
        return cls(
            tenant_id=tenant_id,
            human_handoff_number=_norm_phone(doc.get("human_handoff_number", "")),
            ai_manager_number=_norm_phone(doc.get("ai_manager_number", "")),
            whatsapp_report_number=_norm_phone(doc.get("whatsapp_report_number", "")),
            plan=(doc.get("plan") or "lean").strip().lower(),
            phone_numbers=[_norm_phone(p) for p in (doc.get("phone_numbers") or []) if str(p).strip()],
            provider_cred_refs=dict(doc.get("provider_cred_refs") or {}),
            retention=RetentionPolicy(**{k: ret[k] for k in ret if k in RetentionPolicy.__dataclass_fields__}),
            compliance=ComplianceSettings(**{k: comp[k] for k in comp if k in ComplianceSettings.__dataclass_fields__}),
            whatsapp=WhatsAppConfig(**{k: wa[k] for k in wa if k in WhatsAppConfig.__dataclass_fields__}),
            version=version,
            updated_by=doc.get("updated_by", ""),
        )

    def validate(self) -> list[str]:
        """Return a list of soft warnings (NOT exceptions) — blank fields are allowed (a vendor may
        not have set a handoff number yet). Only obviously-malformed non-blank phones warn, so the
        panel can show a hint without blocking the save."""
        warns: list[str] = []
        for name in ("human_handoff_number", "ai_manager_number", "whatsapp_report_number"):
            v = getattr(self, name)
            if v and not _E164.match(v):
                warns.append(f"{name} '{v}' is not a valid E.164 number")
        for p in self.phone_numbers:
            if p and not _E164.match(p):
                warns.append(f"phone_number '{p}' is not a valid E.164 number")
        if self.plan not in ("lean", "standard", "growth", "premium", "enterprise"):
            warns.append(f"unknown plan '{self.plan}'")
        return warns


# --------------------------------------------------------------------------- #
# the live, versioned profile store.
# --------------------------------------------------------------------------- #
class VendorProfileStore:
    """Read/write the Vendor Control Center over the versioned config store. A write bumps the
    version + emits config_changed → propagates live to every worker/scheduler/agent reader."""

    def __init__(self, store: Optional[ConfigStore] = None) -> None:
        self.store = store or ConfigStore()

    def get(self, tenant_id: str, *, is_admin: bool = False) -> VendorProfile:
        """Read the profile (cache-aware). A tenant with no row yet gets a DEFAULT profile (blank
        fields, lean plan) — never None, so callers never special-case 'not configured'."""
        snap = self.store.get(tenant_id, NAMESPACE, is_admin=is_admin)
        if snap is None:
            return VendorProfile(tenant_id=tenant_id)
        return VendorProfile.from_doc(tenant_id, snap.doc, snap.version)

    def put(self, profile: VendorProfile, *, updated_by: str = "", is_admin: bool = False) -> VendorProfile:
        """Persist the whole profile (atomic version bump + config_changed event). Returns the
        refreshed profile carrying the new version."""
        tenant_id = (profile.tenant_id or "").strip()
        if not tenant_id:
            raise ValueError("vendor profile requires a tenant_id (fail-closed)")
        doc = profile.to_doc()
        doc["updated_by"] = updated_by or profile.updated_by or ""
        snap = self.store.put(tenant_id, NAMESPACE, doc, updated_by=updated_by, is_admin=is_admin)
        _events.emit_config_changed(tenant_id, NAMESPACE, snap.version, updated_by)
        log.info("vendor profile saved tenant=%s v=%s (LIVE, no redeploy)", tenant_id, snap.version)
        out = VendorProfile.from_doc(tenant_id, doc, snap.version)
        return out

    def patch(self, tenant_id: str, changes: dict, *, updated_by: str = "", is_admin: bool = False) -> VendorProfile:
        """Partial update: merge top-level + nested (retention/compliance/whatsapp) changes onto the
        current profile, then put. Lets the panel save one field without resending the whole doc."""
        cur = self.get(tenant_id, is_admin=is_admin)
        doc = cur.to_doc()
        for k, v in (changes or {}).items():
            if k in ("retention", "compliance", "whatsapp") and isinstance(v, dict):
                sub = dict(doc.get(k) or {})
                sub.update(v)
                doc[k] = sub
            else:
                doc[k] = v
        merged = VendorProfile.from_doc(tenant_id, doc, cur.version)
        return self.put(merged, updated_by=updated_by, is_admin=is_admin)
