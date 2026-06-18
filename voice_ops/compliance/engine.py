"""voice_ops.compliance.engine — `compliance.preflight()` : the dial-time GATE (W26 §3).

ONE entry point the dial loop calls per lead, BEFORE the wallet hold + SIP originate:

    preflight(tenant, lead, campaign) -> Decision{verdict: allow|block|soft,
                                                   reasons[], disclosure_ctx, gate}

Gate order (cheapest-first / hardest-block-first, design/W26 §3.3):
  A1 registration  DLT PE active + header + >=1 approved template + autodialer notified
  A2 number_series CLI is a registered 140/1600 series, not a 10-digit mobile
  A4 window        within the LEGAL hard floor (10:00–19:00, BFSI 08:00) — recipient-local
  A5 consent       TCCCPR place-call consent fresh at dial time (explicit=7d)
  A3 dnd           NCPR national register (<=30d fresh) + local suppression scrub
  B  disclosure    resolve the warm Tier-0 disclosure_ctx (brand+purpose+record cue)

Fail-mode: any Tier-A failure -> BLOCK + reason. A store/DB error during a Tier-A check
-> FAIL-CLOSED block (never dial on unknown compliance state). Tier-B (disclosure /
retention) failure -> resolve to the safe policy + continue (the disclosure is always
produced; recording-notice defaults ON).

FLAG-GATED: when `COMPLIANCE_ENABLED` is OFF, preflight returns ALLOW immediately with
`compliance_unenforced=True` and a still-built disclosure_ctx (so W2 can be tested
independently) — the resting build is byte-identical to pre-engine. The registration +
DLT state is read through a `RegistrationStore` Protocol (InMemory test impl + a future
PgRegistrationStore over the FORCE-RLS dlt_registry table).

Emits W8 events when an EventBus is injected (compliance_blocked / compliance_allowed) —
fire-and-forget, an emit failure NEVER affects a decision. Tenant-isolated: every check
fail-closes on empty tenant. ZERO droplet_work / agent imports; redis/psycopg2 lazy.
"""
from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from . import cli_series, consent as _consent
from .config import ComplianceConfig
from .disclosure import DisclosureCtx, build_disclosure_ctx
from .dnd import DndScrubber, number_hash
from .window_floor import clamp_to_legal_floor, legal_floor

log = logging.getLogger("voice_ops.compliance.engine")

ALLOW = "allow"
BLOCK = "block"
SOFT = "soft"


# --------------------------------------------------------------------------- #
# Registration / DLT state (A1). Protocol + InMemory; a future PgRegistrationStore
# reads the FORCE-RLS dlt_registry table.
# --------------------------------------------------------------------------- #
@dataclass
class RegistrationState:
    tenant_id: str
    pe_status: str = "none"            # none|pending|active|suspended
    headers: List[Dict[str, Any]] = field(default_factory=list)
    templates: List[Dict[str, Any]] = field(default_factory=list)
    cli_numbers: List[Dict[str, Any]] = field(default_factory=list)
    autodialer_notified: bool = False
    sender_of_record: str = "tenant"

    def is_dial_ready(self) -> bool:
        if self.pe_status != "active":
            return False
        if not any((h.get("status") == "active") for h in (self.headers or [])):
            return False
        if not any((t.get("status") == "approved") for t in (self.templates or [])):
            return False
        return bool(self.autodialer_notified)


@runtime_checkable
class RegistrationStore(Protocol):
    def get(self, tenant_id: str) -> Optional[RegistrationState]: ...


class InMemoryRegistrationStore:
    def __init__(self):
        self._rows: Dict[str, RegistrationState] = {}

    def put(self, state: RegistrationState) -> None:
        self._rows[(state.tenant_id or "").strip()] = state

    def get(self, tenant_id: str) -> Optional[RegistrationState]:
        return self._rows.get((tenant_id or "").strip())


# --------------------------------------------------------------------------- #
# Decision.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Decision:
    verdict: str                       # allow | block | soft
    reasons: List[str] = field(default_factory=list)
    gate: str = ""                     # the gate that decided (registration|number_series|window|consent|dnd|disclosure)
    disclosure_ctx: Optional[DisclosureCtx] = None
    needs_rescrub: bool = False        # DND cache miss -> requeue rather than dial
    compliance_unenforced: bool = False  # True when flag OFF (resting marker)

    @property
    def allowed(self) -> bool:
        return self.verdict in (ALLOW, SOFT)


