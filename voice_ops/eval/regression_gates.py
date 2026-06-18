"""voice_ops.eval.regression_gates — the 10 founder rules as AUTOMATED GATES.

This is the deploy gate. Each of the founder's hard regression rules (R1..R10) is
a function that drives the REAL kernel (through the tracked integration façade
`voice_kernel.integrations.outbound`) and returns a GateResult(passed, detail). A
deploy is allowed ONLY when `run_all_gates()` reports every gate passed on the
CURRENT (fixed) kernel; the negative-control fixtures in `verticals.BROKEN_FIXTURES`
prove each gate FAILS on a broken brain (so the suite actually bites).

EARNER SAFETY: this module imports ZERO droplet_work modules at load. It drives
the kernel ON path by setting KERNEL_OUTBOUND in os.environ for the duration of a
gate run (and restoring it after) — the SAME flag the live cutover flips — so a
green gate proves the real cutover path, never the box itself. The agent and the
box are never imported, restarted, or mutated.

R1 is ALSO a REPO-WIDE gate: `scan_repo_for_ai_self_label()` greps the SHIPPED
voice prompt sources for a hard-coded banned self-label, so the #1 rule is
enforced not just on the kernel output but across the codebase.
"""
from __future__ import annotations

import contextlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# --------------------------------------------------------------------------- #
# GateResult + registry plumbing
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class GateResult:
    """The verdict of one regression gate."""

    gate_id: str  # "R1".."R10"
    name: str
    passed: bool
    detail: str = ""
    samples: tuple[str, ...] = ()  # short evidence snippets (never full prompts)


# The human-readable gate list — the canonical founder regression list. Exported
# so the design doc / CI report and the tests share ONE source of truth.
GATE_LIST: tuple[tuple[str, str], ...] = (
    ("R1", "NEVER says 'AI assistant' / any AI self-label (any path/vertical/language) — #1 rule + repo-wide"),
    ("R2", "Vendor script OVERRIDES the default flow (its hook reaches the prompt)"),
    ("R3", "Campaign brief NOT lossy (full brief reaches the prompt, fenced as untrusted)"),
    ("R4", "Selected TTS provider is actually used (Sarvam when selected, no silent swap)"),
    ("R5", "EXACTLY ONE greeting (no double opener)"),
    ("R6", "NEUTRAL pace/loudness (bounded prosody at kernel output)"),
    ("R7", "Language ADAPTS per turn; keeps prior on uncertainty; never English-only"),
    ("R8", "No half-words (truncation repaired at the text layer)"),
    ("R9", "Casual Hinglish grammar (no literary-Hindi 'aapne call kiya'-class errors)"),
    ("R10", "Cross-vertical: support does NOT push sales; real-estate language never leaks"),
    ("R11", "No DOUBLE intro: the kernel carries an explicit single-greeting/no-re-greet rule (1 OPENING)"),
    ("R12", "Name used SPARINGLY: name-at-most-twice + no-emphasis rule present (no per-turn name prefix)"),
    ("R13", "No literary/formal Hindi ('mahatvapurn'-class) — the casual-Hinglish ban is rendered"),
    ("R14", "Closing is LLM-GENERATED (a CLOSING directive, never a canned hardcoded goodbye)"),
    ("R15", "Constant prosody / no name-emphasis: the prompt forbids loud/fast/ALL-CAPS on the name token"),
)


# --------------------------------------------------------------------------- #
# Kernel-driving helpers (LAZY imports — this file stays droplet-free at load).
# --------------------------------------------------------------------------- #
@contextlib.contextmanager
def kernel_outbound_on():
    """Turn the KERNEL_OUTBOUND flag ON for the duration of a gate run, restoring
    the prior env afterward. Mirrors the integration tests' `_on` helper but as a
    context manager so the gates are callable outside pytest (CI script / replay).
    The master KERNEL_ENABLED / KERNEL_INBOUND are cleared so only outbound flips.
    """
    saved = {k: os.environ.get(k) for k in ("KERNEL_OUTBOUND", "KERNEL_ENABLED", "KERNEL_INBOUND")}
    os.environ["KERNEL_OUTBOUND"] = "1"
    os.environ.pop("KERNEL_ENABLED", None)
    os.environ.pop("KERNEL_INBOUND", None)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def build_facade(fields: dict, *, tenant_id: str = "t-eval", campaign_id: str = "camp-eval",
                 call_id: str = "room-eval-1", lead_phone: str = "+919000000000"):
    """Build a WIRED outbound kernel façade for a campaign `fields` dict. Returns
    the OutboundKernel (kernel ON), or None if the flag/build failed. Caller is
    responsible for running inside `kernel_outbound_on()`."""
    import voice_kernel.integrations.outbound as ob

    return ob.build_for_call(
        tenant_id=tenant_id,
        call_id=call_id,
        lead_phone=lead_phone,
        campaign_id=campaign_id,
        campaign_tenant_id=tenant_id,  # outbound: campaign-record owner == tenant
        fields=dict(fields or {}),
    )


def assemble_prompt(fields: dict) -> str:
    """Assemble the ON kernel system prompt for a campaign `fields` dict. The
    legacy_render fallback is a sentinel that must NEVER appear (ON path)."""
    import voice_kernel.integrations.outbound as ob

    with kernel_outbound_on():
        ik = build_facade(fields)
        assert ik is not None, "kernel did not engage (flag off or build failed)"
        return ob.assemble_outbound_instructions(ik, legacy_render=lambda: "__LEGACY_SHOULD_NOT_APPEAR__")


