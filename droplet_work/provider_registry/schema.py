"""provider_registry.schema — dataclasses + enums for the registry (W1 shell).

Spec: design/PROVIDER-FRAMEWORK-PLAN.md §4 ("schema.py — ProviderDef / ProviderCred /
Capability / TransformType dataclasses + from_any") + §5 (the DDL these mirror) + §7
(the transform tiers).

PURE module: stdlib only (dataclasses / enum / typing). NO I/O, NO third-party imports,
NEVER raises at import — so it loads cleanly on an empty-env box (the W1 guarantee).

These dataclasses are the in-process mirror of the three PG tables. They are the typed
shape the W2+ behavioural modules (store / adapter / credentials / registry) construct
and pass around. `from_any` builds a dataclass from a DB row (a Mapping / RowMapping /
sequence-of-tuples-via-keys), tolerating missing/extra keys so a schema add never breaks
a read. The actual encrypt/decrypt + SSRF-validate + 3-tier-transform logic is W2+; this
file only defines the value objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any, List, Mapping, Optional


# ---------------------------------------------------------------------------
# Enums — the controlled vocabularies. `.from_any` is lenient (unknown -> a safe
# default / passthrough string is preserved on the dataclass as the raw text), so a
# new vocabulary value added in a later DDL never breaks an older reader.
# ---------------------------------------------------------------------------
class Capability(str, Enum):
    """What a provider can serve. Consumers ask for a capability, not a provider name
    (§2c — the universal connector seam). Video Studio asks 'video_gen' first."""
    VIDEO_GEN = "video_gen"
    IMAGE_GEN = "image_gen"
    TEXT_GEN = "text_gen"
    TTS = "tts"
    STT = "stt"
    EMBED = "embed"
    RERANK = "rerank"
    TOOL_CALL = "tool_call"
    WEBHOOK = "webhook"
    STORAGE = "storage"


class TransformType(str, Enum):
    """The 3-tier transform model (§7) — how 'add any API via the UI' actually works."""
    OPENAI_COMPAT = "openai_compat"      # Tier 1: zero code, ~90% of the market.
    NAMED_PROVIDER = "named_provider"    # Tier 2: one dict entry (the existing video builders).
    CUSTOM_FIELD_MAP = "custom_field_map"  # Tier 3: JSONPath-only, no-eval (the moat).


class ProviderType(str, Enum):
    HOSTED_API = "hosted_api"
    SELF_HOSTED = "self_hosted"          # super-admin-only + SSRF-validated (W2).
    TOOL_CONNECTOR = "tool_connector"
    PLATFORM_BUILTIN = "platform_builtin"


class AuthScheme(str, Enum):
    BEARER = "bearer"
    API_KEY_HEADER = "api_key_header"
    API_KEY_QUERY = "api_key_query"
    BASIC = "basic"
    OAUTH2_CC = "oauth2_cc"
    NONE = "none"


class CredentialScope(str, Enum):
    """§5 — the one column that delivers 'BYO-key but never leak a platform key'.
      * INTEGRATION : the vendor's OWN key -> the vendor CAN reveal/rotate it (PIN step-up).
      * AI_PROVIDER : a PLATFORM key -> the vendor sees masked-only, NO reveal/rotate.
    """
    INTEGRATION = "integration"
    AI_PROVIDER = "ai_provider"


def _enum_or_raw(enum_cls, value: Any, default: Any = None):
    """Coerce a DB string to its enum member; if unknown, keep the RAW string (so a
    future vocabulary value round-trips) and never raise. None -> default."""
    if value is None:
        return default
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(str(value))
    except (ValueError, KeyError):
        return str(value)  # preserve forward-compatible unknown values verbatim


# Sentinel for "platform-shared" rows (§5 — the '_global' write-locked tenant_id).
GLOBAL_TENANT = "_global"


# ---------------------------------------------------------------------------
# ProviderDef — mirror of the provider_definitions table (§5 table 1).
# ---------------------------------------------------------------------------
@dataclass
class ProviderDef:
    id: Optional[str] = None
    tenant_id: str = ""
    slug: str = ""
    display_name: str = ""
    provider_type: Any = ProviderType.HOSTED_API
    capabilities: List[str] = field(default_factory=list)
    base_url: str = ""
    auth_scheme: Any = AuthScheme.BEARER
    auth_header_name: Optional[str] = None
    auth_value_tmpl: Optional[str] = "Bearer {key}"
    transform_type: Any = TransformType.OPENAI_COMPAT
    named_provider: Optional[str] = None
    request_field_map: Optional[dict] = None
    response_field_map: Optional[dict] = None
    model_default: Optional[str] = None
    cost_per_unit_micros: Optional[int] = None   # INTEGER micro-USD; never float (founder law)
    cost_unit: Optional[str] = None
    health_check_path: Optional[str] = None
    health_interval_s: int = 60
    priority: int = 100
    rate_limit_rpm: Optional[int] = None
    is_enabled: bool = True
    is_platform_default: bool = False
    created_by: Optional[str] = None
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None

    @property
    def is_global(self) -> bool:
        """Platform-shared (super-admin-owned, write-locked) provider definition."""
        return self.tenant_id == GLOBAL_TENANT

    @classmethod
    def from_any(cls, row: Mapping[str, Any] | None) -> Optional["ProviderDef"]:
        """Build from a DB row mapping, tolerating missing/extra keys (never raises)."""
        if row is None:
            return None
        data = dict(row)
        obj = cls()
        valid = {f.name for f in fields(cls)}
        for k, v in data.items():
            if k in valid:
                setattr(obj, k, v)
        # coerce capabilities to a list (DB jsonb may arrive as a list already)
        if isinstance(obj.capabilities, (str, bytes)):
            obj.capabilities = []
        elif obj.capabilities is None:
            obj.capabilities = []
        else:
            obj.capabilities = list(obj.capabilities)
        obj.provider_type = _enum_or_raw(ProviderType, obj.provider_type, ProviderType.HOSTED_API)
        obj.auth_scheme = _enum_or_raw(AuthScheme, obj.auth_scheme, AuthScheme.BEARER)
        obj.transform_type = _enum_or_raw(TransformType, obj.transform_type, TransformType.OPENAI_COMPAT)
        # UUID objects from psycopg2 must be stringified (JSON can't serialize uuid.UUID).
        if obj.id is not None and not isinstance(obj.id, str):
            obj.id = str(obj.id)
        return obj


# ---------------------------------------------------------------------------
# ProviderCred — mirror of the provider_credentials table (§5 table 2).
# NOTE: this object carries CIPHERTEXT only. The plaintext is NEVER stored on the
# dataclass; decrypt happens behind the get_secret() seam (W2 credentials.py) and the
# plaintext is handed to the caller transiently, never persisted on a value object.
# ---------------------------------------------------------------------------
@dataclass
class ProviderCred:
    id: Optional[str] = None
    tenant_id: str = ""
    provider_def_id: str = ""
    ciphertext: Optional[bytes] = None       # AES-256-GCM(plaintext, DEK), 12-byte nonce prepended
    wrapped_dek: Optional[bytes] = None      # NULL on the interim Fernet path
    key_aad: str = ""                        # 'tenant_id||provider_def_id||version' (GCM binding)
    key_version: int = 1
    kek_version: Optional[str] = None
    scope: Any = CredentialScope.INTEGRATION
    last_rotated_at: Optional[Any] = None
    expires_at: Optional[Any] = None
    is_active: bool = True
    created_at: Optional[Any] = None

    @property
    def is_revealable_by_vendor(self) -> bool:
        """§6 reveal policy: only the vendor's OWN ('integration') key may be revealed/
        rotated by the vendor. A platform ('ai_provider') key is masked-only to a vendor."""
        scope = self.scope.value if isinstance(self.scope, CredentialScope) else str(self.scope)
        return scope == CredentialScope.INTEGRATION.value

    @classmethod
    def expected_aad(cls, tenant_id: str, provider_def_id: str, key_version: int) -> str:
        """The MANDATORY GCM AAD binding (§2d / §5): copying a ciphertext into another
        tenant's row changes the AAD -> decrypt fails with InvalidTag (no plaintext).
        This is the single canonical AAD formula every encrypt/decrypt (W2) must use."""
        return f"{tenant_id}||{provider_def_id}||{key_version}"

    @classmethod
    def from_any(cls, row: Mapping[str, Any] | None) -> Optional["ProviderCred"]:
        if row is None:
            return None
        data = dict(row)
        obj = cls()
        valid = {f.name for f in fields(cls)}
        for k, v in data.items():
            if k in valid:
                setattr(obj, k, v)
        obj.scope = _enum_or_raw(CredentialScope, obj.scope, CredentialScope.INTEGRATION)
        # Stringify UUID objects from psycopg2.
        for uuid_field in ("id", "provider_def_id"):
            v = getattr(obj, uuid_field, None)
            if v is not None and not isinstance(v, str):
                setattr(obj, uuid_field, str(v))
        return obj
