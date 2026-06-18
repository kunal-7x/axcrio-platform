"""voice_ops.compliance — the India Consent & Regulatory Engine (W26 -> W12 seam).

TRACKED + droplet-free. The server-side DIAL-TIME GATE that makes the outbound earner
legally safe to run at volume in India. ONE entry point — `preflight(tenant, lead,
campaign) -> Decision{allow|block|soft, reasons, disclosure_ctx}` — is called from a
single point in the dial loop (design/W12-TELEPHONY-COMPLIANCE-SEAM.md) BEFORE the
wallet hold + SIP originate.

What it enforces (grounded in design/W26-COMPLIANCE-CONSENT-ENGINE.md):
  * DND/NCPR scrub-before-dial (national register cache + local per-tenant suppression).
  * LEGAL calling-window HARD FLOOR — the live default 09:00–21:00 is OUT OF BOUNDS;
    the floor is ~10:00–19:00 (BFSI 08:00–19:00) and a tenant CANNOT widen past it.
  * 140 / 1600 (160) CLI-series check — a plain 10-digit mobile is itself a violation.
  * Consent ledger freshness (TCCCPR place-call + DPDP process-data; explicit=7d) +
    retention TTL — append-only, FORCE-RLS table (mirror of ddl_wallet.sql).
  * The warm Tier-0 disclosure_ctx (brand + purpose + recording cue, NEVER the banned
    "AI assistant") the brain emits FIRST.

Posture: FAIL-CLOSED on Tier A (registration/number/window/consent/DND) — a DB error or
unknown state BLOCKS the dial (never dial on unknown compliance state). FAIL-SOFT on
Tier B (recording/retention) — resolve to the safe policy + continue. Flag-gated
`COMPLIANCE_ENABLED`, DEFAULT OFF — when off, `preflight` returns `allow` with a
`compliance_unenforced=true` marker so the resting build is byte-identical to pre-engine
(enabling it BEFORE DLT/number registration would block 100% of dials).

ZERO droplet_work / agent imports; redis/psycopg2 lazy. Emits W8 events
(voice_kernel.events) when a bus is injected; an emit failure never affects a decision.
"""
from .engine import ComplianceEngine, Decision, DisclosureCtx, preflight  # noqa: F401
from .config import ComplianceConfig  # noqa: F401