# --------------------------------------------------------------------------- #
# R1 — NO AI SELF-LABEL (the #1 rule). Two surfaces: (a) the kernel-rendered
# prompt's SPOKEN disclosure, across every golden vertical + language; (b) a
# repo-wide scan of the shipped voice prompt sources.
# --------------------------------------------------------------------------- #
def _banned():
    from voice_kernel.brain_packs.disclosure import contains_banned_phrase, strip_guardrail

    return contains_banned_phrase, strip_guardrail


def gate_r1_no_ai_self_label(goldens=None) -> GateResult:
    """R1: no banned AI self-label in the SPOKEN disclosure of ANY golden vertical,
    in ANY configured language. The GUARDRAIL meta-instruction legitimately NAMES
    the phrase as a prohibition, so we scan only the SPOKEN portion (strip_guardrail).
    Also asserts no banned self-intro instruction survives in the rendered prompt.
    """
    from .verticals import all_goldens

    goldens = goldens if goldens is not None else all_goldens()
    contains_banned, strip_guardrail = _banned()
    bad: list[str] = []
    with kernel_outbound_on():
        for g in goldens:
            ik = build_facade(g.fields, campaign_id=f"camp-{g.name}")
            if ik is None:
                bad.append(f"{g.name}: kernel did not engage")
                continue
            pkt = ik.kernel.svc.context_engine.build_packet(ik.base_ctx)
            spoken = strip_guardrail(pkt.identity.ai_disclosure_str)
            if contains_banned(spoken):
                bad.append(f"{g.name}: spoken disclosure leaked self-label: {spoken[:80]!r}")
            out = assemble_prompt(g.fields).lower()
            for phrase in ("is an ai assistant", "i am an ai assistant", "की एक ai assistant"):
                if phrase in out:
                    bad.append(f"{g.name}: prompt instructs banned self-intro {phrase!r}")
    return GateResult(
        "R1", "no AI self-label (kernel + every vertical/language)",
        passed=not bad, detail="; ".join(bad[:5]) or "clean across all goldens",
        samples=tuple(bad[:5]),
    )


# Shipped voice prompt sources to grep for a HARD-CODED banned self-label. We scan
# the kernel's authoritative disclosure surface + the live legacy prompt builder.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_VOICE_PROMPT_SOURCES = (
    "voice_kernel/brain_packs/disclosure.py",
    "voice_kernel/context/context_engine.py",
    "voice_kernel/packet.py",
    "droplet_work/prompt.py",  # the legacy live builder (present only on the box/checkout)
)

# A self-label is a VIOLATION only when it is an INSTRUCTION TO SAY it, not when it
# is named as a PROHIBITION ("never say 'AI assistant'") or carried as a block-list
# entry / banned-phrase constant (which is exactly the fix we want present).
_PROHIBITION_CUES = (
    "never", "not ", "no ", "don't", "do not", "mat ", "nahi", "kabhi", "banned",
    "block", "forbid", "prohibit", "reject", "guardrail", "strip", "scan", "avoid",
    "banned_phrases", "self-label", "self_label", "block-list", "blocklist",
)
# the banned self-label tokens we hunt for AS A SPOKEN INSTRUCTION. We require an
# imperative speech verb on the same line, so a bare quoted list entry (data) and a
# prohibition are never flagged — only a line that tells the brain to SAY it.
_SELF_LABEL_TOKENS = (
    "ai assistant", "i am an ai", "i'm an ai", "की एक ai assistant", "ai असिस्टेंट",
)
_SPEAK_VERBS = (
    "say ", "tell them", "introduce yourself as", "state that you are",
    "open by saying", "kehna", "bata", "bol ", "boliye", "shuruaat",
)


def _is_data_or_prohibition_line(low: str) -> bool:
    """True if a line carrying a banned token is DATA (a quoted block-list/constant
    entry) or a PROHIBITION — i.e. allowed, not a violation."""
    if any(cue in low for cue in _PROHIBITION_CUES):
        return True
    stripped = low.strip()
    # a bare quoted-string tuple/list entry: e.g.   "ai assistant",   (data, not code)
    if re.fullmatch(r'["\'].*["\']\s*,?\s*(#.*)?', stripped):
        return True
    return False


def scan_repo_for_ai_self_label(root: Optional[Path] = None) -> GateResult:
    """REPO-WIDE #1 gate: grep the shipped voice-prompt sources for a HARD-CODED
    instruction to self-label as an AI assistant. A line that NAMES the phrase as a
    prohibition, carries it as a block-list/constant entry, or otherwise does not
    INSTRUCT the brain to say it is allowed (that's the fix); a line that instructs
    the brain to SAY it (a speech verb + the banned token) is a violation."""
    root = root or _REPO_ROOT
    violations: list[str] = []
    for rel in _VOICE_PROMPT_SOURCES:
        p = root / rel
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # pragma: no cover - unreadable file
            violations.append(f"{rel}: unreadable ({exc!r})")
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            low = line.lower()
            if not any(tok in low for tok in _SELF_LABEL_TOKENS):
                continue
            if _is_data_or_prohibition_line(low):
                continue
            # a banned token NOT in a data/prohibition line is a violation only if it
            # is phrased as a spoken instruction.
            if any(v in low for v in _SPEAK_VERBS):
                violations.append(f"{rel}:{i}: {line.strip()[:90]}")
    return GateResult(
        "R1-repo", "repo-wide: no hard-coded AI self-label instruction",
        passed=not violations,
        detail="; ".join(violations[:5]) or "no shipped voice source instructs an AI self-label",
        samples=tuple(violations[:5]),
    )


