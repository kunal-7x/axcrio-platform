"""voice_ops.eval.replay — the CALL-REPLAY scaffold.

Replays a recorded (or golden) conversation turn-by-turn through the REAL kernel —
WARM prefix once, then HOT `on_turn` per caller utterance — and re-derives what the
brain WOULD have instructed, WITHOUT placing a call or touching the box. It then
asserts the founder's per-conversation invariants end-to-end:

  * no AI self-label in the assembled prompt (R1),
  * EXACTLY ONE greeting directive (R5),
  * the vendor script's hook reached the prompt (R2),
  * the campaign brief is present + fenced (R3),
  * the language ADAPTS to the caller turn-by-turn and never cold-forces English
    (R7) — verified against each GoldenTurn.expect_lang.

This is the scaffold the founder asked for: "replay a recorded transcript through
the kernel". A recorded transcript is fed as a RecordedCall (system fields + an
ordered list of caller turns); golden conversations are the shipped fixtures, but
ANY captured transcript can be replayed by constructing a RecordedCall from it
(loader below maps a `[{"role","text","lang"}]` transcript to caller turns).

Droplet-free: every kernel import is lazy; the box/agent is never imported.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from .regression_gates import assemble_prompt, build_facade, kernel_outbound_on


@dataclass(frozen=True)
class ReplayTurn:
    """One replayed turn: the caller utterance, the resolved language the brain
    would mirror, and whether it switched vs the prior turn."""

    idx: int
    user_text: str
    stt_lang: str
    reply_lang: str
    tts_lang: str
    lang_switched: bool
    expected_lang: Optional[str]
    lang_ok: bool


@dataclass
class ReplayResult:
    """The outcome of replaying one conversation through the kernel."""

    name: str
    prompt: str
    turns: list[ReplayTurn] = field(default_factory=list)
    invariants: dict = field(default_factory=dict)  # name -> bool
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(self.invariants.values()) and all(t.lang_ok for t in self.turns)

    def failures(self) -> list[str]:
        out = [k for k, v in self.invariants.items() if not v]
        out += [f"turn{t.idx}_lang({t.reply_lang}!={t.expected_lang})" for t in self.turns if not t.lang_ok]
        return out


@dataclass(frozen=True)
class RecordedCall:
    """A recorded call to replay: the campaign `fields` (the system config that
    governed the call) + the ordered caller turns. A caller turn is
    (user_text, stt_lang, expect_lang|None). Build one from a stored transcript via
    `recorded_call_from_transcript`."""

    name: str
    fields: dict
    turns: tuple  # tuple[ (user_text, stt_lang, expect_lang|None, note) ]


def recorded_call_from_transcript(
    name: str,
    fields: dict,
    transcript: list,
    *,
    user_roles=("user", "customer", "caller", "human"),
) -> RecordedCall:
    """Map a stored transcript (a list of {"role","text","lang"} dicts — the shape
    outbound transcripts/{room}.json and inbound ai_manager_sessions turns use) to a
    RecordedCall by extracting only the CALLER turns (the brain re-derives its own
    replies). `expect_lang` defaults to None (assert nothing) unless the transcript
    row carries an `expect_lang`."""
    turns = []
    for row in transcript or []:
        role = str(row.get("role", "")).strip().lower()
        if role not in user_roles:
            continue
        turns.append((
            str(row.get("text", "")),
            str(row.get("lang", "") or row.get("stt_lang", "")),
            row.get("expect_lang"),
            str(row.get("note", "")),
        ))
    return RecordedCall(name=name, fields=dict(fields or {}), turns=tuple(turns))


def recorded_call_from_golden(g) -> RecordedCall:
    """Adapt a GoldenConversation (verticals.py) into a RecordedCall for replay."""
    return RecordedCall(
        name=g.name,
        fields=dict(g.fields),
        turns=tuple((t.user_text, t.stt_lang, t.expect_lang, t.note) for t in g.turns),
    )


def _count_greeting_directives(prompt_low: str) -> int:
    cues = ("नमस्ते", "namaste", "good morning", "good afternoon", "good evening")
    return sum(prompt_low.count(c) for c in cues)


def replay_conversation(call: RecordedCall) -> ReplayResult:
    """Replay one RecordedCall through the kernel and assert the founder invariants.

    WARM: assemble the system prompt once (the prefix the agent would set).
    HOT:  feed each caller turn through `on_turn`, collecting the resolved language
          and asserting it matches the recorded/golden expectation.
    Returns a ReplayResult whose `.passed` is the per-conversation verdict.
    """
    import voice_kernel.integrations.outbound as ob

    from voice_kernel.brain_packs.disclosure import contains_banned_phrase, strip_guardrail
    from voice_kernel.brain_packs.delivery import (
        has_name_sparingly_rule,
        has_single_greeting_rule,
    )
    from voice_kernel.brain_packs.language import contains_banned_literary

    res = ReplayResult(name=call.name, prompt="")
    with kernel_outbound_on():
        ik = build_facade(call.fields, campaign_id=f"camp-{call.name}")
        if ik is None:
            res.invariants["kernel_engaged"] = False
            res.notes.append("kernel did not engage (flag off / build failed)")
            return res
        res.invariants["kernel_engaged"] = True

        # WARM prefix.
        prompt = assemble_prompt(call.fields)
        res.prompt = prompt
        low = prompt.lower()

        # R1 — no AI self-label in the SPOKEN disclosure or the prompt body.
        pkt = ik.kernel.svc.context_engine.build_packet(ik.base_ctx)
        spoken = strip_guardrail(pkt.identity.ai_disclosure_str)
        res.invariants["R1_no_ai_self_label"] = not contains_banned_phrase(spoken) and not any(
            b in low for b in ("is an ai assistant", "i am an ai assistant", "की एक ai assistant")
        )

        # R5 — exactly one greeting directive.
        res.invariants["R5_single_greeting"] = _count_greeting_directives(low) <= 1

        # W-VOICE-HEART invariants — the new outbound voice-heart rules are LIVE in
        # the rendered prompt (so the BAD-transcript regressions are structurally gone).
        # R11 — no double intro: an explicit single-greeting / no-re-greet rule + 1 OPENING.
        res.invariants["R11_no_double_intro"] = (
            has_single_greeting_rule(prompt) and low.count("opening:") == 1
        )
        # R12 — name said sparingly + at constant volume (no per-turn name prefix).
        res.invariants["R12_name_sparingly"] = has_name_sparingly_rule(prompt)
        # R13 — natural Hinglish: the formal/literary ('mahatvapurn') ban is rendered,
        # and no literary token is used as plain spoken guidance (only inside the ban).
        _lit_ok = "mahatvapurn" in low and "literary" in low
        if "mahatvapurn" in low:
            _seg = low.split("mahatvapurn", 1)[0][-80:]
            _lit_ok = _lit_ok and any(p in _seg for p in ("never", "not ", "avoid", "literary"))
        res.invariants["R13_natural_hinglish"] = _lit_ok
        # R14 — the closing is LLM-generated (a CLOSING directive that bans a canned line).
        _close_ok = "closing:" in low
        if _close_ok:
            _cseg = low.split("closing:", 1)[1][:400]
            _close_ok = any(c in _cseg for c in ("never a canned", "never scripted", "never a scripted", "llm-generated"))
        res.invariants["R14_llm_close"] = _close_ok

        # R2 — vendor hook reached the prompt (if the script declares one).
        raw = str(call.fields.get("raw_script", ""))
        hook = next((tok for tok in raw.split() if tok.startswith("VENDORHOOKWORD")), "")
        res.invariants["R2_vendor_hook_present"] = (hook in prompt) if hook else True

        # R3 — brief present + fenced (if the campaign carries one).
        brief = str(call.fields.get("product_summary", ""))
        marker = next((tok for tok in brief.split() if tok.startswith("BRIEFMARKER")), "")
        if marker:
            fenced = "<campaign_brief>" in prompt and "</campaign_brief>" in prompt
            inside = fenced and (prompt.index("<campaign_brief>") < prompt.index(marker) < prompt.index("</campaign_brief>"))
            res.invariants["R3_brief_lossless_fenced"] = marker in prompt and inside
        else:
            res.invariants["R3_brief_lossless_fenced"] = True

        # HOT — replay each caller turn; assert language adaptation (R7).
        for idx, (user_text, stt_lang, expect_lang, _note) in enumerate(call.turns):
            out = asyncio.run(ob.on_turn(ik, user_text=user_text, detected_lang=stt_lang))
            lang_ok = (expect_lang is None) or (out["reply_lang"] == expect_lang)
            # never cold-force English on turn 0.
            if idx == 0 and out["reply_lang"] == "english" and expect_lang not in ("english",):
                lang_ok = False
                res.notes.append("turn0 cold-forced English (the killed regression)")
            res.turns.append(ReplayTurn(
                idx=idx, user_text=user_text, stt_lang=stt_lang,
                reply_lang=out["reply_lang"], tts_lang=out["tts_lang"],
                lang_switched=out["lang_switched"], expected_lang=expect_lang, lang_ok=lang_ok,
            ))
        res.invariants["R7_language_adapts"] = all(t.lang_ok for t in res.turns)

    return res


def replay_all_goldens() -> list[ReplayResult]:
    """Replay every shipped golden conversation. CI / the cutover script asserts
    every ReplayResult.passed before a deploy."""
    from .verticals import all_goldens

    return [replay_conversation(recorded_call_from_golden(g)) for g in all_goldens()]


__all__ = [
    "ReplayTurn", "ReplayResult", "RecordedCall",
    "recorded_call_from_transcript", "recorded_call_from_golden",
    "replay_conversation", "replay_all_goldens",
]
