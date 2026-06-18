"""voice_kernel.context.vendor_script — the VendorScriptEngine implementation.

Fixes Founder's #1 complaint: the VENDOR SCRIPT WAS IGNORED. When a vendor
supplies a script, it becomes the AUTHORITATIVE conversation blueprint — the
stage-by-stage flow (greet → confirm/permission → intro → reason → qualify →
pitch → objections → close) is driven by what the VENDOR wrote, overriding the
default framework. When NO script is present, the engine returns "" so the
kernel's default FSM/brain-pack flow runs unchanged.

Two structural safety guarantees (C3):
  1. The script is UNTRUSTED vendor text. `stage_excerpt` returns a plain string,
     but the ContextEngine wraps the WHOLE campaign block (card + any script
     excerpt) in a CAMPAIGN_BRIEF fence, ABOVE which the PLATFORM safety/identity
     layer always sits BY POSITION. Script content can request a tone or a line
     but can NEVER override the platform safety rules (it is positionally and
     typographically below them, marked data-not-instructions).
  2. Forged fence tags inside the script are defanged (text_hygiene.sanitize) so
     the script cannot break out of its fence.

Dynamic variables: the vendor writes `{{lead_name}}`, `{{product}}`, `{{offer}}`,
etc. in their script; `render(vars)` substitutes campaign/lead variables at
assembly time. Unknown placeholders are left intact (never crash, never leak a
raw `{{x}}` as a command — it stays inside the fence as data).

Per-stage segmentation: the engine parses the script into labelled stages (by
heading/keyword) so `stage_excerpt(stage)` returns ONLY the relevant slice for
the current turn (keeps the per-turn prompt small while the full script stays
recallable). If the script has no detectable structure, the WHOLE script is the
GREET/INTRO excerpt (it is still authoritative, just unsegmented).

Pure-stdlib; the engine is constructed with a dict of compiled scripts keyed by
campaign_id (so the hot `stage_excerpt`/`card_overrides` are pure dict reads).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..packet import Stage
from ..tokens import clamp_chars
from .text_hygiene import sanitize

# Stage heading synonyms. We map a vendor's free-text section headers onto the
# kernel Stage enum so a script written in plain language still segments. These
# are GENERIC conversation-stage words, NOT campaign content.
_STAGE_KEYWORDS: dict[Stage, tuple[str, ...]] = {
    Stage.GREET: ("greet", "greeting", "opening", "intro hello", "namaste", "hello", "open"),
    Stage.PERMISSION: ("permission", "confirm", "verify", "right person", "is this", "may i", "time to talk", "busy"),
    Stage.INTRO: ("intro", "introduction", "who we are", "about us", "reason for call", "purpose", "why calling"),
    Stage.QUALIFY: ("qualify", "qualifying", "discovery", "needs", "requirement", "questions", "understand"),
    Stage.OBJECTION: ("objection", "objections", "concern", "rebuttal", "pushback", "if they say"),
    Stage.BOOKING: ("book", "booking", "appointment", "schedule", "site visit", "slot"),
    Stage.CLOSE: ("close", "closing", "ask", "cta", "call to action", "next step", "wrap up", "end"),
    Stage.FOLLOWUP: ("follow up", "follow-up", "followup", "callback", "later"),
}

# A standalone heading line: short, optionally ends-with-colon, nothing after.
_HEADING_RE = re.compile(r"^\s*(?:[#*\-•\d.)\s]*)([A-Za-z][A-Za-z /&'-]{2,40})\s*[:：]?\s*$")
# An INLINE heading: "Label: content on the same line" (the common vendor form,
# e.g. "Permission: Kya aapke paas do minute hain?"). Group 1 = the label,
# group 2 = the content that follows on that line.
_INLINE_HEADING_RE = re.compile(r"^\s*(?:[#*\-•\d.)\s]*)([A-Za-z][A-Za-z /&'-]{2,30})\s*[:：]\s+(\S.*)$")
# {{variable}} placeholders the vendor writes in their script.
_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


@dataclass(frozen=True)
class CompiledScript:
    """A vendor script parsed into stage-labelled segments. Built at save-time."""

    campaign_id: str
    raw: str  # the full sanitized script (authoritative, lossless)
    segments: dict = field(default_factory=dict)  # Stage -> text slice
    overrides: dict = field(default_factory=dict)  # card field overrides (e.g. greeting)
    has_script: bool = False


def _detect_stage(heading: str) -> Stage | None:
    h = heading.strip().lower()
    for stage, kws in _STAGE_KEYWORDS.items():
        for kw in kws:
            if kw in h:
                return stage
    return None


def parse_script(raw: str) -> dict:
    """Segment a free-text vendor script into {Stage: text}. Best-effort: if no
    headings are detected, the whole script lands under GREET (still authoritative,
    just unsegmented). Pure."""
    text = sanitize(raw)
    if not text.strip():
        return {}
    lines = text.split("\n")
    segments: dict[Stage, list[str]] = {}
    current: Stage | None = None
    found_heading = False
    for line in lines:
        # 1. inline "Label: content" — most common vendor form.
        im = _INLINE_HEADING_RE.match(line)
        if im:
            stage = _detect_stage(im.group(1))
            if stage is not None:
                current = stage
                found_heading = True
                segments.setdefault(current, []).append(im.group(2).strip())
                continue
        # 2. standalone heading line ("Greeting", "QUALIFY:", "1. Close").
        m = _HEADING_RE.match(line)
        stage = _detect_stage(m.group(1)) if m else None
        if stage is not None:
            current = stage
            found_heading = True
            segments.setdefault(current, [])
            continue
        if line.strip():
            if current is None:
                current = Stage.GREET  # preamble before the first heading
            segments.setdefault(current, []).append(line)
    if not found_heading:
        # no structure detected — the entire script is the authoritative blueprint,
        # surfaced from the GREET stage onward.
        return {Stage.GREET: text.strip()}
    return {st: "\n".join(ls).strip() for st, ls in segments.items() if "\n".join(ls).strip()}


def compile_script(campaign_id: str, raw_script: str, *, greeting_hint: str = "") -> CompiledScript:
    """Save-time: parse a vendor script into a CompiledScript. Empty/absent script
    -> has_script=False (the kernel's default flow runs). Derives a `greeting`
    card-override from the GREET segment so the OPENER itself is the vendor's."""
    text = sanitize(raw_script)
    if not text.strip():
        return CompiledScript(campaign_id=campaign_id, raw="", segments={}, overrides={}, has_script=False)
    segments = parse_script(text)
    overrides: dict = {}
    greet = segments.get(Stage.GREET, "")
    if greet:
        # the first sentence/line of the GREET segment becomes the greeting override
        # (the opener the vendor actually wrote), unless the vendor set one explicitly.
        first_line = next((ln.strip() for ln in greet.split("\n") if ln.strip()), "")
        overrides["greeting"] = greeting_hint.strip() or first_line
    return CompiledScript(
        campaign_id=campaign_id,
        raw=text,
        segments=segments,
        overrides=overrides,
        has_script=True,
    )


def render_vars(text: str, variables: dict) -> str:
    """Substitute {{var}} placeholders with campaign/lead variables. Unknown
    placeholders are left intact (as fenced data, never as a command). Values are
    sanitized so an injected var value cannot smuggle a fence break-out."""
    if not text or "{{" not in text:
        return text or ""
    vmap = {str(k): sanitize(str(v)) for k, v in (variables or {}).items()}

    def _sub(m: re.Match) -> str:
        key = m.group(1)
        return vmap.get(key, m.group(0))  # leave unknown {{x}} intact

    return _VAR_RE.sub(_sub, text)


class VendorScriptEngineImpl:
    """The W3 VendorScriptEngine: vendor script = authoritative blueprint.

    Constructed with a mapping {campaign_id: CompiledScript} (built at save-time)
    plus an optional {campaign_id: variables} for {{var}} substitution. Hot calls
    (`stage_excerpt`, `card_overrides`) are pure dict reads + render — safe on the
    HOT path. When a campaign has no script, returns "" / {} so the kernel's
    DEFAULT framework runs (greet→confirm→intro→reason→qualify→pitch→objections→
    close from the brain pack / FSM).
    """

    def __init__(self, scripts: dict | None = None, variables: dict | None = None):
        self._scripts: dict[str, CompiledScript] = dict(scripts or {})
        self._vars: dict[str, dict] = dict(variables or {})

    # -- registration helpers (save-time) -----------------------------------
    def register(self, campaign_id: str, raw_script: str, *, variables: dict | None = None, greeting_hint: str = "") -> CompiledScript:
        cs = compile_script(campaign_id, raw_script, greeting_hint=greeting_hint)
        self._scripts[campaign_id] = cs
        if variables is not None:
            self._vars[campaign_id] = dict(variables)
        return cs

    def set_variables(self, campaign_id: str, variables: dict) -> None:
        self._vars[campaign_id] = dict(variables or {})

    def has_script(self, campaign_id: str) -> bool:
        cs = self._scripts.get(campaign_id)
        return bool(cs and cs.has_script)

    # -- Protocol surface ---------------------------------------------------
    def stage_excerpt(self, campaign_id: str, stage: Stage, max_chars: int = 600) -> str:
        """Return the AUTHORITATIVE script excerpt for this stage, with dynamic
        variables substituted, clamped to `max_chars` for the per-turn prompt.

        Empty string when no script (kernel default flow runs). The returned text
        is a SUGGESTED blueprint for the stage; the ContextEngine fences it.
        """
        cs = self._scripts.get(campaign_id)
        if not cs or not cs.has_script:
            return ""  # default framework
        text = cs.segments.get(stage, "")
        if not text and stage in (Stage.GREET, Stage.INTRO):
            # unsegmented script: surface the whole blueprint at the opening stages.
            text = cs.segments.get(Stage.GREET, cs.raw)
        if not text:
            return ""
        text = render_vars(text, self._vars.get(campaign_id, {}))
        return clamp_chars(text, max_chars)

    def card_overrides(self, campaign_id: str) -> dict:
        """Card field overrides derived from the script (e.g. the vendor's own
        greeting becomes the opener). Variables substituted. Empty when no script.
        """
        cs = self._scripts.get(campaign_id)
        if not cs or not cs.has_script:
            return {}
        out = dict(cs.overrides)
        v = self._vars.get(campaign_id, {})
        return {k: render_vars(val, v) if isinstance(val, str) else val for k, val in out.items()}

    def full_blueprint(self, campaign_id: str) -> str:
        """The whole authoritative script (lossless), variables substituted. Used
        by the ContextEngine to surface the flow ordering when assembling, and by
        W4 for recall. Empty when no script."""
        cs = self._scripts.get(campaign_id)
        if not cs or not cs.has_script:
            return ""
        return render_vars(cs.raw, self._vars.get(campaign_id, {}))