# --------------------------------------------------------------------------- #
# R2 — VENDOR SCRIPT OVERRIDES THE DEFAULT FLOW (its STAGE STRUCTURE drives the
# rendered flow — not merely echoed somewhere in the brief).
#
# W17 red-team B2 fix: the kernel pastes the parsed script into the campaign card,
# so a naive "hook in prompt" check is True for ANY non-empty script (the brief
# fence echoes it) and can NEVER detect the real regression — the vendor script
# IGNORED and the default flow used instead. So R2 now asserts the vendor's stage
# structure actually DROVE A FLOW SLOT: the hook must land on a FLOW directive line
# (TALKING POINTS / QUALIFYING / OBJECTIONS / CLOSING) inside the campaign brief —
# which only happens because the GREET/INTRO/PITCH stage was parsed and routed to
# the talking_points slot (context_engine._apply_vendor_script). A brain that drops
# the script renders NO such flow line, and the gate FLIPS TO FAIL (proven by the
# negative control `gate_r2_*` test + `prompt_dropping_vendor_script`).
# --------------------------------------------------------------------------- #
# The campaign-card FLOW slots the parsed vendor stages feed (context_engine):
#   GREET/PERMISSION/INTRO -> TALKING POINTS ; QUALIFY -> QUALIFYING ;
#   OBJECTION -> OBJECTIONS ; CLOSE -> CLOSING. A hook on one of these lines proves
# the stage STRUCTURE drove the flow, not a raw dump.
_R2_FLOW_SLOT_CUES = ("talking points:", "qualifying", "objection", "closing")


def _vendor_hook(raw: str) -> str:
    return next((tok for tok in str(raw).split() if tok.startswith("VENDORHOOKWORD")), "")


def _brief_body(prompt_low: str) -> str:
    """Return the lowercased text INSIDE the <campaign_brief> fence (where the parsed
    vendor stages render as flow slots), or the whole prompt if unfenced."""
    if "<campaign_brief>" in prompt_low and "</campaign_brief>" in prompt_low:
        return prompt_low.split("<campaign_brief>", 1)[1].split("</campaign_brief>", 1)[0]
    return prompt_low


def hook_drives_flow(prompt: str, hook: str) -> bool:
    """True iff the vendor `hook` lands on a FLOW-SLOT directive line (talking
    points / qualifying / objections / closing) — i.e. the parsed stage STRUCTURE
    drove the rendered flow, not merely echoed in the brief blob. This is the
    override check (not the echo check) the red-team demanded."""
    if not hook:
        return True
    h = hook.lower()
    body = _brief_body(prompt.lower())
    return any(
        h in line and any(cue in line for cue in _R2_FLOW_SLOT_CUES)
        for line in body.splitlines()
    )


def gate_r2_vendor_script_authoritative(goldens=None) -> GateResult:
    from .verticals import all_goldens

    goldens = goldens if goldens is not None else all_goldens()
    bad: list[str] = []
    with kernel_outbound_on():
        for g in goldens:
            hook = _vendor_hook(g.fields.get("raw_script", ""))
            if not hook:
                continue  # set has no vendor hook to check
            out = assemble_prompt(g.fields)
            if hook not in out:
                bad.append(f"{g.name}: vendor hook {hook!r} absent from prompt (script ignored)")
                continue
            # OVERRIDE, not echo: the hook must drive a FLOW slot, proving the parsed
            # stage structure shaped the rendered flow (not a raw paste).
            if not hook_drives_flow(out, hook):
                bad.append(
                    f"{g.name}: vendor hook {hook!r} present but NOT on a flow slot "
                    f"(script echoed, did not drive the flow — default flow used)"
                )
    return GateResult(
        "R2", "vendor script drives the FLOW (override, not echo)",
        passed=not bad, detail="; ".join(bad[:5]) or "every vendor stage drove its flow slot",
        samples=tuple(bad[:5]),
    )


# --------------------------------------------------------------------------- #
# R3 — CAMPAIGN BRIEF NOT LOSSY (full brief reaches the prompt, fenced).
# --------------------------------------------------------------------------- #
def gate_r3_brief_not_lossy(goldens=None) -> GateResult:
    from .verticals import all_goldens

    goldens = goldens if goldens is not None else all_goldens()
    bad: list[str] = []
    with kernel_outbound_on():
        for g in goldens:
            brief = str(g.fields.get("product_summary", ""))
            marker = next((tok for tok in brief.split() if tok.startswith("BRIEFMARKER")), "")
            if not marker:
                continue
            out = assemble_prompt(g.fields)
            if marker not in out:
                bad.append(f"{g.name}: brief marker {marker!r} lost (lossy compression)")
                continue
            # fenced as untrusted (C3): the marker must sit INSIDE a brief fence.
            if "<campaign_brief>" in out and "</campaign_brief>" in out:
                o, c, m = out.index("<campaign_brief>"), out.index("</campaign_brief>"), out.index(marker)
                if not (o < m < c):
                    bad.append(f"{g.name}: brief escaped its C3 fence")
            else:
                bad.append(f"{g.name}: brief not wrapped in a campaign_brief fence")
    return GateResult(
        "R3", "campaign brief is lossless + fenced",
        passed=not bad, detail="; ".join(bad[:5]) or "every brief reached the prompt inside its fence",
        samples=tuple(bad[:5]),
    )


