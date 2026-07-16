"""verticals.composer — the pure composer that turns campaign fields into a
multi-vertical / multi-persona / multi-language brain, ADDITIVELY.

This is the ONLY module the live agent calls. Contract (every item is load-bearing
for "never break the perfect system"):

  * enabled()      — master gate. ``FEATURE_VERTICALS`` env, default OFF.
  * fill_fields()  — returns a NEW fields dict with persona/language identity keys
                     filled ONLY where the campaign left them blank. Input is never
                     mutated. When disabled or no vertical -> returns the SAME object.
  * apply_to_prompt() — appends a lean domain directive to an already-built prompt.
                     When disabled or no vertical -> returns the base string unchanged.
                     Cache-safe: a one-time suffix, never a per-turn rewrite.
  * resolve_voice()— PROVIDER-AWARE persona voice. Returns {} unless a persona maps a
                     REAL voice for the active provider. Never emits a cross-namespace
                     id (a Sarvam speaker is never returned for the ElevenLabs path).
  * catalogue()    — the fields/personas/languages catalogue for a UI/HTTP surface.

Every public function is wrapped so an exception degrades to the byte-identical
"off" behaviour. No network, no heavy wheels, no import of the agent/livekit stack.
"""

from __future__ import annotations

import os

from . import languages as lang_mod
from . import overlay
from . import personas as personas_mod
from . import registry

VERSION = "1.0.0"


def _truthy(v) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def enabled() -> bool:
    """Master gate. Default OFF — with this off, every function is byte-identity."""
    return _truthy(os.getenv("FEATURE_VERTICALS", "0"))


def _present(fields: dict, key: str) -> bool:
    """True if the campaign already set a non-empty value for ``key``."""
    v = fields.get(key)
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    return bool(v)


# ── effective (overlay-merged) registry tables ───────────────────────────────
def _eff_fields() -> dict:
    return overlay.fields(registry.FIELDS)


def _eff_personas() -> dict:
    return overlay.personas(personas_mod.PERSONAS)


def _eff_languages() -> dict:
    return overlay.languages(lang_mod.LANGUAGES)


def resolve_profile(fields: dict | None) -> dict | None:
    """Resolve (vertical, sub-option, persona, language) from the campaign fields.

    Returns None when there is no ``vertical`` selected (the byte-identical path) or
    the vertical is unknown. Pure; never raises.
    """
    try:
        f = fields or {}
        vkey = f.get("vertical") or f.get("field") or f.get("industry_use_case")
        field = registry.get_field(vkey, source=_eff_fields()) if vkey else None
        sub = registry.get_sub_option(field, f.get("sub_option") or f.get("use_case")) if field else None

        # persona: explicit persona_key (survives fill_fields overloading `persona` with the
        # prose line) > explicit `persona` selector > sub default > field default.
        p_src = _eff_personas()
        persona = (personas_mod.get_persona(f.get("persona_key"), source=p_src)
                   or personas_mod.get_persona(f.get("persona"), source=p_src)
                   or (personas_mod.get_persona(sub.get("default_persona"), source=p_src) if sub else None)
                   or (personas_mod.get_persona(field.get("default_persona"), source=p_src) if field else None))

        # language: explicit field > field default > None
        l_src = _eff_languages()
        lang = lang_mod.get_language(f.get("language"), source=l_src)
        if not lang and field:
            defs = field.get("default_languages") or []
            lang = lang_mod.get_language(defs[0], source=l_src) if defs else None

        # Three INDEPENDENT axes: a profile exists if ANY of field / persona / language is set,
        # so multi-persona or multi-language works without a vertical (and vice-versa). None only
        # when nothing is selected -> the byte-identical path.
        if not field and not persona and not lang:
            return None
        return {"field": field, "sub": sub, "persona": persona, "language": lang}
    except Exception:  # noqa: BLE001 — resolution must never break a call
        return None


