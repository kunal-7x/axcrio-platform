"""trunk_registry.schema — dataclasses + enums for the trunk registry (T2).

Spec: design/TELEPHONY-INDEPENDENCE-PLAN.md §2.2 (the 3 tables) + §3 (red-team B1: the
is_campaign_eligible gate; red-team D: is_undeletable). A column-for-column TWIN of
provider_registry/schema.py — same PURE module discipline.

PURE module: stdlib only (dataclasses / enum / typing). NO I/O, NO third-party imports,
NEVER raises at import — so it loads cleanly on an empty-env box.

These dataclasses are the in-process mirror of the three PG tables (db/ddl_trunk_registry.sql):
  * SipTrunk        <- sip_trunks
  * SipTrunkCred    <- sip_trunk_credentials
  * SipTrunkHealth  <- sip_trunk_health_log (read shape; writes are append-only)
`from_any` builds a dataclass from a DB row (a Mapping / RowMapping), tolerating missing/extra
keys so a schema add never breaks a read. The encrypt/decrypt + SSRF-validate + resolve logic
lives in the behavioural modules; this file only defines the value objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any, List, Mapping, Optional


# ---------------------------------------------------------------------------
# Sentinel for "platform-shared" rows (§2.2 — the '_global' write-locked tenant_id).
# The live Vobiz trunk is seeded as a '_global' row so flag-on dials the SAME trunk.
# ---------------------------------------------------------------------------
GLOBAL_TENANT = "_global"


# ---------------------------------------------------------------------------
# Enums — the controlled vocabularies (mirror the DDL CHECK constraints). `.from_any`
# is lenient (unknown -> the raw string is preserved), so a new vocabulary value added
# in a later DDL never breaks an older reader.
# ---------------------------------------------------------------------------
class TrunkType(str, Enum):
    """How this trunk bridges to PSTN. A consumer SIM is NEVER a trunk directly (§0)."""
    SIP_PROVIDER = "sip_provider"     # Vobiz / Plivo / Exotel / a 140-series VNO trunk.
    GSM_GATEWAY = "gsm_gateway"       # a physical SIM via GoIP/Yeastar — manual-only, 1 SIM = 1 call.
    DIRECT_SIP = "direct_sip"         # a raw SIP endpoint (super-admin only).


class Direction(str, Enum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"
    BOTH = "both"


class Transport(str, Enum):
    UDP = "udp"
    TCP = "tcp"
    TLS = "tls"


class Encryption(str, Enum):
    DISABLE = "disable"
    SRTP = "srtp"


class DltStatus(str, Enum):
    UNREGISTERED = "unregistered"
    PENDING = "pending"
    REGISTERED = "registered"


class RotationStrategy(str, Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_USED = "least_used"
    STICKY = "sticky"


class CredentialScope(str, Enum):
    """§2.2 — the one column that delivers 'BYO-key but never leak a platform key'.
      * INTEGRATION : the vendor's OWN SIP password -> the vendor CAN reveal/rotate it (PIN step-up).
      * PLATFORM    : a PLATFORM SIP password -> the vendor sees masked-only, NO reveal/rotate.
    """
    INTEGRATION = "integration"
    PLATFORM = "platform"


# The dial PURPOSE a consumer asks for. CAMPAIGN demands campaign-eligibility (the B1 gate);
# TEST / MANUAL are a single founder-placed dial (never an auto-dial) and skip that gate so
# flag-on can dial the (non-140) Vobiz '_global' trunk for a real test ring.
class Purpose(str, Enum):
    CAMPAIGN = "campaign"   # auto-dialed at volume -> REQUIRES is_campaign_eligible (140 + DLT).
    TEST = "test"           # a single founder test ring -> eligibility NOT required.
    MANUAL = "manual"       # a single founder-typed manual recall -> eligibility NOT required.
    INBOUND = "inbound"     # inbound DID -> agent routing (not gated by the campaign rule).


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


def _as_list(v) -> List[Any]:
    """Coerce a jsonb column (which may arrive as a list, a str, or None) to a list."""
    if isinstance(v, (str, bytes)):
        return []
    if v is None:
        return []
    try:
        return list(v)
    except TypeError:
        return []


# ---------------------------------------------------------------------------
# SipTrunk — mirror of the sip_trunks table (§2.2 table 1).
# ---------------------------------------------------------------------------
@dataclass
class SipTrunk:
    id: Optional[str] = None
    tenant_id: str = ""
    slug: str = ""
    display_name: str = ""
    trunk_type: Any = TrunkType.SIP_PROVIDER
    provider_vendor: Optional[str] = None
    direction: Any = Direction.OUTBOUND
    sip_host: str = ""
    sip_port: int = 5060
    transport: Any = Transport.UDP
    encryption: Any = Encryption.DISABLE
    auth_username: Optional[str] = None
    allowed_addresses: List[str] = field(default_factory=list)
    did_pool: List[str] = field(default_factory=list)
    caller_id: Optional[str] = None
    max_concurrency: int = 1
    cost_per_minute_paise: Optional[int] = None   # INTEGER paise; never float (founder law)
    # ===== COMPLIANCE GATES (red-team B1) =====
    is_140_series: bool = False
    dlt_entity_id: Optional[str] = None
    dlt_status: Any = DltStatus.UNREGISTERED
    per_did_daily_cap: int = 0
    # rotation / failover
    priority: int = 100
    rotation_strategy: Any = RotationStrategy.ROUND_ROBIN
    # state
    is_enabled: bool = True
    is_test_verified: bool = False
    quarantined_until: Optional[Any] = None
    is_undeletable: bool = False
    livekit_trunk_id: Optional[str] = None        # the LiveKit-SIP ST_<id> this row resolves to
    # the DB-DERIVED campaign-eligibility gate (GENERATED column; read-only, never user-set)
    is_campaign_eligible: bool = False
    created_by: Optional[str] = None
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None

    @property
    def is_global(self) -> bool:
        """Platform-shared (super-admin-owned, write-locked) trunk."""
        return self.tenant_id == GLOBAL_TENANT

    @property
    def is_gsm(self) -> bool:
        ttype = self.trunk_type.value if isinstance(self.trunk_type, TrunkType) else str(self.trunk_type)
        return ttype == TrunkType.GSM_GATEWAY.value

    def is_quarantined(self, now=None) -> bool:
        """True iff this trunk is currently resting (quarantined_until in the future)."""
        if self.quarantined_until is None:
            return False
        try:
            import datetime as _dt
            ref = now or _dt.datetime.now(_dt.timezone.utc)
            qu = self.quarantined_until
            if isinstance(qu, str):
                # tolerate an ISO string from a non-psycopg2 row
                qu = _dt.datetime.fromisoformat(qu.replace("Z", "+00:00"))
            # normalise both to aware-UTC for a safe compare
            if getattr(qu, "tzinfo", None) is None:
                qu = qu.replace(tzinfo=_dt.timezone.utc)
            if getattr(ref, "tzinfo", None) is None:
                ref = ref.replace(tzinfo=_dt.timezone.utc)
            return qu > ref
        except Exception:  # noqa: BLE001 — never raise from a value-object helper
            return False

    @property
    def dids(self) -> List[str]:
        """The DID pool, falling back to the single caller_id if the pool is empty."""
        pool = [d for d in (self.did_pool or []) if d]
        if pool:
            return pool
        return [self.caller_id] if self.caller_id else []

    @classmethod
    def from_any(cls, row: Mapping[str, Any] | None) -> Optional["SipTrunk"]:
        """Build from a DB row mapping, tolerating missing/extra keys (never raises)."""
        if row is None:
            return None
        data = dict(row)
        obj = cls()
        valid = {f.name for f in fields(cls)}
        for k, v in data.items():
            if k in valid:
                setattr(obj, k, v)
        obj.allowed_addresses = _as_list(obj.allowed_addresses)
        obj.did_pool = _as_list(obj.did_pool)
        obj.trunk_type = _enum_or_raw(TrunkType, obj.trunk_type, TrunkType.SIP_PROVIDER)
        obj.direction = _enum_or_raw(Direction, obj.direction, Direction.OUTBOUND)
        obj.transport = _enum_or_raw(Transport, obj.transport, Transport.UDP)
        obj.encryption = _enum_or_raw(Encryption, obj.encryption, Encryption.DISABLE)
        obj.dlt_status = _enum_or_raw(DltStatus, obj.dlt_status, DltStatus.UNREGISTERED)
        obj.rotation_strategy = _enum_or_raw(RotationStrategy, obj.rotation_strategy,
                                             RotationStrategy.ROUND_ROBIN)
        # bools may arrive as None from a partial row
        obj.is_140_series = bool(obj.is_140_series)
        obj.is_enabled = bool(obj.is_enabled)
        obj.is_test_verified = bool(obj.is_test_verified)
        obj.is_undeletable = bool(obj.is_undeletable)
        obj.is_campaign_eligible = bool(obj.is_campaign_eligible)
        # UUID objects from psycopg2 must be stringified (JSON can't serialize uuid.UUID).
        if obj.id is not None and not isinstance(obj.id, str):
            obj.id = str(obj.id)
        return obj


# ---------------------------------------------------------------------------
# SipTrunkCred — mirror of the sip_trunk_credentials table (§2.2 table 2).
# Carries CIPHERTEXT only. The plaintext is NEVER stored on the dataclass; decrypt happens
# behind the get_secret() seam (credentials.py) and the plaintext is handed to the caller
# transiently, never persisted on a value object.
# ---------------------------------------------------------------------------
@dataclass
class SipTrunkCred:
    id: Optional[str] = None
    tenant_id: str = ""
    trunk_id: str = ""
    ciphertext: Optional[bytes] = None       # AES-256-GCM(sip_password, DEK), 12-byte nonce prepended
    wrapped_dek: Optional[bytes] = None       # NULL on the interim Fernet path
    key_aad: str = ""                         # 'tenant_id||trunk_id||version' (GCM binding)
    key_version: int = 1
    kek_version: Optional[str] = None
    scope: Any = CredentialScope.INTEGRATION
    last_rotated_at: Optional[Any] = None
    expires_at: Optional[Any] = None
    is_active: bool = True
    created_at: Optional[Any] = None

    @property
    def is_revealable_by_vendor(self) -> bool:
        """§2.2 reveal policy: only the vendor's OWN ('integration') SIP password may be
        revealed/rotated by the vendor. A platform password is masked-only to a vendor."""
        scope = self.scope.value if isinstance(self.scope, CredentialScope) else str(self.scope)
        return scope == CredentialScope.INTEGRATION.value

    @classmethod
    def expected_aad(cls, tenant_id: str, trunk_id: str, key_version: int) -> str:
        """The MANDATORY GCM AAD binding (§2.2): copying a ciphertext into another tenant's
        row changes the AAD -> decrypt fails with InvalidTag (no plaintext). The single
        canonical AAD formula every encrypt/decrypt must use. Identical FORM to the
        provider_registry binding (tenant||def||version) but over the TRUNK id."""
        return f"{tenant_id}||{trunk_id}||{key_version}"

    @classmethod
    def from_any(cls, row: Mapping[str, Any] | None) -> Optional["SipTrunkCred"]:
        if row is None:
            return None
        data = dict(row)
        obj = cls()
        valid = {f.name for f in fields(cls)}
        for k, v in data.items():
            if k in valid:
                setattr(obj, k, v)
        obj.scope = _enum_or_raw(CredentialScope, obj.scope, CredentialScope.INTEGRATION)
        for uuid_field in ("id", "trunk_id"):
            v = getattr(obj, uuid_field, None)
            if v is not None and not isinstance(v, str):
                setattr(obj, uuid_field, str(v))
        return obj


# ---------------------------------------------------------------------------
# SipTrunkHealth — read shape of a sip_trunk_health_log row (§2.2 table 3).
# ---------------------------------------------------------------------------
@dataclass
class SipTrunkHealth:
    id: Optional[int] = None
    tenant_id: str = ""
    trunk_id: str = ""
    did: Optional[str] = None
    checked_at: Optional[Any] = None
    event: Optional[str] = None
    is_healthy: Optional[bool] = None
    sip_code: Optional[int] = None
    latency_ms: Optional[int] = None
    error_code: Optional[str] = None

    @classmethod
    def from_any(cls, row: Mapping[str, Any] | None) -> Optional["SipTrunkHealth"]:
        if row is None:
            return None
        data = dict(row)
        obj = cls()
        valid = {f.name for f in fields(cls)}
        for k, v in data.items():
            if k in valid:
                setattr(obj, k, v)
        if obj.trunk_id is not None and not isinstance(obj.trunk_id, str):
            obj.trunk_id = str(obj.trunk_id)
        return obj