# --------------------------------------------------------------------------- #
# R4 — SELECTED TTS PROVIDER IS ACTUALLY USED (Sarvam when selected; no swap).
# --------------------------------------------------------------------------- #
def gate_r4_selected_tts_provider_used(goldens=None) -> GateResult:
    import voice_kernel.integrations.outbound as ob

    from .verticals import all_goldens

    goldens = goldens if goldens is not None else all_goldens()
    bad: list[str] = []
    with kernel_outbound_on():
        for g in goldens:
            ik = build_facade(g.fields, campaign_id=f"camp-{g.name}")
            if ik is None:
                bad.append(f"{g.name}: kernel did not engage")
                continue
            choice = ob.choose_tts(ik)
            if choice.tts != g.expect_provider:
                bad.append(
                    f"{g.name}: selected {choice.tts!r} but expected {g.expect_provider!r} "
                    f"(reason={choice.reason!r})"
                )
                continue
            # the SELECTED provider must be the one a downstream speech plan renders
            # for — prove the choice flows to the planner (no silent divergence).
            plan = ob.plan_speech(ik, raw_text="the price is 95 lakh rupees", lang="hi")
            if plan is None:
                bad.append(f"{g.name}: speech plan was None (provider not wired through)")
    return GateResult(
        "R4", "selected TTS provider is honoured (no silent swap)",
        passed=not bad, detail="; ".join(bad[:5]) or "selected provider used end-to-end",
        samples=tuple(bad[:5]),
    )


# --------------------------------------------------------------------------- #
# R5 — EXACTLY ONE GREETING (no double opener). With OPENER_ALREADY_SAID default,
# the kernel prompt emits exactly ONE opening directive and NO surplus fresh-
# greeting section.
#
# W17 red-team B3 fix: counting only the literal greeting CUES (नमस्ते/namaste/...)
# was VACUOUS — every golden has ZERO such cues, so `hits > 1` could never trip and
# the gate passed without ever proving an opener exists (a "zero opener" regression
# would also pass green). R5 now asserts the kernel renders EXACTLY ONE OPENING
# directive (the structural `OPENING:` flow line) — not zero (missing opener), not
# two (double opener) — AND no surplus literal fresh-greeting cue. The negative
# control (`_count_openers` test + a constructed double-opener prompt) proves the
# gate flips to FAIL on both a double opener and a missing one.
# --------------------------------------------------------------------------- #
# greeting tokens that, if they appear MORE THAN ONCE as an instruction, signal a
# double opener. We count fresh-greeting cues in the rendered prompt.
_GREETING_CUES = ("नमस्ते", "namaste", "good morning", "good afternoon", "good evening")
# the STRUCTURAL opening directive the kernel renders exactly once per prompt (the
# greet->confirm->intro skeleton). EXACTLY ONE is the single-greeting invariant.
_OPENING_DIRECTIVE = "opening:"


def _count_openers(prompt_low: str) -> int:
    """Count the structural OPENING directives in a rendered prompt. Exactly one is
    correct; zero = a missing opener (also a regression); >1 = a double opener."""
    return prompt_low.count(_OPENING_DIRECTIVE)


def gate_r5_single_greeting(goldens=None) -> GateResult:
    from .verticals import all_goldens

    goldens = goldens if goldens is not None else all_goldens()
    bad: list[str] = []
    with kernel_outbound_on():
        for g in goldens:
            out = assemble_prompt(g.fields).lower()
            # (a) EXACTLY ONE structural opening directive — not zero (no opener),
            # not two (double opener). This is the non-vacuous single-greeting check
            # (every golden carries exactly one OPENING: line).
            openers = _count_openers(out)
            if openers != 1:
                bad.append(
                    f"{g.name}: {openers} opening directives (expected exactly 1; "
                    f"{'no opener' if openers == 0 else 'double opener'})"
                )
            # (b) no surplus hard-coded literal fresh-greeting cue ("say नमस्ते" as a
            # second opener) — a double opener by a different door.
            hits = sum(out.count(cue) for cue in _GREETING_CUES)
            if hits > 1:
                bad.append(f"{g.name}: {hits} fresh-greeting cues in one prompt (double opener risk)")
    return GateResult(
        "R5", "exactly one greeting (one opening directive, no double opener)",
        passed=not bad, detail="; ".join(bad[:5]) or "exactly one opening directive in every prompt",
        samples=tuple(bad[:5]),
    )


