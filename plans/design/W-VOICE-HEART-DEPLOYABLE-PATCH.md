# W-VOICE-HEART-DEPLOYABLE-PATCH — the exact box `agent.py` hunks (KERNEL_OUTBOUND-gated)

> BUILD/verify ONLY — **NO box mutation in this wave.** Branch `fix/callback-retry-scheduling`.
> 🚨 EARNER LAW: `droplet_work/agent.py` is the OUTBOUND earner (GITIGNORED, box-only).
> Local working copy md5 = **`6c577b9b688169419895909052c08365`** (matches the red-team);
> box golden = `98655dbf…`. Re-locate EVERY anchor by the SURROUNDING CODE shown, never the
> raw line number. Every hunk is gated by `_KERNEL_OUTBOUND`; **OFF (default) = byte-identical**.
> The TTS ENGINE lines (`elevenlabs.TTS` provider/voice_id/model, `sarvam.STT`, `groq.LLM`,
> `AgentSession`) stay BYTE-IDENTICAL — only the prosody KNOBS (Hunk D) and the spoken-line
> CALLS (Hunks H/I) and the name-inject (Hunk J) change, all behind the flag (D is voice-correct
> either way and is pinned via the drop-in, see below).
>
> The tracked kernel side (CLOSING + single-greeting + name-sparing/no-emphasis directives,
> the W17 R11-R15 gates, the BAD-transcript replay, the systemd drop-in) is ALREADY COMMITTED
> on this branch and is inert until `KERNEL_OUTBOUND=1`. This doc is the agent-side companion.

## Patch A — flag + façade slot (right after `lead_name` is read, local `:428`)

Anchor (literal): `    lead_name = (meta.get("lead_name") or "").strip()`. Insert AFTER it:

```python
    # --- W-VOICE-HEART outbound kernel façade (flag KERNEL_OUTBOUND, default OFF) ---
    _OK = None  # voice_kernel.integrations.outbound.OutboundKernel | None
    _KERNEL_OUTBOUND = os.getenv("KERNEL_OUTBOUND", "0") in ("1", "true", "True")
```

OFF ⇒ `_OK` stays None and NOTHING from `voice_kernel` is imported on this path.
`_KERNEL_OUTBOUND` is now defined ABOVE `:464` (Hunk J needs it) — ordering satisfied.

## Hunk J — name SPARINGLY (gate the lead-name injection + OPENER_ALREADY_SAID, local `:464-481`)

Anchor:
```python
    base_instructions = system_prompt
    if lead_name:
        base_instructions += f"\n\nLEAD NAME (इस caller का naam): {lead_name} — opener में इसी naam से greet करो।"
```
**Replace the `if lead_name:` block with** (gate it on the LEGACY path only):
```python
    base_instructions = system_prompt
    if lead_name and not _KERNEL_OUTBOUND:
        # OFF (legacy): keep the proven append byte-identical.
        base_instructions += f"\n\nLEAD NAME (इस caller का naam): {lead_name} — opener में इसी naam से greet करो।"
    # ON (kernel): lead_name flows to the kernel via build_for_call(fields=...); the
    # persona uses it AT MOST once (NAME USE directive) and forbids per-turn name
    # prefixes + emphasis — no "greet by this naam every turn" license is injected.
```
And the `OPENER_ALREADY_SAID` block (local `:475`) — gate it the SAME way (there is no
pre-spoken worker opener on the kernel-on path, so the suppress-block is not needed; the
no-re-greet behavior lives in the kernel `SINGLE GREETING:` directive):
```python
    if (not _KERNEL_OUTBOUND) and os.getenv("OPENER_ALREADY_SAID", "1") in ("1", "true", "True"):
        base_instructions += (
            "\n\n=== तुम पहले ही OPEN कर चुके हो (ज़रूरी) ===\n"
            ... (rest of the block UNCHANGED) ...
```

## Patch B+C — the brain swap (instruction seam, local `:485`)

Anchor (literal): `    instructions = base_instructions`. **Replace that single line with:**
```python
    # --- W-VOICE-HEART-B: build the per-call outbound kernel façade (flag-gated) ---
    # OUTBOUND TENANT (C2 fail-closed): tenant = the CAMPAIGN RECORD's owner (server-
    # written), NEVER a dispatch-metadata body value. camp is loaded by _load_campaign.
    if _KERNEL_OUTBOUND:
        try:
            from voice_kernel.integrations import outbound as _ko
            _camp_owner = str((camp or {}).get("tenant_id", "")).strip()
            _OK = _ko.build_for_call(
                tenant_id=_camp_owner,
                call_id=room_name,
                lead_phone=phone,                       # mem.parse_phone(room_name) above
                campaign_id=str(meta.get("campaign_id", "")),
                campaign_tenant_id=_camp_owner,
                fields=fields, recap=recap,
            )
        except Exception as _exc:                       # never break the earner
            logger.warning("outbound kernel facade build failed -> legacy: %r", _exc)
            _OK = None

    # --- W-VOICE-HEART-C: instruction source (OFF/None _OK == byte-identical legacy) ---
    _legacy_instr = lambda: base_instructions           # the verbatim legacy string
    if _KERNEL_OUTBOUND and _OK is not None:
        from voice_kernel.integrations import outbound as _ko
        instructions = _ko.assemble_outbound_instructions(
            _OK, legacy_render=_legacy_instr, fields=fields, recap=recap)
    else:
        instructions = _legacy_instr()                  # OFF: byte-identical to today
```

