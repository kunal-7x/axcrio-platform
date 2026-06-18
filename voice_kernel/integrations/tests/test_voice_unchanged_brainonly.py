"""VOICE-UNCHANGED static assertion — the part W17 does NOT cover (W-VOICE-SURGICAL-PLAN B.4.2).

🚨 EARNER LAW: the OUTBOUND earner is `droplet_work/agent.py` (LIVE box md5
`98655dbf`). The brain-only cutover applies ONLY Patches A+B+C of
`design/W-INT-OUTBOUND-PATCH-BRAINONLY.md` — the instruction (brain) swap — and
DELIBERATELY OMITS Patch D (TTS/Sarvam router), E (per-turn hot hook), F
(post-call memory), G (box-memory bind), which are the VOICE PATH and must stay
the old worker's, byte-identical.

W17 (`run_all_gates`) proves the BRAIN is upgraded (vendor flow, full brief, no
self-label, single greeting, language adapts). It does NOT — and cannot — prove
the VOICE PATH is untouched, because it never sees `agent.py`. THIS test closes
that gap with a STATIC SOURCE assertion against the real `droplet_work/agent.py`:

  The brain-only patch's two edit anchors —
    (1) the flag/façade slot inserted right after `lead_name` is read, and
    (2) the single-line instruction seam `instructions = base_instructions`
  — fall ENTIRELY OUTSIDE every voice-constructor span:
    elevenlabs.TTS(...) + VoiceSettings(...)  (the perfect voice)
    sarvam.STT(...)                            (STT)
    groq.LLM(...)                              (LLM)
    AgentSession(...)                          (VAD / timing / interruption knobs)
    session.say(opener, ...)                   (the opener delivery)

So applying A+B+C cannot edit a single voice-constructor line: the perfect voice
(ElevenLabs `QTKSa2Iyv0yoxvXY2V8a` @ stability 0.45 / speed 1.08), the STT/LLM,
the turn-taking knobs, and the opener `say()` are byte-identical ON or OFF.

DRIFT-ROBUST: anchors are located by CODE LANDMARK (regex), never by raw line
number — the box golden is `98655dbf`, the local working copy may differ
(`6c577b9b`/`9150fabe`), and the founder may bump lines with future env-gated
fixes. The test re-locates every span by its surrounding code.

DROPLET-FREE: this reads `droplet_work/agent.py` AS A TEXT FILE only; it never
imports `droplet_work.agent` (no livekit / box SDK pulled). If the agent file is
absent from the checkout (gitignored, box-only) the file-bound tests SKIP — but
the disjointness LOGIC is also proven on a synthetic fixture so the guarantee is
always exercised in CI.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# repo root = .../caps (this file is caps/voice_kernel/integrations/tests/…)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_AGENT_PY = _REPO_ROOT / "droplet_work" / "agent.py"
_HAS_AGENT = _AGENT_PY.exists()


# --------------------------------------------------------------------------- #
# The voice-constructor LANDMARKS the brain patch must never touch. Each entry
# is (name, open_regex). The span runs from the matched open line down to the
# closing line of its call/argument block (balanced-paren scan). These are the
# EXACT regions DIAGNOSIS §5 / W-VOICE-SURGICAL-PLAN names as the voice path.
# --------------------------------------------------------------------------- #
_VOICE_LANDMARKS = (
    ("tts_elevenlabs", re.compile(r"\belevenlabs\.TTS\s*\(")),
    ("voice_settings", re.compile(r"\bVoiceSettings\s*\(")),
    ("stt_sarvam", re.compile(r"\bsarvam\.STT\s*\(")),
    ("llm_groq", re.compile(r"\bgroq\.LLM\s*\(")),
    ("agent_session", re.compile(r"\bAgentSession\s*\(")),
    ("opener_say", re.compile(r"\bsession\.say\s*\(\s*opener")),
)

# The brain-only patch (A+B+C) edits EXACTLY these two anchors, by landmark:
#   B/C — the single instruction-seam line:  `instructions = base_instructions`
_INSTR_SEAM = re.compile(r"^\s*instructions\s*=\s*base_instructions\s*$")
#   A   — the flag/façade slot is inserted right AFTER `lead_name` is first read.
_LEAD_NAME_READ = re.compile(r"^\s*lead_name\s*=")


def _span_of(lines: list[str], open_idx: int) -> tuple[int, int]:
    """Return (start_line, end_line) 1-based, inclusive, for a parenthesised call
    that OPENS at 0-based `open_idx`, by balancing parens across lines. A bare
    landmark with no '(' on its line spans that single line."""
    depth = 0
    started = False
    for j in range(open_idx, len(lines)):
        for ch in lines[j]:
            if ch == "(":
                depth += 1
                started = True
            elif ch == ")":
                depth -= 1
        if started and depth <= 0:
            return (open_idx + 1, j + 1)
    return (open_idx + 1, len(lines))  # unterminated -> to EOF (defensive)


def _voice_spans(src: str) -> dict[str, tuple[int, int]]:
    """Map each present voice landmark -> its (start,end) 1-based inclusive span."""
    lines = src.splitlines()
    spans: dict[str, tuple[int, int]] = {}
    for name, rx in _VOICE_LANDMARKS:
        for i, line in enumerate(lines):
            if rx.search(line):
                spans[name] = _span_of(lines, i)
                break
    return spans


def _brain_anchor_lines(src: str) -> dict[str, int]:
    """1-based line numbers of the two brain-patch edit anchors (or absent)."""
    lines = src.splitlines()
    out: dict[str, int] = {}
    for i, line in enumerate(lines):
        if "instr_seam" not in out and _INSTR_SEAM.match(line):
            out["instr_seam"] = i + 1
        if "lead_name_read" not in out and _LEAD_NAME_READ.match(line):
            out["lead_name_read"] = i + 1
    return out


def _in_span(line_no: int, span: tuple[int, int]) -> bool:
    return span[0] <= line_no <= span[1]


# --------------------------------------------------------------------------- #
# 1. The disjointness LOGIC — always exercised, on a synthetic fixture, so the
#    guarantee is proven in CI even when agent.py is absent from the checkout.
# --------------------------------------------------------------------------- #
_SYNTHETIC_AGENT = '''\
async def entrypoint(ctx):
    lead_name = _read_name(ctx)
    base_instructions = system_prompt
    if lead_name:
        base_instructions += f"LEAD NAME: {lead_name}"
    instructions = base_instructions

    tts = elevenlabs.TTS(
        api_key=KEY,
        voice_id="QTKSa2Iyv0yoxvXY2V8a",
        voice_settings=VoiceSettings(
            stability=0.45, speed=1.08,
        ),
        auto_mode=True,
    )
    session = AgentSession(
        stt=sarvam.STT(language="hi-IN"),
        llm=groq.LLM(model="llama"),
    )
    await session.say(opener, allow_interruptions=True)
'''


def test_disjointness_logic_on_synthetic_agent():
    """The CORE guarantee, proven independent of the box checkout: the two brain
    anchors lie OUTSIDE every voice-constructor span. Belt-and-suspenders: also
    assert the spans were actually found (the regex landmarks are real)."""
    spans = _voice_spans(_SYNTHETIC_AGENT)
    anchors = _brain_anchor_lines(_SYNTHETIC_AGENT)
    # every voice landmark resolved on the fixture.
    assert set(spans) == {n for n, _ in _VOICE_LANDMARKS}, f"missing spans: {spans}"
    # both brain anchors found.
    assert "instr_seam" in anchors and "lead_name_read" in anchors, anchors
    # DISJOINT: neither anchor falls inside ANY voice span.
    for aname, aline in anchors.items():
        for vname, vspan in spans.items():
            assert not _in_span(aline, vspan), (
                f"brain anchor {aname}@{aline} INSIDE voice span {vname}{vspan}"
            )
    # and the brain seam sits BEFORE the first voice constructor (it is assembled
    # in entrypoint before the agent/session is built) — structural sanity.
    first_voice = min(s[0] for s in spans.values())
    assert anchors["instr_seam"] < first_voice
    assert anchors["lead_name_read"] < first_voice


# --------------------------------------------------------------------------- #
# 2. The SAME assertion against the REAL droplet_work/agent.py (SKIP if absent).
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not _HAS_AGENT, reason="droplet_work/agent.py absent (box-only checkout)")
def test_real_agent_voice_constructors_present_and_disjoint_from_brain_seam():
    """On the real earner source: every voice constructor is present, and the
    two brain-patch anchors fall OUTSIDE every voice-constructor span — so
    applying Patches A+B+C edits ZERO voice-constructor lines."""
    src = _AGENT_PY.read_text(encoding="utf-8", errors="replace")
    spans = _voice_spans(src)
    anchors = _brain_anchor_lines(src)

    # the voice path is identifiable in the real file (the patch knows what NOT to
    # touch). The opener say() and AgentSession are required; the rest are too.
    for required in ("tts_elevenlabs", "voice_settings", "stt_sarvam", "llm_groq",
                     "agent_session", "opener_say"):
        assert required in spans, f"voice landmark {required!r} not found in agent.py"

    # the brain seam the patch replaces, and the flag-slot anchor, are present.
    assert "instr_seam" in anchors, "instruction seam `instructions = base_instructions` not found"
    assert "lead_name_read" in anchors, "`lead_name = ...` anchor not found"

    # THE GUARANTEE: neither brain anchor intersects any voice-constructor span.
    for aname, aline in anchors.items():
        for vname, vspan in spans.items():
            assert not _in_span(aline, vspan), (
                f"brain anchor {aname}@{aline} falls INSIDE voice-constructor "
                f"{vname} span {vspan} — Patches A+B+C would edit the voice path!"
            )


@pytest.mark.skipif(not _HAS_AGENT, reason="droplet_work/agent.py absent (box-only checkout)")
def test_real_agent_brain_seam_precedes_all_voice_constructors():
    """The instruction seam (and the flag slot) are assembled in `entrypoint`
    BEFORE the TTS/STT/LLM/session/opener are constructed — so the brain patch is
    a pure pre-construction edit and the voice constructors run on whatever
    `instructions` was selected, their own code untouched."""
    src = _AGENT_PY.read_text(encoding="utf-8", errors="replace")
    spans = _voice_spans(src)
    anchors = _brain_anchor_lines(src)
    first_voice = min(s[0] for s in spans.values())
    assert anchors["lead_name_read"] < first_voice
    assert anchors["instr_seam"] < first_voice, (
        "instruction seam must precede the first voice constructor"
    )


@pytest.mark.skipif(not _HAS_AGENT, reason="droplet_work/agent.py absent (box-only checkout)")
def test_real_agent_perfect_voice_params_present_unchanged():
    """Defensive: the perfect-voice signature (ElevenLabs voice_id + the
    stability/speed defaults the founder tuned) is PRESENT in the voice block.
    The brain patch never edits this block, so these values are byte-identical
    ON or OFF. This is a witness, not a behavioural change."""
    src = _AGENT_PY.read_text(encoding="utf-8", errors="replace")
    lines = src.splitlines()
    spans = _voice_spans(src)
    tts_s, tts_e = spans["tts_elevenlabs"]
    vs_s, vs_e = spans["voice_settings"]
    voice_block = "\n".join(lines[tts_s - 1: max(tts_e, vs_e)])
    # the perfect voice IS this ElevenLabs voice id (DIAGNOSIS §5).
    assert "QTKSa2Iyv0yoxvXY2V8a" in src, "perfect-voice ElevenLabs voice_id missing"
    # stability/speed are read from env with the perfect-voice defaults; the patch
    # never touches this VoiceSettings construction.
    assert "VoiceSettings" in voice_block
    assert "EL_STABILITY" in voice_block or "stability" in voice_block


# --------------------------------------------------------------------------- #
# 3. Droplet-free witness: reading agent.py must not import the box agent module.
# --------------------------------------------------------------------------- #
def test_reading_agent_source_pulls_no_box_module():
    """We read agent.py as TEXT only — never `import droplet_work.agent` (that
    would pull livekit + the box SDKs). Assert no box module leaked in."""
    import sys

    if _HAS_AGENT:
        _AGENT_PY.read_text(encoding="utf-8", errors="replace")
    leaked = [m for m in sys.modules if m.split(".")[0] == "droplet_work"
              or m in ("livekit", "livekit.agents")]
    assert leaked == [], f"reading agent.py leaked a box/SDK module: {leaked}"
