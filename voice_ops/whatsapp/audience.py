"""voice_ops.whatsapp.audience — the WhatsApp audience resolver (W16).

Resolve a target lead set from a rich `AudienceSpec` — NEVER "send to all". The
founder's full target list:

  - hot / warm / cold / dead   — the W7 lead lifecycle (FactCall.lead_status)
  - campaign-X                 — leads touched by a specific campaign
  - agent-Y                    — leads handled by a specific agent
  - requested_brochure         — behavioural: lead asked for the brochure
  - follow_up_pending          — a callback / follow-up is scheduled but not done
  - a named custom segment     — resolved via an injectable segment hook
  - explicit lead_ids          — hand-picked rows (union)

The resolver reads the W14 reporting read-model (`ReportingStore` of `FactCall`
rows) — it NEVER re-classifies a lead; it records what the memory FSM derived.
Rows are projected to deduped `ResolvedLead`s (latest call per lead wins). It is
tenant-scoped and fail-closed: an EMPTY spec resolves to NOTHING (you must
positively choose an audience) unless `include_all` is explicitly set.

`requested_brochure` / a custom segment are behavioural signals that may not live
in FactCall; an optional `signal_hook(tenant_id) -> {lead_id: set(signals)}` lets
the seam inject them from the conversation/segment store without this module
importing it. Pure stdlib otherwise.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

from .model import AudienceSpec
from ..reporting.store import ReportingStore
from ..reporting.model import FactCall, LeadStatus

log = logging.getLogger("voice_ops.whatsapp.audience")


def _lead_id_of(fact: FactCall) -> str:
    """A stable per-lead id. The W14 FactCall is keyed per-call (no lead_id column),
    so we derive a stable per-lead key:
      1. an explicit `lead_id` if a future row carries one;
      2. else the masked phone (the lead's stable identity across calls — two calls
         to the same number collapse to one lead, which is what an audience wants);
      3. else the call_id (never empty for a real row)."""
    explicit = (getattr(fact, "lead_id", "") or "").strip()
    if explicit:
        return explicit
    ph = (fact.lead_phone_masked or "").strip()
    return ph or fact.call_id


@dataclass
class ResolvedLead:
    lead_id: str
    name: str = ""
    phone_masked: str = ""
    lead_status: str = "new"
    campaign_id: str = ""
    agent: str = ""
    requested_brochure: bool = False
    follow_up_pending: bool = False


@dataclass
class AudienceResult:
    tenant_id: str
    leads: tuple = ()                        # tuple[ResolvedLead]

    @property
    def lead_ids(self) -> tuple:
        return tuple(l.lead_id for l in self.leads)

    @property
    def count(self) -> int:
        return len(self.leads)

    def breakdown(self) -> dict:
        out = {"hot": 0, "warm": 0, "cold": 0, "dead": 0, "new": 0, "total": len(self.leads)}
        for l in self.leads:
            out[l.lead_status] = out.get(l.lead_status, 0) + 1
        return out


class AudienceResolver:
    """Tenant-scoped resolver over the W14 reporting read-model.

    `signal_hook`  : optional Callable[[tenant_id], dict[lead_id, set[str]]] supplying
                     behavioural signals ('requested_brochure', 'follow_up_pending',
                     a segment name). The seam wires it; tests inject a stub.
    `opted_out_hook`: optional Callable[[tenant_id], set[str]] of suppressed lead_ids
                     (DNC / STOP) — always subtracted when spec.exclude_opted_out."""

    def __init__(self, reporting: Optional[ReportingStore] = None, *,
                 signal_hook: Optional[Callable[[str], dict]] = None,
                 opted_out_hook: Optional[Callable[[str], set]] = None) -> None:
        self.reporting = reporting or ReportingStore()
        self.signal_hook = signal_hook
        self.opted_out_hook = opted_out_hook

    # ----------------------------------------------------------- projection -- #
    def _project(self, tenant_id: str) -> dict:
        """Project FactCall rows to a deduped {lead_id: ResolvedLead}, latest call
        per lead winning the lifecycle/agent/campaign fields. Folds in behavioural
        signals from the hook."""
        signals = {}
        if self.signal_hook:
            try:
                signals = self.signal_hook(tenant_id) or {}
            except Exception as exc:  # noqa: BLE001
                log.info("audience signal_hook failed (ignored): %r", exc)
                signals = {}

        facts = sorted(self.reporting.scan(tenant_id), key=lambda f: f.ts_iso)  # oldest first
        leads: dict[str, ResolvedLead] = {}
        for f in facts:
            lid = _lead_id_of(f)
            if not lid:
                continue
            sig = signals.get(lid, set())
            leads[lid] = ResolvedLead(  # latest (later in sorted order) overwrites
                lead_id=lid,
                name=f.lead_name or leads.get(lid, ResolvedLead(lid)).name,
                phone_masked=f.lead_phone_masked or leads.get(lid, ResolvedLead(lid)).phone_masked,
                lead_status=(f.lead_status.value if isinstance(f.lead_status, LeadStatus) else str(f.lead_status or "new")),
                campaign_id=f.campaign_id or leads.get(lid, ResolvedLead(lid)).campaign_id,
                agent=f.agent or leads.get(lid, ResolvedLead(lid)).agent,
                requested_brochure=("requested_brochure" in sig) or bool(getattr(f, "requested_brochure", False)),
                follow_up_pending=("follow_up_pending" in sig) or bool(f.callback_scheduled and not f.booked),
            )
        # attach the named-segment membership for the predicate to read.
        self._segment_members = {lid: s for lid, s in signals.items()}
        return leads

    # --------------------------------------------------------------- resolve -- #
    def resolve(self, tenant_id: str, spec: AudienceSpec) -> AudienceResult:
        """Resolve `spec` to the deduped lead set. Tenant-scoped + fail-closed."""
        if not (tenant_id or "").strip():
            return AudienceResult(tenant_id="", leads=())
        if spec.is_empty():
            # fail-closed: no positive selection -> empty audience (never 'all').
            return AudienceResult(tenant_id=tenant_id, leads=())

        leads = self._project(tenant_id)
        members = getattr(self, "_segment_members", {})
        temp_set = {str(t).lower() for t in (spec.temps or ())}
        explicit = {str(i).strip() for i in (spec.lead_ids or ()) if str(i).strip()}

        opted = set()
        if spec.exclude_opted_out and self.opted_out_hook:
            try:
                opted = set(self.opted_out_hook(tenant_id) or set())
            except Exception as exc:  # noqa: BLE001
                log.info("audience opted_out_hook failed (ignored): %r", exc)

        out: list[ResolvedLead] = []
        for lid, lead in leads.items():
            if lid in opted:
                continue
            if spec.include_all:
                out.append(lead)
                continue
            # explicit hand-picks always pass (union).
            if lid in explicit:
                out.append(lead)
                continue
            # every set filter must pass (AND across active filters).
            if temp_set and lead.lead_status not in temp_set:
                continue
            if spec.campaign_id and lead.campaign_id != spec.campaign_id:
                continue
            if spec.agent and lead.agent != spec.agent:
                continue
            if spec.requested_brochure and not lead.requested_brochure:
                continue
            if spec.follow_up_pending and not lead.follow_up_pending:
                continue
            if spec.segment and spec.segment not in members.get(lid, set()):
                continue
            # if ANY positive filter was set, this lead passed all of them -> include.
            if (temp_set or spec.campaign_id or spec.agent or spec.requested_brochure
                    or spec.follow_up_pending or spec.segment):
                out.append(lead)

        # union: explicit lead_ids that aren't in the projection still resolve as bare ids.
        present = {l.lead_id for l in out}
        for lid in explicit:
            if lid not in present and lid not in opted:
                out.append(leads.get(lid) or ResolvedLead(lead_id=lid))

        out.sort(key=lambda l: (l.lead_status, l.lead_id))
        return AudienceResult(tenant_id=tenant_id, leads=tuple(out))

    def preview(self, tenant_id: str, spec: AudienceSpec) -> dict:
        """Truthful preview for the panel: count + lifecycle breakdown (mirrors the
        run-campaign audience preview bar)."""
        res = self.resolve(tenant_id, spec)
        return {"count": res.count, "breakdown": res.breakdown(),
                "lead_ids": list(res.lead_ids)}
