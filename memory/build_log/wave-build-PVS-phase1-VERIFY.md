# PVS Phase-1 — INTEGRATED VERIFY (2026-06-14)

Honest end-to-end verify of the just-shipped PVS Phase-1 (backend + frontend). NO /run, NO ring
(DID +918071583488 resting / spam-flagged — per AGENT_LEARNINGS hard rule). Earner gate = md5 +
process + health only.

## EARNER GATE — PASS (before & after, md5/process/health only)
- agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED (live box `/opt/famit-agent/agent.py`).
- famit-agent MainPID `1477083` / ActiveEnter `2026-06-10 19:58:18 UTC` — NEVER restarted.
- famit-agent + famit-caller both `active`; /health `200`; 0 5xx / 0 Traceback in caller journal (last 800).
- agent.py mtime `2026-06-09 13:05:23` (predates this wave — untouched).
- agent.py:485 `voice_id=(fields.get("voice_id") or os.getenv("ELEVENLABS_VOICE_ID", ...))` — voice
  switching honored on outbound with ZERO edit.

## PER-ITEM RESULT
1. **/tiers correct + cost math — PASS.** lean 0.75 (sarvam · groq gpt-oss-20b · sarvam bulbul:v2 ·
   voice anushka) / standard 1.3 (… llama-3.3-70b · bulbul:v3 · manisha) / premium 1.6 (… llama-70b ·
   elevenlabs eleven_flash_v2_5 · voice blank→UI keeps EL voice). order=[lean,standard,premium],
   ob_prov_pending=true. UI cost-meter uses the headline `est_inr_per_min` (the founder's source of
   truth) — `_voice-providers.tsx:180/388`.
2. **Voice preview FREE both providers — PASS.** EL: 26 voices, public-GCS `preview_url` + accent/
   gender; `/voice-preview?provider=elevenlabs` → **307 redirect** to the free clip (no key, no synth).
   Sarvam: 7 v2 speakers, `/voice-preview?provider=sarvam&id=anushka` → **200 audio/wav ~206KB**
   FileResponse; bad id → 404. ZERO token burn.
3. **Custom-provider CRUD — PASS + secure.** Legacy pw `FamitCall2026` → **403** (the #1 finding
   respected). Real admin JWT (`/auth/login` Form): add (`cp_113a29f14b`, key masked `sk-v…cret`,
   never returned plaintext) → appears in `/providers` → PUT update ok → DELETE → list back to
   baseline clean. Stored in separate Fernet store `var/custom_providers.json.enc`.
4. **Persistence + voice honored — PASS.** POST `/campaigns/{cid}` (Form `fields_json`, MERGE delta):
   tier=premium, voice_id=CwhRBWXzGAHq8TQ4Fs17, tts_provider=elevenlabs, est_avg_call_min=2.0 all
   round-tripped; `tier_resolved` snapshot captured the premium triple AND let the explicit voice_id
   override the tier-default voice. Invalid tier → coerces to lean. Voice honored on outbound via
   agent.py:485 (no edit). (Test campaign restored to lean clean.)
5. **OB-PROV correctly flagged Phase-2 — PASS.** /tiers.ob_prov_pending=true + phase_note; UI renders
   the honesty note ("live-call provider swap is Phase 2, needs founder approval",
   `_voice-providers.tsx:648-660`). agent.py byte-identical (md5 unchanged).
6. **Earner gate — PASS.** (md5/process/health only — see above. NO /run, NO ring per hard rule.)

## FRONTEND EDGE
- panel.famit.in `/ /login /run /super-admin/api-keys /crm` → all **200**.
- Deployed BUILD_ID `g2QcGqqd8YfBKyKVsKkXv` (matches frontend wave); famit-panel `active`.

## RESIDUAL / NOTES
- Cost-meter divergence (KNOWN, by design): rate-card per-component sum (assumes 900 TTS chars/min)
  ≈ 1.86 / 3.27 / 4.35 ₹/min, which is ~2.5× the headline 0.75/1.3/1.6. The UI deliberately shows the
  headline `est_inr_per_min` for presets (founder's source of truth) and only uses the rate-card sum
  for the Custom mix. RECOMMEND: re-tune `tts_chars_per_min` assumption (try ~330-360 for a real
  conversational minute where the agent isn't speaking the whole time) so the Custom-mix number lands
  near the preset headlines. Pure-data edit to tiers.py, no risk.
- PUT custom-provider response echoes `name:None` (cosmetic — the rename persists; the field just
  isn't echoed back). Not a functional defect.
- The legacy `/login` mints a stateless token == legacy-pw equivalent → correctly 403'd on /admin/*.
  Real admin path = `/auth/login` JWT.

## PHASE-2 DECISION FOR THE FOUNDER (OB-PROV)
Making a per-campaign STT/LLM/TTS PROVIDER swap (Lean=Sarvam vs Premium=ElevenLabs) actually take
effect on the LIVE outbound call requires editing agent.py `_build_pipeline` (the sacred earner).
Today: voice selection within ElevenLabs is ALREADY live; the tier/provider config is persisted and
drives the UI + cost-meter, but the live-call provider engine is fixed. OB-PROV needs: founder
sign-off + a default-identical edit + a real ring-gate before/after. Recommend scheduling it as its
own one-box-mutating wave when the DID is un-rested.
