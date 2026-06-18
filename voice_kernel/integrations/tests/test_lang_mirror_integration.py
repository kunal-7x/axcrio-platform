"""Integration test for the PER-TURN ADAPTIVE LANGUAGE MIRROR wired into
on_turn of BOTH voice_kernel.integrations.inbound and .outbound.

The founder fix: mirror the caller's language EVERY turn — Hindi->Hindi,
English->English, switch-back->switch, Hinglish->hinglish — adaptive, never
hardcoded. Proven here over the real per-call kernel façade (flag ON), and proven
TURN-SCOPED (the cached stable prefix never changes when the language flips).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest

import voice_kernel.integrations.inbound as ib
import voice_kernel.integrations.outbound as ob

_FIELDS = {
    "agent_name": "Riya",
    "company_name": "Famit",
    "product_name": "SolarMax",
    "plan": "lean",
    "raw_script": "STAGE GREET: greet warmly. STAGE PITCH: mention the price clearly.",
}


def _build_inbound(monkeypatch):
    monkeypatch.setenv("KERNEL_INBOUND", "1")
    monkeypatch.delenv("KERNEL_ENABLED", raising=False)
    return ib.build_for_call(
        tenant_id="t1", call_id="room-1", caller_id="+910000000000",
        campaign_id="camp-1", campaign_tenant_id="t1", fields=dict(_FIELDS),
    )


def _build_outbound(monkeypatch):
    monkeypatch.setenv("KERNEL_OUTBOUND", "1")
    monkeypatch.delenv("KERNEL_ENABLED", raising=False)
    return ob.build_for_call(
        tenant_id="t1", call_id="room-1", lead_phone="+910000000000",
        campaign_id="camp-1", campaign_tenant_id="t1", fields=dict(_FIELDS),
    )


# --------------------------------------------------------------------------- #
# THE FOUNDER SCENARIO — adaptive per-turn mirror over a full call
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("mod_build", ["inbound", "outbound"])
def test_per_turn_mirror_full_call_sequence(monkeypatch, mod_build):
    """Hindi turn -> reply hindi + tts hi; NEXT English turn -> reply english +
    tts en; switch BACK to Hindi -> hindi again; a Hinglish turn -> hinglish.
    Wired identically into BOTH integrations (one shared brain)."""
    if mod_build == "inbound":
        ik, mod = _build_inbound(monkeypatch), ib
    else:
        ik, mod = _build_outbound(monkeypatch), ob
    assert ik is not None

    # Turn 1 — Hindi.
    out1 = asyncio.run(mod.on_turn(ik, user_text="हाँ बताइए मुझे जानकारी चाहिए",
                                   detected_lang="hindi", history_len=0))
    assert out1["reply_lang"] == "hi"
    assert "USER LANGUAGE: hindi" in (out1["rag_suffix"] or "")

    # Turn 2 — English mid-call (the bug: agent used to stay Hindi). Now it flips.
    out2 = asyncio.run(mod.on_turn(ik, user_text="can you please tell me the price and details",
                                   detected_lang="hindi", history_len=2))
    assert out2["reply_lang"] == "en"
    assert "USER LANGUAGE: english" in (out2["rag_suffix"] or "")

    # Turn 3 — switch BACK to Hindi.
    out3 = asyncio.run(mod.on_turn(ik, user_text="नहीं हिंदी में बात करिए",
                                   detected_lang="hindi", history_len=4))
    assert out3["reply_lang"] == "hi"
    assert "USER LANGUAGE: hindi" in (out3["rag_suffix"] or "")

    # Turn 4 — Hinglish code-mix.
    out4 = asyncio.run(mod.on_turn(ik, user_text="मुझे property visit करनी है site पर",
                                   detected_lang="hindi", history_len=6))
    assert out4["reply_lang"] == "hi"
    assert "USER LANGUAGE: hinglish" in (out4["rag_suffix"] or "")


@pytest.mark.parametrize("mod_build", ["inbound", "outbound"])
def test_mirror_appends_per_turn_directive_not_hardcoded(monkeypatch, mod_build):
    """The per-turn reply instruction is appended (MIRROR: ...) and matches the
    DETECTED language — adaptive, not pinned. English turn carries the English
    instruction; Hindi turn carries the Devanagari instruction."""
    if mod_build == "inbound":
        ik, mod = _build_inbound(monkeypatch), ib
    else:
        ik, mod = _build_outbound(monkeypatch), ob

    out_en = asyncio.run(mod.on_turn(ik, user_text="what is the location please",
                                     detected_lang="hindi"))
    assert "MIRROR:" in (out_en["rag_suffix"] or "")
    assert "English" in (out_en["rag_suffix"] or "")  # english steer

    out_hi = asyncio.run(mod.on_turn(ik, user_text="ठीक है आगे बताओ", detected_lang="english"))
    suffix = out_hi["rag_suffix"] or ""
    assert "MIRROR:" in suffix
    assert any(0x0900 <= ord(c) <= 0x097F for c in suffix)  # Devanagari steer


# --------------------------------------------------------------------------- #
# TURN-SCOPED: the cached STABLE PREFIX never changes when the language flips
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("mod_build", ["inbound", "outbound"])
def test_stable_prefix_unchanged_across_language_switch(monkeypatch, mod_build):
    """Cache-safe: switching language mid-call mutates ONLY the per-turn L5 suffix.
    The cached stable system prefix (assemble_*_instructions) is byte-identical
    before and after the switch — so the Groq prompt-prefix cache is never busted."""
    if mod_build == "inbound":
        ik, mod = _build_inbound(monkeypatch), ib
        assemble = lambda: mod.assemble_inbound_instructions(ik, legacy_render=lambda: "L")
    else:
        ik, mod = _build_outbound(monkeypatch), ob
        assemble = lambda: mod.assemble_outbound_instructions(ik, legacy_render=lambda: "L")

    prefix_before = assemble()
    # Drive a Hindi -> English -> Hindi switch through on_turn.
    asyncio.run(mod.on_turn(ik, user_text="हाँ ठीक है", detected_lang="hindi"))
    asyncio.run(mod.on_turn(ik, user_text="tell me the price please", detected_lang="hindi"))
    asyncio.run(mod.on_turn(ik, user_text="नहीं हिंदी में", detected_lang="english"))
    prefix_after = assemble()

    assert prefix_before == prefix_after, "stable cached prefix must NOT change on a language switch"
    # And the prefix must not carry any per-turn USER LANGUAGE / MIRROR directive.
    assert "USER LANGUAGE:" not in prefix_before
    assert "MIRROR:" not in prefix_before


@pytest.mark.parametrize("mod_build", ["inbound", "outbound"])
def test_off_path_unchanged_inert_dict(monkeypatch, mod_build):
    """Flag OFF (ik=None): on_turn stays the exact inert 3-key dict (byte-identity
    of the OFF turn is preserved — no mirror engages)."""
    mod = ib if mod_build == "inbound" else ob
    monkeypatch.delenv("KERNEL_INBOUND", raising=False)
    monkeypatch.delenv("KERNEL_OUTBOUND", raising=False)
    monkeypatch.delenv("KERNEL_ENABLED", raising=False)
    out = asyncio.run(mod.on_turn(None, user_text="anything at all", detected_lang="hi"))
    assert out == {"reply_lang": "hi", "rag_suffix": None, "speech_plan": None}
