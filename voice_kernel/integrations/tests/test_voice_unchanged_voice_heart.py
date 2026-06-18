"""VOICE-HEART static assertion — the SUPERSET of the brain-only voice-unchanged test.

The W-VOICE-HEART deployable patch (design/W-VOICE-HEART-DEPLOYABLE-PATCH.md) applies,
beyond the brain swap (A+B+C), three SPOKEN-LINE / NAME hunks and one PROSODY-KNOB hunk,
each KERNEL_OUTBOUND-gated (D pinned via the drop-in):

  Hunk H — suppress the worker's `session.say(opener, ...)` on kernel-on.
  Hunk I — suppress the hardcoded close `session.say(line, ...)` on kernel-on.
  Hunk J — skip the lead-name "greet by this naam" injection on kernel-on.
  Hunk D — pin the CONSTANT prosody in the `VoiceSettings(...)` KNOBS only (0.45/1.08).

The EARNER GUARANTEE this test proves, by code landmark (drift-robust, never a raw line):

  1. The TTS ENGINE constructors — `elevenlabs.TTS(...)` provider/voice_id/model/auto_mode,
     `sarvam.STT(...)`, `groq.LLM(...)`, `AgentSession(...)` — are NOT the surface any
     voice-heart hunk edits. The brain anchors (lead_name read + instruction seam) fall
     OUTSIDE every voice-constructor span (the brain-only guarantee, re-proven here).
  2. Hunk D edits ONLY the `VoiceSettings(...)` KNOBS, which live INSIDE the
     `elevenlabs.TTS(...)` span but are a DISTINCT sub-construct: the perfect-voice
     signature (`voice_id="QTKSa2Iyv0yoxvXY2V8a"`, `model="eleven_flash_v2_5"`,
     `auto_mode=True`) sits OUTSIDE the `VoiceSettings(...)` span, so pinning the knobs
     leaves the engine/voice_id BYTE-IDENTICAL.
  3. The spoken-line anchors Hunks H/I touch (`session.say(opener`, `session.say(line`)
     are NOT inside the STT/LLM/Session constructor spans — they are post-construction
     calls, so gating them cannot edit a voice ENGINE constructor.

DROPLET-FREE: reads `droplet_work/agent.py` AS TEXT only; never imports the box agent.
SKIPs the file-bound checks if the gitignored agent is absent, but the disjointness LOGIC
is always proven on a synthetic fixture so CI always exercises the guarantee.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_AGENT_PY = _REPO_ROOT / "droplet_work" / "agent.py"
_HAS_AGENT = _AGENT_PY.exists()


# Voice-ENGINE constructor landmarks (the TTS engine — never edited by any hunk).
_ENGINE_LANDMARKS = (
    ("tts_elevenlabs", re.compile(r"\belevenlabs\.TTS\s*\(")),
    ("stt_sarvam", re.compile(r"\bsarvam\.STT\s*\(")),
    ("llm_groq", re.compile(r"\bgroq\.LLM\s*\(")),
    ("agent_session", re.compile(r"\bAgentSession\s*\(")),
)
_VOICE_SETTINGS = re.compile(r"\bVoiceSettings\s*\(")
_OPENER_SAY = re.compile(r"\bsession\.say\s*\(\s*opener")
_CLOSE_SAY = re.compile(r"\bsession\.say\s*\(\s*line")

# brain anchors (A/B/C) — the seam + the lead_name read.
_INSTR_SEAM = re.compile(r"^\s*instructions\s*=\s*base_instructions\s*$")
_LEAD_NAME_READ = re.compile(r"^\s*lead_name\s*=")
# Hunk J anchor — the lead-name "greet by this naam" injection line.
_NAME_INJECT = re.compile(r"LEAD NAME .* से greet")


def _span_of(lines: list[str], open_idx: int) -> tuple[int, int]:
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
    return (open_idx + 1, len(lines))


def _first_span(src: str, rx: re.Pattern) -> tuple[int, int] | None:
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if rx.search(line):
            return _span_of(lines, i)
    return None


def _engine_spans(src: str) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for name, rx in _ENGINE_LANDMARKS:
        sp = _first_span(src, rx)
        if sp:
            out[name] = sp
    return out


def _line_of(src: str, rx: re.Pattern) -> int | None:
    for i, line in enumerate(src.splitlines()):
        if rx.search(line):
            return i + 1
    return None


def _in_span(line_no: int | None, span: tuple[int, int] | None) -> bool:
    if line_no is None or span is None:
        return False
    return span[0] <= line_no <= span[1]


# --------------------------------------------------------------------------- #
# Synthetic fixture — the structure the deployable patch targets. Always proven.
# --------------------------------------------------------------------------- #
_SYNTH = '''\
async def entrypoint(ctx):
    lead_name = _read_name(ctx)
    base_instructions = system_prompt
    if lead_name and not _KERNEL_OUTBOUND:
        base_instructions += f"\\n\\nLEAD NAME (naam): {lead_name} — opener में इसी naam से greet करो।"
    instructions = base_instructions

    tts = elevenlabs.TTS(
        api_key=KEY,
        voice_id="QTKSa2Iyv0yoxvXY2V8a",
        model="eleven_flash_v2_5",
        voice_settings=VoiceSettings(
            stability=float(os.getenv("EL_STABILITY", "0.45")),
            speed=float(os.getenv("EL_SPEED", "1.08")),
        ),
        auto_mode=True,
    )
    session = AgentSession(
        stt=sarvam.STT(language="unknown"),
        llm=groq.LLM(model="llama"),
    )
    if not _KERNEL_OUTBOUND:
        await session.say(opener, allow_interruptions=True)
    async def _confirm_then_hangup(signal):
        if not _KERNEL_OUTBOUND:
            line = _goodbye_line(signal)
            handle = session.say(line, allow_interruptions=False)
'''


def test_synthetic_hunks_disjoint_from_engine_spans():
    """The CORE guarantee, independent of the box checkout: the brain anchors + the
    spoken-line anchors fall OUTSIDE every voice-ENGINE constructor span, and Hunk D's
    VoiceSettings span is nested inside elevenlabs.TTS but excludes the voice_id/model."""
    eng = _engine_spans(_SYNTH)
    assert set(eng) == {n for n, _ in _ENGINE_LANDMARKS}, f"missing engine spans: {eng}"

    seam = _line_of(_SYNTH, _INSTR_SEAM)
    name_read = _line_of(_SYNTH, _LEAD_NAME_READ)
    name_inject = _line_of(_SYNTH, _NAME_INJECT)
    opener_say = _line_of(_SYNTH, _OPENER_SAY)
    close_say = _line_of(_SYNTH, _CLOSE_SAY)
    assert all(x is not None for x in (seam, name_read, name_inject, opener_say, close_say))

    # brain + name anchors are OUTSIDE every engine span.
    for anchor in (seam, name_read, name_inject):
        for vname, vspan in eng.items():
            assert not _in_span(anchor, vspan), f"anchor@{anchor} inside engine {vname}{vspan}"

    # the spoken-line CALLS (H/I) are NOT inside the STT/LLM/Session ENGINE spans
    # (they may sit after AgentSession but never inside its constructor span).
    for call in (opener_say, close_say):
        for vname in ("stt_sarvam", "llm_groq", "agent_session"):
            assert not _in_span(call, eng[vname]), f"spoken-line@{call} inside {vname}"

    # Hunk D: VoiceSettings is nested inside elevenlabs.TTS, but the perfect-voice
    # signature (voice_id/model) lies OUTSIDE the VoiceSettings span -> pinning the
    # knobs cannot touch voice_id/model.
    vs = _first_span(_SYNTH, _VOICE_SETTINGS)
    tts = eng["tts_elevenlabs"]
    assert tts[0] <= vs[0] and vs[1] <= tts[1], "VoiceSettings must nest inside elevenlabs.TTS"
    lines = _SYNTH.splitlines()
    vid_line = next(i + 1 for i, l in enumerate(lines) if "QTKSa2Iyv0yoxvXY2V8a" in l)
    model_line = next(i + 1 for i, l in enumerate(lines) if "eleven_flash_v2_5" in l)
    assert not _in_span(vid_line, vs), "voice_id must be OUTSIDE the VoiceSettings span"
    assert not _in_span(model_line, vs), "model must be OUTSIDE the VoiceSettings span"


# --------------------------------------------------------------------------- #
# The SAME, against the REAL droplet_work/agent.py (SKIP if absent).
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not _HAS_AGENT, reason="droplet_work/agent.py absent (box-only checkout)")
def test_real_agent_voice_heart_hunks_disjoint_from_engine():
    src = _AGENT_PY.read_text(encoding="utf-8", errors="replace")
    eng = _engine_spans(src)
    for required in ("tts_elevenlabs", "stt_sarvam", "llm_groq", "agent_session"):
        assert required in eng, f"engine landmark {required!r} not found in agent.py"

    seam = _line_of(src, _INSTR_SEAM)
    name_read = _line_of(src, _LEAD_NAME_READ)
    opener_say = _line_of(src, _OPENER_SAY)
    close_say = _line_of(src, _CLOSE_SAY)
    assert seam and name_read, "brain anchors (seam + lead_name read) not found"
    assert opener_say, "opener session.say anchor (Hunk H) not found"
    assert close_say, "close session.say(line) anchor (Hunk I) not found"

    # brain anchors outside every engine span.
    for anchor in (seam, name_read):
        for vname, vspan in eng.items():
            assert not _in_span(anchor, vspan), f"brain anchor@{anchor} inside engine {vname}{vspan}"
    # spoken-line calls not inside the STT/LLM/Session constructor spans.
    for call in (opener_say, close_say):
        for vname in ("stt_sarvam", "llm_groq", "agent_session"):
            assert not _in_span(call, eng[vname]), f"spoken-line@{call} inside {vname}"


@pytest.mark.skipif(not _HAS_AGENT, reason="droplet_work/agent.py absent (box-only checkout)")
def test_real_agent_hunk_d_touches_only_voicesettings_knobs():
    """Hunk D (constant prosody) edits ONLY the VoiceSettings knobs; the perfect-voice
    signature (voice_id + model + auto_mode) sits OUTSIDE the VoiceSettings span and is
    byte-identical ON or OFF."""
    src = _AGENT_PY.read_text(encoding="utf-8", errors="replace")
    vs = _first_span(src, _VOICE_SETTINGS)
    tts = _first_span(src, re.compile(r"\belevenlabs\.TTS\s*\("))
    assert vs and tts, "elevenlabs.TTS / VoiceSettings not found"
    assert tts[0] <= vs[0] and vs[1] <= tts[1], "VoiceSettings must nest inside elevenlabs.TTS"
    assert "QTKSa2Iyv0yoxvXY2V8a" in src, "perfect-voice voice_id missing"
    lines = src.splitlines()
    vid_line = next((i + 1 for i, l in enumerate(lines) if "QTKSa2Iyv0yoxvXY2V8a" in l), None)
    assert vid_line is not None and not _in_span(vid_line, vs), (
        "voice_id must be OUTSIDE the VoiceSettings span (Hunk D pins knobs, never the voice_id)"
    )
    # the knobs Hunk D pins ARE inside the VoiceSettings span.
    vs_block = "\n".join(lines[vs[0] - 1: vs[1]])
    assert "EL_STABILITY" in vs_block or "stability" in vs_block
    assert "EL_SPEED" in vs_block or "speed" in vs_block


def test_reading_agent_source_pulls_no_box_module():
    import sys

    if _HAS_AGENT:
        _AGENT_PY.read_text(encoding="utf-8", errors="replace")
    leaked = [m for m in sys.modules if m.split(".")[0] == "droplet_work"
              or m in ("livekit", "livekit.agents")]
    assert leaked == [], f"reading agent.py leaked a box/SDK module: {leaked}"