def fill_fields(fields: dict | None) -> dict:
    """Return fields with persona/language IDENTITY keys filled where blank.

    Fills only: ``agent_name``, ``voice_gender``, ``persona`` (free-text line) and
    ``language`` — and ONLY when the campaign left them empty (explicit values always
    win). Does NOT touch ``voice_id`` (that is namespace-sensitive; see resolve_voice).
    Input dict is never mutated. Disabled / no-vertical -> returns the SAME object.
    """
    try:
        if not enabled():
            return fields if fields is not None else {}
        f = fields or {}
        prof = resolve_profile(f)
        if not prof:
            return fields if fields is not None else {}

        out = dict(f)
        persona = prof.get("persona")  # explicit selection > sub/field default
        if persona:
            # Stash the RESOLVED persona key so a later resolve_voice() call (which runs on
            # the post-fill dict, where `persona` has been replaced by prose) still resolves
            # THIS persona's voice — not the vertical default's.
            if not _present(out, "persona_key") and persona.get("key"):
                out["persona_key"] = persona.get("key")
            if not _present(out, "agent_name"):
                out["agent_name"] = persona.get("display") or out.get("agent_name")
            if not _present(out, "voice_gender"):
                out["voice_gender"] = persona.get("gender", "female")
            # The `persona` field is overloaded: a campaign may put EITHER a registry
            # selector key ("dr_meera") OR free-text persona prose there. Only expand a
            # selector (or a blank) into the rich persona line; leave hand-written
            # free-text exactly as today.
            raw = str(out.get("persona") or "").strip()
            is_selector = bool(personas_mod.get_persona(raw, source=_eff_personas())) if raw else False
            if not raw or is_selector:
                line = str(persona.get("line") or "").strip()
                if line:
                    out["persona"] = line
        lang = prof.get("language")
        if lang and not _present(out, "language"):
            out["language"] = lang.get("name") or lang.get("code")
        return out
    except Exception:  # noqa: BLE001
        return fields if fields is not None else {}


def _render_directive(prof: dict, tts_provider: str = "elevenlabs") -> str:
    """Render the lean domain directive block appended to the brain. Short by design.

    Only a FIELD produces a directive (goal/slots/compliance). A persona/language-only
    profile has no domain block — its identity/voice/language are applied via fill_fields
    and resolve_voice, so this returns '' and the prompt is unchanged.
    """
    field = prof.get("field")
    if not field:
        return ""
    sub = prof.get("sub")
    lang = prof.get("language")

    label = field.get("label", "")
    lines: list[str] = []
    head = f"=== क्षेत्र: {label}"
    if sub:
        head += f" — {sub.get('label','')}"
    head += " ==="
    lines.append(head)

    if sub:
        goal = str(sub.get("goal") or "").strip()
        if goal:
            lines.append(f"मक़सद: {goal}।")
        tip = str(sub.get("directive") or "").strip()
        if tip:
            lines.append(tip)
        slots = [str(s).strip() for s in (sub.get("slots") or []) if str(s).strip()]
        if slots:
            lines.append("caller राज़ी हो तो politely ये details लो: " + ", ".join(slots) + "।")

    comp = str(field.get("compliance") or "").strip()
    if comp:
        lines.append("ज़रूरी सीमाएँ: " + comp)

    if lang:
        reply = str(lang.get("reply") or "").strip()
        code = lang.get("code")
        prov = str(tts_provider or "").strip().lower()
        speakable = lang.get("sarvam_speakable") if prov == "sarvam" else lang.get("el_speakable")
        # Only steer the LLM to reply in a NON-default script when the ACTIVE TTS engine can
        # actually SPEAK it. The runtime clamp keeps audio on hi/en for ElevenLabs, so asking
        # the model for (say) Bengali script on an EL box would yield garbled/mispronounced
        # glyphs — the same failure the existing gujarati->Hindi degrade guards against. When
        # unspeakable on the active engine we simply omit the nudge (the base prompt already
        # tells the model to mirror the caller; the clamp keeps the voice safe).
        if reply and code not in ("hi", "hinglish") and speakable:
            lines.append("भाषा: " + reply)

    return "\n".join(lines).strip()


def apply_to_prompt(base_prompt: str, fields: dict | None, tts_provider: str = "elevenlabs") -> str:
    """Append the domain directive to an already-built system prompt (cache-safe).

    ``tts_provider`` makes the appended language nudge provider-aware (so we never ask the
    LLM to reply in a script the active TTS engine can't speak). Disabled / no-vertical /
    render-empty -> returns ``base_prompt`` unchanged.
    """
    try:
        base = base_prompt if isinstance(base_prompt, str) else str(base_prompt or "")
        if not enabled():
            return base
        prof = resolve_profile(fields)
        if not prof:
            return base
        directive = _render_directive(prof, tts_provider)
        if not directive:
            return base
        return base.rstrip() + "\n\n" + directive
    except Exception:  # noqa: BLE001
        return base_prompt if isinstance(base_prompt, str) else str(base_prompt or "")