The kernel system prompt (ON) authors the WHOLE persona including the `OPENING:`
(script pattern: time-of-day → greetings from {company} → confirm identity → WAIT →
reason+permission), the `CLOSING:` (LLM goodbye, no canned line), the `SINGLE GREETING:`
+ `NAME USE:` delivery rules, the casual-Hinglish `LANGUAGE:` ban, cross-vertical from
the brief. One LLM voice — mirroring the inbound the founder loved.

## Hunk H — SUPPRESS the worker's spoken opener (local `:890-912`)

Anchor: the opener build at `:894` (`opener = _llm_opener(`) through the `session.say(opener,
...)` at `:912`. **Wrap the WHOLE opener-build-and-say block** so it runs ONLY on the legacy
path; on kernel-on, the kernel `OPENING:`/`SINGLE GREETING:` directives make the LLM speak the
single greeting as its own turn 1:
```python
    if not _KERNEL_OUTBOUND:
        # LEGACY path — byte-identical to today (old worker opener spoken via say()).
        _disclose_ai = bool(fields.get("disclose_ai", True))
        _disc_phrase = str(fields.get("ai_disclosure") or "").strip()
        opener = _llm_opener(
            fields.get("agent_name") or "Riya",
            fields.get("company_name") or "Famit",
            fields.get("product_name") or "हमारी property",
            lead_name,
            gender=agent_gender,
            disclose=_disclose_ai,
            disclosure_phrase=_disc_phrase,
        )
        logger.info("opener: %s", opener[:200])
        _opener_in_ctx = os.getenv("OPENER_IN_CTX", "0") not in ("0", "false", "False")
        await session.say(opener, allow_interruptions=True, add_to_chat_ctx=_opener_in_ctx)
    else:
        # KERNEL-ON — the brain owns the SINGLE greeting (the LLM speaks it as turn 1
        # from the OPENING:/SINGLE GREETING: directives). Suppress the worker's second
        # speaker entirely (the structural single-greeting guarantee, mirror inbound).
        logger.info("kernel-on: greeting owned by the brain; worker opener suppressed")
        try:
            await session.generate_reply()              # nudge the opening turn (LiveKit API)
        except Exception as _exc:                        # noqa: BLE001 — never break the earner
            logger.warning("kernel greeting kickoff fell through to model turn-1: %r", _exc)
```
> THE ONE BEHAVIORAL UNKNOWN: confirm `session.generate_reply()` (or the pinned
> `livekit-agents` equivalent "say hello first") on the box's plugin version on the
> CANARY. The `try/except` fails OPEN to the model's natural turn-1 — never a crash.

## Hunk I — SUPPRESS the hardcoded close (local `:708-738`, `_confirm_then_hangup`)

Anchor: inside `_confirm_then_hangup`, the `line = _llm_close/_goodbye_line` build +
`handle = session.say(line, ...)` (local `:715-731`). **Gate the build+say on the legacy path:**
```python
        try:
            if not _KERNEL_OUTBOUND:
                _agent_nm = fields.get("agent_name") or "Riya"
                _company_nm = fields.get("company_name") or "Famit"
                if os.getenv("LLM_CLOSE", "0") in ("1", "true", "True"):
                    line = _llm_close(signal, _agent_nm, _company_nm, agent_gender, turns)
                else:
                    line = _goodbye_line(signal, _agent_nm, _company_nm, agent_gender)
                logger.info("P2 closure signal=%s -> goodbye: %s", signal, line[:120])
                handle = session.say(line, allow_interruptions=False)
                try:
                    await handle.wait_for_playout()
                except Exception:  # noqa: BLE001
                    await asyncio.sleep(2.5)
                await asyncio.sleep(0.4)
            else:
                # KERNEL-ON — the brain already spoke the close (CLOSING: directive) as a
                # normal LLM turn. Give it a moment to play, then tear down. NEVER say a
                # hardcoded goodbye on top of the LLM's authored close.
                logger.info("kernel-on closure signal=%s: brain owns the close; worker says nothing", signal)
                await asyncio.sleep(1.2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("closure say failed: %r", exc)
        finally:
            ... (delete_room teardown UNCHANGED) ...
```

## Hunk D — CONSTANT prosody (local `:587-608`, the VoiceSettings KNOBS only)

This is the ONLY change to the voice block, and it touches ONLY the `VoiceSettings`
KNOBS — never the `elevenlabs.TTS(...)` provider/voice_id/model/auto_mode lines. It is
NOT gated on `KERNEL_OUTBOUND` (the constant inbound voice is correct either way) and is
pinned LIVE via the systemd drop-in so it needs no redeploy to revert.

