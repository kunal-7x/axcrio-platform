# PVS Phase-1 FRONTEND — Voice & Providers UI

Wave: backend/handoff-name-clean-line branch. Spec: design/spec-provider-voice-switcher.md (F1/F3/F4/F5).
Builds on the SHIPPED PVS Phase-1 backend (caller.py routes /voices /voice-preview /providers /tiers
/admin/custom-providers + per-campaign tier fields via POST /campaigns/{cid}).

## EARNER GATE (NO /run, NO ring — HARD RULE)
This is a FRONTEND wave deployed to the FORTRESS panel box (143.110.247.249) which has NO agent dir.
The earner box (168.144.153.145) is NEVER touched. Gate = agent.py md5 9150fabe... UNCHANGED +
famit-agent MainPID 1477083 NEVER restarted + /health 200 + 0 5xx (verify read-only on earner box).
Deploy = build LOCALLY, ship artifacts, backup-first (*.PVSUIbak.<ts>), restart famit-panel ONLY.

## BUILD UNITS — ALL DONE (2026-06-14)
- [x] F1 lib/api.ts — Voice type (preview_url/accent/gender/sample_url); getVoices(provider);
      getProviders(); getTiers(); voicePreviewUrl(provider,id); getCustomProviders/add/update/delete;
      updateCampaign(cid)+getCampaign(cid) nested {campaign:{fields}}; CampaignFields/Tier types.
- [x] F4 app/run/_voice-providers.tsx (NEW) + wired into app/run/page.tsx left rail (after Pacing,
      before Handoff). 3-stop LEAN/STANDARD/PREMIUM segmented slider, live ₹/min (tier headline =
      source of truth; custom = rate-card per-component sum), voice dropdown w/ ▶ Play (ONE shared
      <audio> at /voice-preview FREE), cost-meter (₹/min × avg-min × #leads), recommended badge
      (heuristic: >=200 leads->lean, <=25->premium, else standard), provider-health dots from
      /providers, Advanced disclosure (3 per-role selects -> tier:custom), Phase-2 honesty note.
- [x] F3 app/super-admin/api-keys/_custom-providers.tsx (NEW) + wired into page.tsx. "Add custom
      provider" card (name + kind select + base_url + model + key), list w/ enable Switch + delete.
- [x] BUILD GREEN: npx tsc --noEmit EXIT 0 + npm run build EXIT 0 (BUILD_ID g2QcGqqd8YfBKyKVsKkXv;
      /run 16kB, /super-admin/api-keys 7.74kB).
- [x] DEPLOY FORTRESS backup-first (*.PVSUIbak.20260613-185207), restart famit-panel ONLY.
      200 on / /login /run /super-admin/api-keys /crm on loopback:3001 AND panel.famit.in edge;
      new BUILD_ID served on both (no stale cache).
- [x] EARNER GATE before+after PASS: agent.py md5 9150fabe... UNCHANGED, famit-agent MainPID 1477083
      NEVER restarted, /health 200, all 3 services active. (Frontend box has NO agent dir.)
- [ ] commit + gitleaks clean.

## DEPLOY ARTIFACTS
- New live BUILD_ID: g2QcGqqd8YfBKyKVsKkXv (prev tuuIjqN7fCf_iEL-obLon)
- FORTRESS backups: .next/app/lib.PVSUIbak.20260613-185207 (kept)
- ⚠️ FOUND + FIXED a pre-existing corruption: components/Button/index.tsx had a pasted TUI dump
  (from a prior session's terminal render) injected mid-file -> TSC invalid-character errors.
  NOT my code. Restored from HEAD (git checkout HEAD -- components/Button/index.tsx). Build then green.
- ⚠️ Cost-meter: tier headline est_inr_per_min (0.75/1.3/1.6) is the displayed ₹/min (founder's
  source of truth). The rate_card per-component sum DIVERGES from the headline (rate_card assumes
  900 chars/min which gives ~₹1.35 just for Bulbul-v2 TTS, vs the spec's ₹0.14 headline). So the
  preset path shows the headline; only the CUSTOM mix uses the rate-card sum. Documented for Phase 2.

## KEY FACTS
- saveCampaign POSTs /campaigns (create). NEW updateCampaign POSTs /campaigns/{cid} (per spec B6).
- GET /campaigns/{cid} envelope = {campaign:{...,fields:{...}}} (nested; read campaign.fields).
- Campaign type today lacks `id` mapping in run page (campaignId resolved from name). Persist tier via cid.
- /tiers returns rate_card + cost_formula; cost meter is PURE CLIENT-SIDE (zero burn).
- voice-preview EL = 307 redirect (FREE); sarvam = FileResponse wav. Just point <audio src> at the URL.
- Icon registry HAS: star-stroke/star-fill, check-circle-fill, chevron, plus, info, lock, send, trash.
  NO play icon -> inline triangle SVG.
- ob_prov_pending:true in /tiers -> show the Phase-2 note.