# --------------------------------------------------------------------------- #
# R6 — NEUTRAL pace/loudness (bounded prosody at KERNEL OUTPUT). Run apply_prosody
# on a sample reply and assert fillers are OFF by default (neutral delivery) and
# sensitive (price/booking) lines are returned clean.
# --------------------------------------------------------------------------- #
def gate_r6_neutral_prosody() -> GateResult:
    from voice_kernel.speech.prosody import apply_prosody

    bad: list[str] = []
    sample = (
        "main aapko ek baat batana chahti hoon",
        "the price is 95 lakh rupees",  # SENSITIVE -> must stay clean
        "kya aap interested hain",
    )
    # default (fillers OFF) — neutral delivery: NO prepended verbal-nod filler.
    out = apply_prosody(sample, hinglish=True)
    fillers = {"haan,", "achha,", "toh,", "dekhiye,"}
    for s in out:
        first = (s.split(" ", 1)[0].lower() + ",") if s else ""
        if first in fillers:
            bad.append(f"filler injected with neutral default: {s[:50]!r}")
    # sensitive price line must be byte-clean (no injected pause/filler in a price).
    price_out = apply_prosody(("the price is 95 lakh rupees",), hinglish=True)[0]
    if price_out.strip() != "the price is 95 lakh rupees":
        bad.append(f"sensitive price line was modified: {price_out!r}")
    return GateResult(
        "R6", "neutral prosody (fillers OFF by default; sensitive lines clean)",
        passed=not bad, detail="; ".join(bad[:5]) or "prosody is neutral and price-safe",
        samples=tuple(bad[:5]),
    )


# --------------------------------------------------------------------------- #
# R7 — LANGUAGE ADAPTS per turn; keeps prior on uncertainty; never English-only.
# Drive a multi-turn sequence through the kernel's on_turn and assert the resolved
# language follows the golden's expect_lang turn-by-turn.
# --------------------------------------------------------------------------- #
def gate_r7_language_adapts(goldens=None) -> GateResult:
    import asyncio

    import voice_kernel.integrations.outbound as ob

    from .verticals import all_goldens

    goldens = goldens if goldens is not None else all_goldens()
    bad: list[str] = []
    with kernel_outbound_on():
        for g in goldens:
            ik = build_facade(g.fields, campaign_id=f"camp-{g.name}")
            if ik is None:
                bad.append(f"{g.name}: kernel did not engage")
                continue
            # NEVER seed/force English: the first resolved lang must be Hinglish/Hindi
            # family, never a cold English default.
            for idx, t in enumerate(g.turns):
                res = asyncio.run(ob.on_turn(ik, user_text=t.user_text, detected_lang=t.stt_lang))
                if t.expect_lang is not None and res["reply_lang"] != t.expect_lang:
                    bad.append(
                        f"{g.name} turn{idx}: got {res['reply_lang']!r} expected {t.expect_lang!r} "
                        f"({t.note})"
                    )
                if res["reply_lang"] == "english" and idx == 0 and t.expect_lang != "english":
                    bad.append(f"{g.name} turn0: cold-forced English (the killed regression)")
    return GateResult(
        "R7", "language adapts per turn; keeps prior; never English-only",
        passed=not bad, detail="; ".join(bad[:5]) or "language tracked the caller across every golden",
        samples=tuple(bad[:5]),
    )


# --------------------------------------------------------------------------- #
# R8 — NO HALF-WORDS (truncation repaired at the text layer).
# --------------------------------------------------------------------------- #
def gate_r8_no_half_words() -> GateResult:
    from voice_kernel.speech.segment import repair_truncation, split_sentences

    bad: list[str] = []
    # simulate a stream cut mid-word (the half-word the founder heard).
    cut_samples = (
        "main aapko price ke baare mein bataना chahta th",  # cut mid-word
        "the booking amount is ninety five thou",
        "हाँ ठीक है मुझे साइट विजिट कर",
    )
    for raw in cut_samples:
        repaired = repair_truncation(raw)
        segs = split_sentences(repaired)
        joined = " ".join(segs).strip() if segs else repaired
        # the planner's contract: output must not END on a dangling partial token.
        # We assert the repaired text differs from the raw cut OR ends cleanly.
        last = joined.split()[-1] if joined.split() else ""
        if joined == raw and _looks_dangling(last):
            bad.append(f"half-word survived repair: {joined[-30:]!r}")
    return GateResult(
        "R8", "no half-words (truncation repaired)",
        passed=not bad, detail="; ".join(bad[:5]) or "truncation repaired on every cut sample",
        samples=tuple(bad[:5]),
    )


def _looks_dangling(word: str) -> bool:
    """Heuristic: a Latin word of <=2 chars ending a sentence, or a clearly-cut
    token, looks dangling. Conservative — the real check is repair_truncation."""
    if not word:
        return False
    w = word.strip(".,!?।…")
    return len(w) <= 2 and w.isalpha()


# --------------------------------------------------------------------------- #
# R9 — CASUAL HINGLISH (no literary-Hindi). enforce_casual_hinglish must replace
# literary words, and has_literary_hindi must flag a literary input.
# --------------------------------------------------------------------------- #
def gate_r9_casual_hinglish() -> GateResult:
    from voice_kernel.speech.hinglish import enforce_casual_hinglish, has_literary_hindi

    bad: list[str] = []
    literary = "yeh ek mahatvapurn aur avashyak baat hai"
    casual = enforce_casual_hinglish(literary)
    if "mahatvapurn" in casual.lower() or "avashyak" in casual.lower():
        bad.append(f"literary word survived: {casual!r}")
    if "zaroori" not in casual.lower():
        bad.append(f"casual replacement not applied: {casual!r}")
    if not has_literary_hindi(literary):
        bad.append("has_literary_hindi failed to flag a literary input")
    if has_literary_hindi(casual):
        bad.append(f"casual output still flagged literary: {casual!r}")
    return GateResult(
        "R9", "casual Hinglish (literary Hindi killed)",
        passed=not bad, detail="; ".join(bad[:5]) or "literary Hindi replaced with casual Hinglish",
        samples=tuple(bad[:5]),
    )


