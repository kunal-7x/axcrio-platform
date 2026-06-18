"""voice_ops.security.docs_scrub — the DOCS-SCRUB target list for the W20 legacy-token retirement.

After the gate is OFF and the secret is rotated, the OLD legacy literal is dead — but it is
still PRINTED in a number of docs/notes across the repo (and, worse, embedded as a hardcoded fallback
in a couple of source files). Leaving the literal lying around is an information-disclosure liability
and a foot-gun (someone copy-pastes it back into a script). This module enumerates exactly WHERE the
literal appears so the runbook can scrub them — WITHOUT this module itself ever printing the literal.

CRITICAL: this file does NOT contain the secret value. It refers to it ONLY by a fingerprint and a
human label. The scrub TARGETS are file paths + a description of what to replace. The runbook does the
actual edits (or a follow-up tracked PR); the source-file fallbacks are addressed by the PATCH DOC.

The fingerprint below lets an operator VERIFY a candidate string is the legacy secret ('does this
match what we're scrubbing?') without us ever embedding the plaintext. It is computed from the value
supplied at runtime (e.g. read from the box .env), never hardcoded.

IMPORT ISOLATION: pure stdlib. ZERO droplet/caller/auth imports.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List, Optional


def legacy_secret_fingerprint(value: str, *, domain: str = "famit-secret") -> str:
    """Non-reversible 12-hex id of a candidate legacy secret — lets the runbook confirm 'this string
    is the one we are retiring' WITHOUT this module ever holding/printing the plaintext."""
    t = (value or "")
    if not t:
        return ""
    return hashlib.sha256((domain + "|" + t).encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class ScrubTarget:
    """One place the legacy literal / its hardcoded fallback lives and must be cleansed."""

    path: str
    kind: str          # "doc" (mentions the literal) | "source_fallback" (hardcoded default) | "env"
    what: str          # human description of the replacement action
    tracked: bool      # in git? (gitignored droplet_work is scrubbed on the box, not via PR)


# Grounded in the EXPLORE findings + repo CLAUDE.md secret inventory.
# NOTE: we describe the targets; we never reproduce the secret string here.
SCRUB_TARGETS: List[ScrubTarget] = [
    # --- source fallbacks (the dangerous ones — a literal default in code) ------------ #
    ScrubTarget(
        "droplet_work/caller.py", "source_fallback",
        "Line ~253 `PW = cfg_get('CALLER_PASS', '<literal>')` — replace the literal default with a "
        "non-secret sentinel that fails closed (e.g. raise if CALLER_PASS unset). Via PATCH DOC.",
        tracked=False,
    ),
    ScrubTarget(
        "droplet_work/config.py", "source_fallback",
        "Line ~19 `PW = get('CALLER_PASS', '<literal>')` — same: drop the hardcoded default. PATCH DOC.",
        tracked=False,
    ),
    ScrubTarget(
        "droplet_work/voice_tools.py", "source_fallback",
        "Lines ~34-38 `_ADMIN_CRED = ... or '<literal>'` loopback cred — replace with AIM_SERVICE_TOKEN "
        "(a provisioned service credential), no literal fallback. PATCH DOC + service-token provision.",
        tracked=False,
    ),
    ScrubTarget(
        "droplet_work/ai_manager_voice_tools.W2.py", "source_fallback",
        "Lines ~44-45 same loopback literal fallback — same fix as voice_tools.py.",
        tracked=False,
    ),
    # --- env (the live value) --------------------------------------------------------- #
    ScrubTarget(
        "/opt/famit-agent/.env", "env",
        "CALLER_PASS=<literal> on the box — rotate via rotation.rotate_caller_pass(); set "
        "LEGACY_TOKEN_MODE=off. Distribute the new value via the secret store, never echo it.",
        tracked=False,
    ),
    # --- docs that PRINT the literal (information disclosure) -------------------------- #
    ScrubTarget(
        "design/control-security.md", "doc",
        "Mentions the literal as the #1 finding — keep the FINDING, replace the literal with "
        "'the legacy static password (retired W20)'.",
        tracked=True,
    ),
    ScrubTarget(
        "CLAUDE.md / MEMORY notes / HANDOFF docs", "doc",
        "Any place quoting the literal password — replace with a reference, never the value. "
        "grep the repo for the literal and the fingerprint, scrub each tracked hit in a follow-up PR.",
        tracked=True,
    ),
    ScrubTarget(
        "TEAMMATE_HANDOVER.md / *ALL_CREDENTIALS.md", "doc",
        "Credential handover docs — replace the static password with 'issued via JWT/Logto; no static "
        "password'. These are gitignored on the box; scrub the local copies.",
        tracked=False,
    ),
]


def scrub_list(*, tracked_only: bool = False) -> List[ScrubTarget]:
    """The scrub worklist. `tracked_only` filters to git-tracked files (the ones a PR can fix; the
    gitignored droplet_work + box .env are scrubbed on the box per the runbook)."""
    if tracked_only:
        return [t for t in SCRUB_TARGETS if t.tracked]
    return list(SCRUB_TARGETS)


def grep_hints(legacy_value: Optional[str] = None) -> List[str]:
    """Operator grep hints for the scrub. We return the SEARCH PATTERNS to run, NOT the secret — if a
    `legacy_value` is supplied we return its fingerprint (to cross-check a hit), never the value."""
    hints = [
        "grep -rIn --exclude-dir=.git 'CALLER_PASS' .   # find every reference to the password env",
        "grep -rIn --exclude-dir=.git 'X-Auth' droplet_work/   # loopback cred header usages",
        "grep -rIn --exclude-dir=.git 'legacy_pw\\|LEGACY_TOKEN' .   # the gate + classification sites",
    ]
    if legacy_value:
        hints.append(
            f"# verify a candidate hit is the retired secret by fingerprint == {legacy_secret_fingerprint(legacy_value)}"
        )
    return hints