class ComplianceEngine:
    """The dial-time gate. Construct once per process with the stores it needs (all
    optional -> InMemory). `event_bus` is any object with async `emit(Event)` (W8) or
    None."""

    def __init__(self, cfg: Optional[ComplianceConfig] = None, *,
                 registration_store: Optional[RegistrationStore] = None,
                 consent_ledger: Optional[_consent.ConsentLedger] = None,
                 dnd_scrubber: Optional[DndScrubber] = None,
                 event_bus: Any = None,
                 now_fn=None):
        self.cfg = cfg or ComplianceConfig.from_env()
        self.reg = registration_store or InMemoryRegistrationStore()
        self.consent = consent_ledger or _consent.ConsentLedger(
            explicit_days=self.cfg.explicit_consent_days, now_fn=now_fn)
        self.dnd = dnd_scrubber or DndScrubber(
            salt=self.cfg.number_hash_salt, refresh_days=self.cfg.dnd_refresh_days, now_fn=now_fn)
        self._bus = event_bus
        self._now = now_fn or (lambda: _dt.datetime.now(_dt.timezone.utc))

    # ------------------------------------------------------------- preflight #
    async def preflight(self, tenant_id: str, lead: Dict[str, Any],
                        campaign: Dict[str, Any]) -> Decision:
        """The gate. `lead` = {phone, lead_id?, tz?}; `campaign` = {id?, vertical?,
        purpose?, cli?, brand?, product?, window_start?, window_end?, recording?}.
        Returns a Decision. NEVER raises — any internal error on a Tier-A check
        fail-closes to BLOCK (never dial on unknown compliance state)."""
        lead = lead or {}
        campaign = campaign or {}
        phone = str(lead.get("phone") or "")
        vertical = str(campaign.get("vertical") or "")
        purpose = str(campaign.get("purpose") or cli_series.PURPOSE_CAMPAIGN)

        # disclosure is ALWAYS resolved (Tier-B safe), even when the flag is OFF, so W2 can test it.
        disclosure = self._build_disclosure(campaign)

        t = (tenant_id or "").strip()
        if not t:
            return await self._finalize(Decision(BLOCK, ["empty_tenant_fail_closed"],
                                                 "tenant", disclosure), tenant_id, campaign, phone)

        # FLAG OFF -> allow (resting), but carry the disclosure_ctx + the marker.
        if not self.cfg.enabled:
            return Decision(ALLOW, ["compliance_unenforced"], "flag_off", disclosure,
                            compliance_unenforced=True)

        # ---- A1 registration (cheapest: cached state) ----
        try:
            reg = self.reg.get(t)
        except Exception as exc:  # noqa: BLE001
            log.info("preflight A1 registration store error (fail-closed): %r", exc)
            return await self._finalize(Decision(BLOCK, ["registration_store_error_fail_closed"],
                                                 "registration", disclosure), t, campaign, phone)
        if reg is None or not reg.is_dial_ready():
            why = "no_dlt_registration" if reg is None else self._reg_reason(reg)
            return await self._finalize(Decision(BLOCK, [why], "registration", disclosure),
                                        t, campaign, phone)

        # ---- A2 number-series (the CLI shape; registration confirmed the number is registered) ----
        cli = str(campaign.get("cli") or self._first_active_cli(reg))
        sv = cli_series.check(cli, purpose=purpose)
        if not sv.eligible:
            return await self._finalize(Decision(BLOCK, [f"cli_series:{sv.reason}"],
                                                 "number_series", disclosure), t, campaign, phone)

        # ---- A4 calling-window legal hard floor (recipient-local) ----
        win_ok, win_reason = self._window_ok(campaign, lead, vertical)
        if not win_ok:
            return await self._finalize(Decision(BLOCK, [f"window:{win_reason}"],
                                                 "window", disclosure), t, campaign, phone)

        # ---- A5 consent freshness at dial time ----
        principal = str(lead.get("lead_id") or "") or number_hash(phone, self.cfg.number_hash_salt)
        cv = self.consent.is_fresh(t, principal,
                                   consent_type=_consent.TCCCPR_PLACE_CALL,
                                   scope=str(campaign.get("id") or ""))
        if not cv.fresh:
            return await self._finalize(Decision(BLOCK, [f"consent:{cv.reason}"],
                                                 "consent", disclosure), t, campaign, phone)

        # ---- A3 DND / NCPR scrub-before-dial ----
        sr = self.dnd.scrub(t, phone)
        if sr.block:
            return await self._finalize(Decision(BLOCK, [f"dnd:{sr.reason}"], "dnd",
                                                 disclosure, needs_rescrub=sr.needs_rescrub),
                                        t, campaign, phone)

        # ---- ALLOW ----
        return await self._finalize(Decision(ALLOW, ["all_gates_passed"], "", disclosure),
                                    t, campaign, phone)

    # ------------------------------------------------------------- helpers #
    def _build_disclosure(self, campaign: Dict[str, Any]) -> DisclosureCtx:
        try:
            tier = int(campaign.get("disclosure_tier", self.cfg.disclosure_tier))
        except (TypeError, ValueError):
            tier = self.cfg.disclosure_tier
        rec = bool(campaign.get("recording", self.cfg.recording_notice))
        return build_disclosure_ctx(
            brand=str(campaign.get("brand") or ""),
            purpose=str(campaign.get("purpose_text") or campaign.get("product") or ""),
            product=str(campaign.get("product") or ""),
            tier=tier, record_cue=rec,
        )

    @staticmethod
    def _reg_reason(reg: RegistrationState) -> str:
        if reg.pe_status != "active":
            return f"pe_status_{reg.pe_status}"
        if not any(h.get("status") == "active" for h in (reg.headers or [])):
            return "no_active_header"
        if not any(t.get("status") == "approved" for t in (reg.templates or [])):
            return "no_approved_template"
        if not reg.autodialer_notified:
            return "autodialer_not_notified"
        return "not_dial_ready"

    @staticmethod
    def _first_active_cli(reg: RegistrationState) -> str:
        for c in (reg.cli_numbers or []):
            if c.get("status") in (None, "active") and c.get("number"):
                return str(c.get("number"))
        return ""

    def _window_ok(self, campaign: Dict[str, Any], lead: Dict[str, Any],
                   vertical: str) -> tuple[bool, str]:
        """Recipient-local window check against the LEGAL hard floor. The tenant window
        is clamped (cannot widen); then we test 'now' against the effective window."""
        tz_name = str(lead.get("tz") or campaign.get("tz") or self.cfg.default_tz)
        try:
            from zoneinfo import ZoneInfo
            tzinfo = ZoneInfo(tz_name)
        except Exception:  # noqa: BLE001 — fixed +05:30 IST fallback
            tzinfo = _dt.timezone(_dt.timedelta(hours=5, minutes=30))
        now_local = self._now().astimezone(tzinfo)

        (eff_start, eff_end), note = clamp_to_legal_floor(
            str(campaign.get("window_start") or "10:00"),
            str(campaign.get("window_end") or "19:00"),
            vertical=vertical, cfg=self.cfg,
        )
        sm = eff_start[0] * 60 + eff_start[1]
        em = eff_end[0] * 60 + eff_end[1]
        cur = now_local.hour * 60 + now_local.minute
        if em <= sm:
            return False, f"degenerate_effective_window({note})"
        if sm <= cur < em:
            return True, f"in_window({note})"
        return False, f"outside_effective_window_{eff_start[0]:02d}:{eff_start[1]:02d}-{eff_end[0]:02d}:{eff_end[1]:02d}({note})"

    async def _finalize(self, decision: Decision, tenant_id: str,
                        campaign: Dict[str, Any], phone: str) -> Decision:
        """Emit the W8 compliance event (fire-and-forget) + return the decision."""
        await self._emit(decision, tenant_id, campaign, phone)
        if decision.verdict == BLOCK:
            log.info("compliance BLOCK gate=%s reasons=%s", decision.gate, decision.reasons)
        return decision

    async def _emit(self, decision: Decision, tenant_id: str,
                    campaign: Dict[str, Any], phone: str) -> None:
        if self._bus is None:
            return
        try:
            from voice_kernel.events import make_event
            name = "provider_failed" if decision.verdict == BLOCK else "call_started"
            # We reuse the closed taxonomy: a compliance block is logged as a distinct
            # payload on a neutral fact; a dedicated compliance event name can be added
            # to the taxonomy in a later append-only change.
            ev = make_event(
                name,
                call_id=f"compliance:{campaign.get('id','')}",
                tenant_id=tenant_id,
                payload={
                    "kind": "compliance_decision",
                    "verdict": decision.verdict,
                    "gate": decision.gate,
                    "reasons": ",".join(decision.reasons)[:200],
                    "disclosure_tier": decision.disclosure_ctx.tier if decision.disclosure_ctx else None,
                },
            )
            await self._bus.emit(ev)
        except Exception as exc:  # noqa: BLE001 — emit never affects a decision
            log.info("compliance event emit failed (non-fatal): %r", exc)


# --------------------------------------------------------------------------- #
# Module-level convenience: a process-wide singleton + a `preflight` function so the
# seam can call `from voice_ops.compliance import preflight` directly (mirrors the
# ergonomic factories in voice_kernel.events).
# --------------------------------------------------------------------------- #
_ENGINE: Optional[ComplianceEngine] = None


def get_engine(cfg: Optional[ComplianceConfig] = None) -> ComplianceEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = ComplianceEngine(cfg)
    return _ENGINE


def set_engine(engine: Optional[ComplianceEngine]) -> None:
    """Inject a configured engine (tests / the seam wiring). None resets to lazy default."""
    global _ENGINE
    _ENGINE = engine


async def preflight(tenant_id: str, lead: Dict[str, Any],
                    campaign: Dict[str, Any]) -> Decision:
    """Module-level gate: `from voice_ops.compliance import preflight`. Uses the
    process singleton engine (lazy from env)."""
    return await get_engine().preflight(tenant_id, lead, campaign)