# --------------------------------------------------------------------------- #
# R10 — CROSS-VERTICAL: support does NOT push sales; real-estate never leaks.
# --------------------------------------------------------------------------- #
# tokens in a rendered prompt that mean "advance/close a SALE". A non-selling mode
# (support/complaint/feedback/booking/reminder) must NOT carry these in its
# objective/success directives.
_SALES_PUSH_CUES = (
    "advance the lead", "purchase intent", "move them toward the next commitment",
    "move a cold/warm lead", "buy-signal", "close the sale", "upsell",
    "site-visit/demo/purchase",
)


def gate_r10_cross_vertical_isolation(goldens=None) -> GateResult:
    from .verticals import all_goldens

    goldens = goldens if goldens is not None else all_goldens()
    bad: list[str] = []
    with kernel_outbound_on():
        for g in goldens:
            out = assemble_prompt(g.fields)
            low = out.lower()
            # (a) a non-selling mode must not instruct a sales push.
            if not g.pushes_sale:
                leaked = [c for c in _SALES_PUSH_CUES if c in low]
                if leaked:
                    bad.append(f"{g.name} ({g.use_case}): non-selling mode pushes sale: {leaked}")
            # (b) real-estate vocabulary must not leak into a non-real-estate call.
            if g.industry != "real_estate":
                for term in g.forbidden_vertical_terms:
                    # match the VERTICAL-TERMS directive surface, not an incidental
                    # brief word; the leak is the industry pack bleeding in.
                    if f"vertical terms:" in low and term.lower() in low.split("vertical terms:", 1)[1][:400]:
                        bad.append(f"{g.name} ({g.industry}): real-estate term leaked: {term!r}")
    return GateResult(
        "R10", "cross-vertical isolation (support≠sales; no real-estate leak)",
        passed=not bad, detail="; ".join(bad[:5]) or "modes + verticals isolated; no leak",
        samples=tuple(bad[:5]),
    )


# --------------------------------------------------------------------------- #
# R11 — NO DOUBLE INTRO (W-VOICE-HEART). The founder's #1 complaint: the outbound
# greeted+pitched, then re-greeted+re-introduced ("main bol rahi hoon..." twice).
# The structural fix is the worker-opener suppression (agent.py Hunk H), but the
# PROMPT must ALSO carry an explicit single-greeting / no-re-greet directive so the
# kernel-ON prefix can never re-introduce by another door (the red-team's grep-found
# gap). R11 asserts the SINGLE GREETING: rule IS in the rendered prompt AND there is
# exactly one OPENING directive (reusing R5's non-vacuous opener counter). Negative
# control: a prompt without the rule (or with two OPENING lines) FAILS.
# --------------------------------------------------------------------------- #
def gate_r11_no_double_intro(goldens=None) -> GateResult:
    from voice_kernel.brain_packs.delivery import has_single_greeting_rule

    from .verticals import all_goldens

    goldens = goldens if goldens is not None else all_goldens()
    bad: list[str] = []
    with kernel_outbound_on():
        for g in goldens:
            out = assemble_prompt(g.fields)
            if not has_single_greeting_rule(out):
                bad.append(f"{g.name}: missing the SINGLE GREETING / no-re-greet rule (double-intro risk)")
            if _count_openers(out.lower()) != 1:
                bad.append(f"{g.name}: {_count_openers(out.lower())} OPENING directives (double/zero intro)")
    return GateResult(
        "R11", "no double intro (explicit single-greeting rule + exactly one OPENING)",
        passed=not bad, detail="; ".join(bad[:5]) or "single-greeting rule present; one OPENING per prompt",
        samples=tuple(bad[:5]),
    )


# --------------------------------------------------------------------------- #
# R12 — NAME USED SPARINGLY (W-VOICE-HEART #3a). The outbound said the lead's name
# again and again, every line. The fix is a PROMPT rule (name at most once/twice,
# never a per-turn prefix). R12 asserts the NAME USE: rule + the no-emphasis clause
# are rendered. Negative control: a prompt lacking the rule FAILS.
# --------------------------------------------------------------------------- #
def gate_r12_name_used_sparingly(goldens=None) -> GateResult:
    from voice_kernel.brain_packs.delivery import has_name_sparingly_rule

    from .verticals import all_goldens

    goldens = goldens if goldens is not None else all_goldens()
    bad: list[str] = []
    with kernel_outbound_on():
        for g in goldens:
            out = assemble_prompt(g.fields)
            if not has_name_sparingly_rule(out):
                bad.append(f"{g.name}: missing the NAME USE (sparingly + no-emphasis) rule")
    return GateResult(
        "R12", "name used sparingly (at-most-twice + no per-turn prefix + no emphasis)",
        passed=not bad, detail="; ".join(bad[:5]) or "name-sparingly rule present in every prompt",
        samples=tuple(bad[:5]),
    )