def resolve_voice(fields: dict | None, tts_provider: str = "elevenlabs") -> dict:
    """Provider-aware persona voice + (Sarvam) language.

    Returns a dict that may contain ``voice_id`` (ElevenLabs), ``speaker`` (Sarvam)
    and ``sarvam_lang``. Returns {} unless a persona maps a REAL voice for the active
    provider (or a Sarvam-speakable language is set). NEVER returns a cross-namespace
    id, so it can never mis-route or dead-air a call.
    """
    try:
        if not enabled():
            return {}
        prof = resolve_profile(fields)
        if not prof:
            return {}
        prov = str(tts_provider or "").strip().lower()
        out: dict = {}

        persona = prof.get("persona")
        v = personas_mod.voice_for(persona, prov)
        if v:
            if prov == "sarvam":
                out["speaker"] = v
            else:
                out["voice_id"] = v

        # Only the Sarvam engine can switch spoken Indic language safely here; the
        # ElevenLabs path stays clamped to hi/en by the runtime (never bypass it).
        lang = prof.get("language")
        if prov == "sarvam" and lang and lang.get("sarvam_speakable") and lang.get("sarvam_lang"):
            out["sarvam_lang"] = lang["sarvam_lang"]

        return out
    except Exception:  # noqa: BLE001
        return {}


def tts_language(fields: dict | None, tts_provider: str = "elevenlabs") -> str | None:
    """The provider TTS language code to PIN for an INTERNATIONAL/non-default campaign, else None.

    Returns a code (e.g. 'es','fr','ar','zh') only when the campaign selects a world language the
    ACTIVE engine can speak. Returns None for hi/en/hinglish and for regional languages the engine
    can't speak — so the runtime keeps its existing langdetect mirroring untouched (byte-identical).
    The agent uses a non-None result to run a FIXED-language call (pin the TTS + disable mirroring).
    """
    try:
        if not enabled():
            return None
        prof = resolve_profile(fields)
        if not prof:
            return None
        lang = prof.get("language")
        if not lang:
            return None
        code = lang.get("code")
        # hi/en/hinglish are the runtime's native path — never override them here.
        if code in ("hi", "en", "hinglish"):
            return None
        prov = str(tts_provider or "").strip().lower()
        speakable = lang.get("sarvam_speakable") if prov == "sarvam" else lang.get("el_speakable")
        if not speakable:
            return None
        # Sarvam wants xx-IN; ElevenLabs wants the bare code.
        if prov == "sarvam":
            return lang.get("sarvam_lang") or None
        return lang.get("tts_code") or None
    except Exception:  # noqa: BLE001
        return None


def catalogue() -> dict:
    """The full fields/personas/languages catalogue (overlay-merged) for a UI/HTTP."""
    try:
        # Rebuild list views from the effective (overlay-merged) tables.
        eff_f = _eff_fields()
        fields_view = []
        for key, f in eff_f.items():
            subs = [{"key": sk, "label": sv.get("label", sk), "goal": sv.get("goal", "")}
                    for sk, sv in (f.get("sub_options") or {}).items()]
            fields_view.append({
                "key": key, "label": f.get("label", key), "tone": f.get("tone", ""),
                "default_persona": f.get("default_persona"),
                "default_languages": list(f.get("default_languages") or []),
                "sub_options": subs,
            })

        eff_p = _eff_personas()
        personas_view = [{
            "key": key, "display": d.get("display", key), "gender": d.get("gender", "female"),
            "tone": d.get("tone", ""), "languages": list(d.get("languages") or []),
            "sarvam_voice": (d.get("voice") or {}).get("sarvam"),
        } for key, d in eff_p.items()]

        eff_l = _eff_languages()
        languages_view = [{
            "code": code, "name": d.get("name", code), "native": d.get("native", ""),
            "el_speakable": bool(d.get("el_speakable")),
            "sarvam_speakable": bool(d.get("sarvam_speakable")),
            "international": bool(d.get("international")),
        } for code, d in eff_l.items()]

        return {"version": VERSION, "enabled": enabled(), "fields": fields_view,
                "personas": personas_view, "languages": languages_view}
    except Exception:  # noqa: BLE001
        return {"version": VERSION, "enabled": enabled(), "fields": [],
                "personas": [], "languages": []}
