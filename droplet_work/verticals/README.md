# `verticals/` — multi-vertical · multi-persona · multi-language brain layer

A **self-contained, pure-stdlib** package that lets ONE voice agent adapt to any
industry (medical, sales, education, finance, real-estate, insurance, e-commerce,
hospitality, recruitment, logistics, fitness, NGO, …) with **named personas** and
**languages** — without changing the proven lean brain.

It is written to be **copied verbatim between services** (haptica-agent ↔
famit-haptica ↔ any future copy), exactly like the voice-tune knobs. No livekit /
agent / caller imports; no network; no heavy wheels.

## Why it can't break the live system

Every entry point is **default-OFF** and **byte-identical when off**:

| Function | Off / no-vertical behaviour |
|---|---|
| `enabled()` | `FEATURE_VERTICALS` env, default `0` → `False` |
| `fill_fields(fields)` | returns the **same** object |
| `apply_to_prompt(p, fields)` | returns `p` **unchanged** |
| `resolve_voice(fields, provider)` | returns `{}` |

Additional invariants:

- **Never mutates** the input `fields` dict (always copies).
- **Never raises** — every public function degrades to the off-behaviour on error.
- **Identity fill only where blank** — an explicit campaign value always wins.
- **Provider-aware voice** — a Sarvam speaker id is never returned on the ElevenLabs
  path (no cross-namespace mis-route, no dead-air).
- **Respects the TTS clamp** — it never asks the runtime to speak an unspeakable
  language; it only sets `sarvam_lang` for Sarvam-speakable languages.
- **Cache-safe** — `apply_to_prompt` appends a one-time suffix; it does **not**
  rewrite the prompt per turn (which would bust the LLM prompt cache).

## Enabling it

```bash
FEATURE_VERTICALS=1          # turn the layer on
```

Then a campaign opts in per-call via its `fields`:

```jsonc
{
  "vertical":   "medical",              // registry.FIELDS key
  "sub_option": "appointment_reminder", // FIELDS[vertical].sub_options key
  "persona":    "dr_meera",             // personas.PERSONAS key (or a display name)
  "language":   "hi"                    // languages.LANGUAGES code / alias / name
}
```

All four are optional: with `FEATURE_VERTICALS=1` but no `vertical`, behaviour is
still byte-identical.

## Live-tunable overrides (no deploy)

Drop a JSON file (path via `VERTICALS_OVERRIDES_PATH`, else
`$HAPTICA_VAR/verticals_overrides.json` / `$FAMIT_VAR/verticals_overrides.json`) to
ADD or tweak verticals/sub-options/personas/languages — deep-merged over the static
registries, mtime-cached. This is the same idiom as `VAR/tier_overrides.json`, and
is the seam a future super-admin "Verticals" page writes to.

## Integration (thin, additive)

```python
from agent_svc import verticals

# 1) BEFORE build_system_prompt — fill persona/language identity blanks:
fields = verticals.fill_fields(fields)
system_prompt = build_system_prompt(fields)

# 2) AFTER the brain (and after any brain_override) — append the domain directive:
system_prompt = verticals.apply_to_prompt(system_prompt, fields)

# 3) At TTS construction — provider-aware persona voice (optional overrides):
vo = verticals.resolve_voice(fields, tts_provider=cfg.tts.provider)
#    vo may contain {"voice_id"|"speaker"|"sarvam_lang"} — default to today's config.
```

## Copying to another service (e.g. famit-haptica)

Copy the whole `verticals/` folder into the target's agent package and add the same
3 hooks in its call entrypoint + TTS construction. Nothing else is required — the
package has no external dependencies.