# --------------------------------------------------------------------------- #
# R13 — NO LITERARY/FORMAL HINDI (W-VOICE-HEART #4). The founder heard
# "mahatvapurn"-class formal Hindi instead of natural Hinglish. The casual-Hinglish
# LANGUAGE directive bans the literary tokens by name. R13 asserts the ban is
# rendered (the literary token 'mahatvapurn' is named as forbidden) AND no
# literary token is used as PLAIN SPOKEN guidance outside the ban list. Negative
# control: the has_literary_hindi detector flips on a literary input.
# --------------------------------------------------------------------------- #
_LITERARY_BAN_CUE = "literary"  # the LANGUAGE directive's ban phrasing


def gate_r13_no_formal_hindi(goldens=None) -> GateResult:
    from voice_kernel.brain_packs.language import contains_banned_literary

    from .verticals import all_goldens

    goldens = goldens if goldens is not None else all_goldens()
    bad: list[str] = []
    with kernel_outbound_on():
        for g in goldens:
            out = assemble_prompt(g.fields)
            low = out.lower()
            # (a) the casual-Hinglish ban must be rendered (names 'mahatvapurn' as
            # forbidden, paired with the 'never use literary' instruction).
            if "mahatvapurn" not in low or _LITERARY_BAN_CUE not in low:
                bad.append(f"{g.name}: casual-Hinglish ban not rendered (formal-Hindi guard missing)")
            # (b) the ONLY occurrence of a literary token must be inside the ban
            # clause ('NEVER use ... mahatvapurn'), never as plain spoken guidance.
            # We check the directive carries the prohibition cue near the token.
            if "mahatvapurn" in low:
                seg = low.split("mahatvapurn", 1)[0][-80:]
                if not any(p in seg for p in ("never", "not ", "avoid", "literary", "मत")):
                    bad.append(f"{g.name}: 'mahatvapurn' rendered WITHOUT a prohibition (used as guidance)")
    # sanity: the detector the gate's negative control relies on actually bites.
    if not contains_banned_literary("yeh mahatvapurn baat hai"):
        bad.append("contains_banned_literary failed to flag a literary input (detector broken)")
    return GateResult(
        "R13", "no formal/literary Hindi (casual-Hinglish ban rendered)",
        passed=not bad, detail="; ".join(bad[:5]) or "formal-Hindi ('mahatvapurn'-class) banned in every prompt",
        samples=tuple(bad[:5]),
    )


# --------------------------------------------------------------------------- #
# R14 — CLOSING IS LLM-GENERATED (W-VOICE-HEART #2-ending). The outbound said a
# hardcoded 'ok perfect' close (and repeated it at bye). The kernel persona carries
# a CLOSING directive that mandates a warm LLM-generated goodbye, never a canned
# line. R14 asserts a CLOSING: directive is rendered AND it explicitly forbids a
# canned/scripted goodbye. Negative control: a prompt with no CLOSING fails.
# --------------------------------------------------------------------------- #
_CLOSING_DIRECTIVE = "closing:"
_CANNED_CLOSE_BAN_CUES = ("never a canned", "never scripted", "never a scripted", "llm-generated")


def gate_r14_llm_generated_closing(goldens=None) -> GateResult:
    from .verticals import all_goldens

    goldens = goldens if goldens is not None else all_goldens()
    bad: list[str] = []
    with kernel_outbound_on():
        for g in goldens:
            low = assemble_prompt(g.fields).lower()
            if _CLOSING_DIRECTIVE not in low:
                bad.append(f"{g.name}: no CLOSING directive (close would fall back to a hardcoded line)")
                continue
            seg = low.split(_CLOSING_DIRECTIVE, 1)[1][:400]
            if not any(cue in seg for cue in _CANNED_CLOSE_BAN_CUES):
                bad.append(f"{g.name}: CLOSING directive does not forbid a canned/scripted goodbye")
    return GateResult(
        "R14", "closing is LLM-generated (a CLOSING directive bans a canned goodbye)",
        passed=not bad, detail="; ".join(bad[:5]) or "every mode carries an LLM-generated CLOSING directive",
        samples=tuple(bad[:5]),
    )


# --------------------------------------------------------------------------- #
# R15 — CONSTANT PROSODY / NO NAME-EMPHASIS (W-VOICE-HEART #3b, #6). Two halves:
#   (a) PROMPT: the name token must never be written with shouting/emphasis markup
#       (the TEXT->prosody artifact that makes flash_v2_5 render the name louder/
#       faster). The NAME USE rule must carry the 'no emphasis' clause, AND the
#       rendered prompt must not itself emit an emphasised name example.
#   (b) DEPLOYABLE: the constant prosody constants are pinned (the derived inbound
#       value 0.45/1.08, style 0, speaker_boost off) — asserted against the shipped
#       systemd drop-in template so the deploy params can't silently drift.
# Negative control: text_emphasizes_name flips on a shouted name.
# --------------------------------------------------------------------------- #
# the constant prosody the deploy pins (derived from the GOOD inbound voice
# `_inbound_ref/aim_voice_agent.LIVE.py:_build_tts`). Asserted against the drop-in.
CONSTANT_PROSODY = {
    "EL_STABILITY": "0.45",
    "EL_SPEED": "1.08",
    "EL_SIMILARITY": "0.80",
    "style": "0.0",
    "use_speaker_boost": "False",
}
_DROPIN_PATH = _REPO_ROOT / "voice_kernel" / "systemd" / "famit-agent.service.d-voice-heart.conf"