**Option 1 (RECOMMENDED first — zero code-default risk):** leave the code at `0.65/1.0`
and pin `EL_STABILITY=0.45` + `EL_SPEED=1.08` via the drop-in
`voice_kernel/systemd/famit-agent.service.d-voice-heart.conf` (the env wins). Revert =
edit the drop-in. OFF + no drop-in = byte-identical to `98655dbf`.

**Option 2 (later, once the 0.45/1.08 ring is confirmed):** flip the in-code DEFAULTS so
a bare box is correct (the ONE intentional resting byte-change), keeping env override:
```python
        voice_settings=VoiceSettings(
            stability=float(os.getenv("EL_STABILITY", "0.45")),     # was "0.65" — the GOOD inbound value
            similarity_boost=float(os.getenv("EL_SIMILARITY", "0.80")),
            style=0.0,                                              # never raise; style>0 = swing
            use_speaker_boost=False,                                # no loudness pumping
            speed=float(os.getenv("EL_SPEED", "1.08")),             # was "1.0" — the GOOD inbound value
        ),
```

> ⚠ PROSODY TENSION (documented honestly): the current LOCAL comment says 0.45 "was over-
> expressive → swinging" and 1.08 "ran 8% fast". BUT the GOOD inbound the founder LOVED runs
> EXACTLY 0.45/1.08 (`_inbound_ref/aim_voice_agent.LIVE.py:_build_tts`). The "swing" was the
> opener+closer speech-event COLLISION (removed by Hunks H/I), NOT low stability. With one
> speaker, 0.45/1.08 is constant + expressive = the loved feel. This is the derived constant.
> Because it ships via the env-overridable drop-in, the real ring decides: if it swings, one
> edit reverts to 0.65/1.0. Pin prosody-only FIRST (step 4), flip the brain SECOND (step 5).

## WHICH LINES STAY BYTE-IDENTICAL (the TTS ENGINE — never touched)

`elevenlabs.TTS(api_key, voice_id="QTKSa2Iyv0yoxvXY2V8a", model="eleven_flash_v2_5",
language, apply_text_normalization, ..., auto_mode=True)` · `sarvam.STT(language="unknown",
model="saarika:v2.5")` · `groq.LLM(...)` + key round-robin · `AgentSession(...)` +
`session.start()` · the per-turn `tts.update_options(language=code)` mirror · the
`_llm_opener`/`_goodbye_line`/`_llm_close` function BODIES (used on the OFF path; only the
CALLS are gated). The static test `test_voice_unchanged_voice_heart.py` proves, by code
landmark, that Hunks A/B/C/H/I/J fall OUTSIDE every voice-constructor span and Hunk D edits
ONLY the `VoiceSettings` knobs.

## GATED DEPLOY PARAMS (founder-gated, one box-mutating variable at a time)

1. Pre-flight (no mutation): confirm box `agent.py` md5 `98655dbf`, `KERNEL_OUTBOUND` unset,
   no drop-in. `cp /opt/famit-agent/agent.py agent.py.HEARTbak.$(date +%s)`; `cp .env .env.HEARTbak.$(date +%s)`.
   `python -m pytest voice_kernel/ voice_ops/` green + `run_all_gates().passed` True + the
   BAD-transcript replay green.
2. Apply Hunks A+B+C+H+I+J to the box `agent.py` (re-locate by surrounding code). Deploy the
   tracked `voice_kernel/` package to the box. Do NOT apply the Sarvam provider router or the
   per-turn hook. Keep `KERNEL_OUTBOUND` UNSET, no drop-in yet.
3. OFF-identity ring: restart `famit-agent`; place ONE real outbound call → confirm ZERO change
   (every hunk inert). Proves the gating before any behavior flips.
4. Pin CONSTANT prosody FIRST: install the drop-in with ONLY `EL_STABILITY=0.45` + `EL_SPEED=1.08`
   (`KERNEL_OUTBOUND` still unset). `daemon-reload && restart`. Verify it did NOT leak to the
   inbound agent (`tr '\0' '\n' < /proc/$(pgrep -f aim_voice_agent)/environ | grep EL_` → EMPTY).
   Ring → the OLD brain now speaks in the constant inbound voice. Swing/too-fast ⇒ revert to
   `EL_STABILITY=0.65`/`EL_SPEED=1.0`.
5. Flip the brain: uncomment `Environment=KERNEL_OUTBOUND=1` in the SAME drop-in. `daemon-reload
   && restart` (drop-in scopes it to `famit-agent` only — never the shared `.env`).
6. Real-call canary (the ONLY acceptance truth): SINGLE greeting following the script pattern,
   name said once (not loud/fast), everything LLM-generated (no "ok perfect", no hardcoded bye),
   natural Hinglish (no "महत्वपूर्ण"), constant pace/loudness, voice = the loved inbound timbre.
   Watch the journal for double-greets, a `session.generate_reply()` crash (Hunk H unknown), latency.
7. Instant revert (always armed): regression ⇒ comment `KERNEL_OUTBOUND` (or =0) + restart ⇒ old
   brain + perfect voice (zero voice-engine risk — the TTS engine + voice_id were never touched).
   Voice issue ⇒ revert the EL_ lines too. Total ⇒ `cp agent.py.HEARTbak agent.py` + restore `.env` + restart.
