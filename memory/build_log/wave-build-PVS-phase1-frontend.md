# PVS Phase-1 FRONTEND — Voice & Providers UI (slider + cost-meter + custom-provider UI)

Wave: backend/handoff-name-clean-line. Spec: design/spec-provider-voice-switcher.md (F1/F3/F4).
Builds on the SHIPPED PVS Phase-1 backend (caller.py routes /voices /voice-preview /providers
/tiers /admin/custom-providers + per-campaign tier fields via POST /campaigns/{cid}).
FRONTEND-only; deployed to FORTRESS panel box (143.110.247.249). Earner box NEVER touched.

## SHIPPED
- **F1 `lib/api.ts`** (additive): extended `Voice` (preview_url/accent/gender/language/sample_url);
  `getVoices(provider?)`, `voicePreviewUrl(provider,id)`, `getProviders()` (+`ProviderInfo`/
  `ProvidersByRole`), `getTiers()` (+`Tier`/`RateCard`/`TiersPayload`), `getCustomProviders`/
  `addCustomProvider`/`updateCustomProvider`/`deleteCustomProvider` (+`CustomProvider`); `getCampaign(cid)`
  (reads NESTED `{campaign:{fields}}`), `updateCampaign(cid, fields)` (POST /campaigns/{cid}); extended
  `Campaign` with `fields?` + new `CampaignFields`/`CampaignTier` types. All read fns dormant-safe
  (404/offline -> empty/null, never an error wall).
- **F4 `app/run/_voice-providers.tsx`** (NEW, ~530 lines) wired into `app/run/page.tsx` left rail
  (card #6.5, after Pacing & caps, before Handoff). The hero:
  - 3-stop **LEAN · STANDARD · PREMIUM** segmented slider (pill group, token-pure) writing campaign
    field `tier`; each stop shows name + the live `≈ ₹/min` from /tiers; recommended stop gets a
    `check-circle-fill` badge.
  - **Live cost-meter**: big `≈ ₹/voice-min` + `Projected · N leads ≈ ₹X` (= ₹/min × avg-min × #leads,
    PURE client-side, zero burn); editable Avg-call-min input; "Saving ≈ ₹/min vs Premium" loss-aversion
    line; telephony footnote (hidden when 0); "wallet meters the real charge" honesty.
  - **Recommended-tier** heuristic (client-side): >=200 leads -> lean (protect budget), <=25 -> premium,
    else standard.
  - **Provider-health** dots row (ElevenLabs/Groq/Sarvam) from /providers `available`.
  - **Voice dropdown**: scrollable rows [name · accent/gender] each with a ▶ Play button (inline triangle
    SVG — icon registry has no `play`) driving ONE shared hidden `<audio>` at the FREE /voice-preview
    proxy (EL 307 -> public GCS clip; Sarvam pre-hosted wav). Selected row gets a check.
  - **Advanced disclosure** (`chevron` toggle): 3 per-role provider `<Select>` (from /providers by_role,
    unavailable shown as "· no key"); touching one flips the campaign to `tier:"custom"` + "Custom mix" chip.
  - **Phase-2 honesty note**: when `/tiers.ob_prov_pending` -> "Voice + tier config apply now; switching
    the live-call STT/LLM/TTS PROVIDER on the outbound leg is coming in Phase 2 (needs founder approval)."
  - Persists via `updateCampaign` (merges the delta onto the campaign's existing `fields` so the backend's
    wholesale replace doesn't drop other fields); inline "Saved" note; read-only role disables writes.
- **F3 `app/super-admin/api-keys/_custom-providers.tsx`** (NEW) wired into `page.tsx`: a "Custom providers"
  card after the 4 built-in provider cards — "Add custom provider" modal (name + kind select(LLM/STT/TTS)
  + base_url + model + key(optional, password)), list rows w/ kind/ready badges + masked key + enable
  Switch + confirm-delete. Reuses `ghostBtnCls`/`flash` from `../_shared`.

## BUILD + DEPLOY
- `npx tsc --noEmit` EXIT 0; `npm run build` EXIT 0. New BUILD_ID `g2QcGqqd8YfBKyKVsKkXv`
  (/run 16kB ↑ from 12.4, /super-admin/api-keys 7.74kB).
- 🟥 **PRE-EXISTING CORRUPTION FOUND + FIXED:** `components/Button/index.tsx` had a pasted Claude-Code
  TUI status dump (box-drawing chars from a prior session's terminal render) injected mid-file ->
  TSC "Invalid character" storm. NOT this wave's code (git showed it ` M` before I started). Restored
  from HEAD (`git checkout HEAD -- components/Button/index.tsx`); build then green. LESSON: a TSC
  invalid-character storm in a component you didn't touch = check `git diff` on THAT file first; a prior
  session likely pasted terminal output into it. Restore from HEAD, don't try to hand-repair.
- Deploy (proven recipe): tar `.next`+`app`+`lib` (59.4MB, md5 `3bfd5828…`) -> scp FORTRESS (md5-gated
  local==box before extract) -> ONE SSH session: backup-first `*.PVSUIbak.20260613-185207` -> extract to
  `_pvsui_stage` -> grep-verify new code in stage -> atomic `mv` swap -> `chown -R deployuser:deployuser`
  -> `systemctl restart famit-panel` ONLY. 200 on `/ /login /run /super-admin/api-keys /crm` on BOTH
  loopback:3001 AND `panel.famit.in` edge; new BUILD_ID served on both (no stale cache). `.old` + tarball
  cleaned; PVSUIbak backups kept.

## EARNER GATE — before+after PASS (md5/process/health ONLY; NO /run, NO ring per HARD RULE)
agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED; famit-agent MainPID `1477083` /
ActiveEnter `2026-06-10 19:58:18` NEVER restarted; famit-agent/famit-caller/aim-voice-agent active;
caller /health 200. (The FORTRESS frontend box has NO agent dir — the earner box was untouched.)

## WHAT THE FOUNDER SEES + CLICKS
- **Run page -> "Voice & Providers" card** (left rail): pick a campaign -> the card hydrates with that
  campaign's saved tier/voice. Drag-click between **Lean / Standard / Premium** (one tap) -> the ₹/min
  number + the projected-spend number + the quality pill update instantly; a green tick marks the
  recommended tier for the current audience size. Below: a scrollable **Voice** list with a ▶ on each row
  -> hear a free 5-6s sample; tap the name to select it. Type a different **Avg call** minutes to re-project.
  Open **Advanced** to hand-pick STT/LLM/TTS providers (-> "Custom mix"). A note states voice + tier apply
  now; the live-call provider swap is Phase 2.
- **Super-admin -> API Keys -> "Custom providers"**: click "Add custom provider", give it a name + kind +
  base URL + model + key -> it appears in the per-campaign Advanced provider picker.

## FILES
- `famit-panel/lib/api.ts` (patched), `famit-panel/app/run/page.tsx` (patched),
  `famit-panel/app/run/_voice-providers.tsx` (NEW), `famit-panel/app/super-admin/api-keys/page.tsx`
  (patched), `famit-panel/app/super-admin/api-keys/_custom-providers.tsx` (NEW),
  `famit-panel/PVS_UI_STATE.md`.

## NEXT
Phase-2 OB-PROV (agent.py edit, gated, founder sign-off, real ring-gate): make the per-campaign
STT/LLM/TTS PROVIDER swap actually take effect on the live outbound call (`_build_pipeline(fields.tier)`,
default-identical). Voice switching within ElevenLabs is already live today (agent.py:485 fields.voice_id).