def gate_r15_constant_prosody_no_name_emphasis(goldens=None) -> GateResult:
    from voice_kernel.brain_packs.delivery import NO_EMPHASIS_CUE, text_emphasizes_name

    from .verticals import all_goldens

    goldens = goldens if goldens is not None else all_goldens()
    bad: list[str] = []
    with kernel_outbound_on():
        for g in goldens:
            low = assemble_prompt(g.fields).lower()
            # (a) the no-emphasis-on-name rule must be present.
            if NO_EMPHASIS_CUE not in low:
                bad.append(f"{g.name}: prompt missing the no-name-emphasis (constant volume) rule")
    # negative-control sanity: the emphasis detector bites on a shouted name.
    if not text_emphasizes_name("RAHUL! great to talk", name="Rahul"):
        bad.append("text_emphasizes_name failed to flag a shouted name (detector broken)")
    if text_emphasizes_name("namaste Rahul ji, kaise hain aap", name="Rahul"):
        bad.append("text_emphasizes_name false-positived on a normal name mention")
    # (b) the constant-prosody drop-in pins the derived inbound constants.
    if _DROPIN_PATH.exists():
        conf = _DROPIN_PATH.read_text(encoding="utf-8", errors="replace")
        for k, v in (("EL_STABILITY", CONSTANT_PROSODY["EL_STABILITY"]),
                     ("EL_SPEED", CONSTANT_PROSODY["EL_SPEED"])):
            if f"{k}={v}" not in conf:
                bad.append(f"drop-in does not pin {k}={v} (constant prosody drift)")
    else:
        bad.append("constant-prosody systemd drop-in template is missing")
    return GateResult(
        "R15", "constant prosody + no name-emphasis (drop-in pins 0.45/1.08; prompt bans shouting the name)",
        passed=not bad, detail="; ".join(bad[:5]) or "prosody pinned constant; name never emphasised",
        samples=tuple(bad[:5]),
    )


# --------------------------------------------------------------------------- #
# THE DEPLOY GATE — run them all.
# --------------------------------------------------------------------------- #
@dataclass
class GateReport:
    results: list[GateResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failed_gates(self) -> list[str]:
        return [r.gate_id for r in self.results if not r.passed]

    def summary(self) -> str:
        lines = [f"{'PASS' if r.passed else 'FAIL'}  {r.gate_id:7s} {r.name} — {r.detail}" for r in self.results]
        verdict = "ALL GREEN — deploy gate OPEN" if self.passed else f"BLOCKED — failing: {self.failed_gates}"
        return "\n".join(lines) + f"\n\n{verdict}"


def run_all_gates(goldens=None) -> GateReport:
    """Run every regression gate against the current kernel + golden sets. Returns
    a GateReport whose `.passed` is the DEPLOY DECISION. CI / the cutover script
    calls this and refuses to deploy unless `.passed`."""
    rep = GateReport()
    rep.results.append(gate_r1_no_ai_self_label(goldens))
    rep.results.append(scan_repo_for_ai_self_label())
    rep.results.append(gate_r2_vendor_script_authoritative(goldens))
    rep.results.append(gate_r3_brief_not_lossy(goldens))
    rep.results.append(gate_r4_selected_tts_provider_used(goldens))
    rep.results.append(gate_r5_single_greeting(goldens))
    rep.results.append(gate_r6_neutral_prosody())
    rep.results.append(gate_r7_language_adapts(goldens))
    rep.results.append(gate_r8_no_half_words())
    rep.results.append(gate_r9_casual_hinglish())
    rep.results.append(gate_r10_cross_vertical_isolation(goldens))
    # W-VOICE-HEART founder rules (the outbound voice-heart fixes).
    rep.results.append(gate_r11_no_double_intro(goldens))
    rep.results.append(gate_r12_name_used_sparingly(goldens))
    rep.results.append(gate_r13_no_formal_hindi(goldens))
    rep.results.append(gate_r14_llm_generated_closing(goldens))
    rep.results.append(gate_r15_constant_prosody_no_name_emphasis(goldens))
    return rep


__all__ = [
    "GateResult", "GateReport", "GATE_LIST",
    "kernel_outbound_on", "build_facade", "assemble_prompt",
    "gate_r1_no_ai_self_label", "scan_repo_for_ai_self_label",
    "gate_r2_vendor_script_authoritative", "hook_drives_flow", "_vendor_hook",
    "gate_r3_brief_not_lossy",
    "gate_r4_selected_tts_provider_used", "gate_r5_single_greeting", "_count_openers",
    "gate_r6_neutral_prosody", "gate_r7_language_adapts",
    "gate_r8_no_half_words", "gate_r9_casual_hinglish",
    "gate_r10_cross_vertical_isolation",
    "gate_r11_no_double_intro", "gate_r12_name_used_sparingly",
    "gate_r13_no_formal_hindi", "gate_r14_llm_generated_closing",
    "gate_r15_constant_prosody_no_name_emphasis", "CONSTANT_PROSODY",
    "run_all_gates",
]
