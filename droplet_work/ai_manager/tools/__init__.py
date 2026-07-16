"""workforce.tools — the ToolRegistry: name -> ToolSpec(schema, fn, scopes, side_effecting, money).

Each tool is a TYPED function over the existing platform API/handlers, tagged with a permission scope
+ a risk class. We REUSE the existing endpoints (campaigns/leads/calls/run/whatsapp/contacts/wallet/
billing/brain-retrieve) — no duplicated business logic. The live catalog reaches caller.py over the
authenticated localhost loopback (transport.py, dormant-until AIWF_SERVICE_TOKEN); the StubTools catalog
is an in-memory mirror with the same names so the offline test runs with zero socket.

risk_class: 'safe' (read-only / internal-metered) | 'risky' (spend/bulk/destructive/export/price/refund).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class ToolSpec:
    name: str                       # == the scope name (e.g. "contacts.read", "whatsapp.send")
    description: str                # PRESCRIPTIVE about WHEN to call (Opt 4.8 under-reaches by default)
    scopes: tuple[str, ...]         # the policy scopes this tool requires (default-deny)
    fn: Callable[..., dict]         # the typed handler: fn(args: dict, ctx) -> result dict
    side_effecting: bool = False    # writes / sends / mutates
    money: bool = False             # can incur EXTERNAL spend (ad budget / invoice)
    risk_class: str = "safe"        # safe | risky
    schema: dict = field(default_factory=dict)  # JSON-schema for args (advisory validation)
    # required_slots: the args that MUST be filled before this tool can run. The AI-Manager brain
    # (state_machine S4.5 ELICIT / chat ELICIT) holds a PendingCommand and asks the user for any of
    # these that the NLU did not extract — multi-turn slot-filling — instead of failing/clarifying.
    # ADVISORY to the runner (it still re-enforces its own gates); AUTHORITATIVE to the elicitation loop.
    required_slots: tuple[str, ...] = ()


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def required_slots_for(self, name: str) -> tuple[str, ...]:
        """The declared required_slots for a tool (() if unknown). Drives the brain's ELICIT loop."""
        spec = self._tools.get(name)
        return tuple(spec.required_slots) if spec else ()

    def for_scopes(self, allowed: frozenset | set) -> list[ToolSpec]:
        """The tools whose required scopes are ALL inside the allowed set (what the LLM is shown)."""
        out = []
        for t in self._tools.values():
            if set(t.scopes) <= set(allowed):
                out.append(t)
        return out

    def describe(self, allowed: frozenset | set) -> list[dict]:
        return [{"name": t.name, "description": t.description, "risk_class": t.risk_class,
                 "money": t.money, "schema": t.schema} for t in self.for_scopes(allowed)]


def build_registry(mode: str = "stub") -> ToolRegistry:
    """mode='stub' (offline, in-memory StubTools) | 'live' (loopback catalog, dormant until token).
    Returns a populated ToolRegistry."""
    reg = ToolRegistry()
    if mode == "live":
        from .catalog import register_live
        register_live(reg)
    else:
        from .stub_tools import register_stub
        register_stub(reg)
    return reg
