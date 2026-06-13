# Wave build — PVS Phase 1 BACKEND (Provider + Voice switcher + Lean/Standard/Premium tiers)

Date: 2026-06-13/14. Branch: backend/handoff-name-clean-line. Spec: `design/spec-provider-voice-switcher.md`.
Scope: PHASE-1 SAFE backend only (additive caller.py routes + llm_router config + Sarvam samples).
NO agent.py / trunks / firewall / SIP. famit-caller restarted ONLY. OB-PROV (outbound provider swap) = Phase 2, NOT built.

## Box / deploy facts
- Box famit@168.144.153.145 `/opt/famit-agent`; caller :8209; venv `/opt/capsy-agent/.venv`; X-Auth `FamitCall2026`.
- caller.py backup `caller.py.PVSbak.20260613-181837` (pre md5 `e802d30167afa4afc306df9fb8884314`).
- caller.py post md5 `3f2c419ee2a9b3e82d869313ec36483c` (tracked mirror `droplet_work/caller.py` synced to match).
- NEW modules (additive, isolated): `llm_router/tiers.py`, `llm_router/custom_providers.py`.
- Patch applied via idempotent `_pvs_patch.py` (marker `# === PVS PHASE-1 ...`), +13892 bytes.
- Sarvam v2 samples (7) generated ONCE via `_pvs_sarvam_samples.py` -> `var/voice_samples/sarvam/<sp>.wav` (~200KB each WAV).

## EARNER GATE — md5/process/health ONLY (NO /run, NO ring per HARD RULE)
- BEFORE: agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` OK; famit-agent MainPID 1477083 / ActiveEnter 2026-06-10 19:58:18; /health 200; 0 5xx.
- AFTER: IDENTICAL (md5 unchanged, MainPID/ActiveEnter unchanged = NOT restarted; all 3 services active; /health 200; 0 5xx/Traceback).

## ROUTES SHIPPED (the contract the frontend consumes)
- **B1 `GET /voices?provider=`** — auth=tenant. EL (default/`elevenlabs`): `{provider, voices:[{voice_id,name,preview_url(public GCS MP3,FREE),accent,gender,language,sample_url}]}` (26 voices, ALL with preview_url — un-stripped). Sarvam (`?provider=sarvam`): `{provider:"sarvam", voices:[{voice_id,name,gender,accent,language,preview_url:"",sample_url:"/voice-preview?provider=sarvam&id=<sp>"}]}` (7 v2 speakers).
- **B2 `GET /voice-preview?provider=&id=`** — auth=tenant. EL -> 307 RedirectResponse to the voice's public preview_url (no key, no synth, zero burn). Sarvam -> `FileResponse audio/wav` of the pre-hosted clip (200, ~206KB); unknown id -> 404.
- **B3 `GET /providers`** — auth=tenant. `{providers:[{id,name,builtin,kinds[],available}], by_role:{stt:[],llm:[],tts:[]}}`. Built-ins sarvam(stt,tts)/groq(llm)/elevenlabs(tts)/sambanova(llm)/openrouter(llm) with `available` from provider_pool.available_count()>0 (EL = ELEVENLABS_API_KEY set). Custom providers appended (kind/model/base_url/masked/available).
- **B6 `GET /tiers`** — auth=tenant. SINGLE SOURCE OF TRUTH: `{tiers:[{key,name,quality,blurb,est_inr_per_min,stt{provider,model,rate_key},llm{...},tts{...},voice{provider,voice_id}}x3], order:["lean","standard","premium"], default:"lean", rate_card:{assumptions{tts_chars_per_min:900,llm_tokens_per_min:1200,default_avg_call_min:1.5}, stt{sarvam:{inr_per_min:0.5}}, llm{groq-gpt-oss-20b:{inr_per_mtok:8}, groq-llama-3.3-70b:{inr_per_mtok:57}}, tts{sarvam-bulbul-v2:{inr_per_1k:1.5}, sarvam-bulbul-v3:{inr_per_1k:3}, elevenlabs-flash-v2.5:{inr_per_1k:4.2}}, telephony_inr_per_min:0}, cost_formula{...}, phase_note, ob_prov_pending:true}`. est ₹/min: lean 0.75, standard 1.3, premium 1.6.
  - COST MATH the FE does client-side (zero burn): stt_inr_per_min = rate_card.stt[stt.rate_key].inr_per_min; llm_inr_per_min = rate_card.llm[llm.rate_key].inr_per_mtok * 1200/1e6; tts_inr_per_min = rate_card.tts[tts.rate_key].inr_per_1k * 900/1000; total = stt+llm+tts; projected_campaign = total * est_avg_call_min * num_leads.

## CUSTOM-PROVIDER CRUD (B4/B5) — super-admin gated (legacy pw `FamitCall2026` EXCLUDED -> 403, by design)
- `GET /admin/custom-providers` -> `{custom_providers:[{id,name,kind,base_url,model,enabled,added_at,masked,available}]}`.
- `POST /admin/custom-providers` (Form name,kind(stt|llm|tts),base_url,model,key) -> `{ok,id,name,kind,model,masked}`. 400 on bad input.
- `PUT /admin/custom-providers/{cid}` (Form enabled,name,base_url,model,key) -> `{ok,id}`; 404 if missing.
- `DELETE /admin/custom-providers/{cid}` -> `{ok,deleted,id}`; 404 if missing.
- Store: `llm_router/custom_providers.py`, SEPARATE Fernet store `var/custom_providers.json.enc` (same PROVIDER_KEYSTORE_SECRET as key_store), 0600, NOT the live earner pool. Phase-1 = register+list+delete+surface in /providers; ROUTING outbound through a custom provider = Phase 2/OB-PROV.

## PER-CAMPAIGN PERSISTENCE (B6 fields) — extends existing `POST /campaigns/{cid}` via `_coerce_fields`
- New fields persisted: `tier` (lean|standard|premium|custom, invalid->lean), `stt_provider`/`llm_provider`/`tts_provider`/`custom_provider_id` (strings), `est_avg_call_min` (clamp 0.1-30, default 1.5), `budget_cap_inr` (int or "" = no cap; Phase-1 estimate/warn only), `tier_resolved` (snapshot of the resolved {stt,llm,tts,voice} triple from tiers.resolve_triple, so a later tiers.py edit never silently rewrites an in-flight campaign; custom -> snapshots explicit overrides). `voice_id` was already persisted (and is already honored on outbound by agent.py:485 — voice switching within EL is LIVE today, no agent.py edit).

## SMOKE (real HTTP, all PASS)
- /tiers: 3 tiers, default lean, ob_prov_pending true, rate card complete, premium 1.6.
- /voices: 26 EL voices ALL with preview_url+accent+gender; ?provider=sarvam = 7 v2 speakers + sample_url.
- /voice-preview: EL -> 307 redirect to googleapis GCS MP3; Sarvam anushka -> 200 audio/wav 206380B; bad id -> 404.
- /providers: builtins available (groq/sarvam/elevenlabs/sambanova/openrouter all True); by_role.tts = sarvam+elevenlabs.
- custom CRUD (with a real admin JWT minted on-box): add -> list (masked sk-t…7890) -> shows in /providers -> update disable -> delete -> empty. Legacy pw add -> 403 (security gate holds).
- campaign persistence: saved premium+EL voice -> read back tier=premium + full tier_resolved; saved custom+providers -> persisted stt/llm/tts_provider + custom tier_resolved; invalid "GARBAGE" tier -> coerced to lean. (GET envelope is `{campaign:{fields:{...}}}` — nested.) Test campaign 985c7e46c0 restored clean afterward.

## PHASE 2 (NOT built; flag in UI + verify): OB-PROV
Making the per-campaign STT/LLM/TTS PROVIDER swap actually take effect on the LIVE outbound call needs an agent.py edit (`_build_pipeline(fields.tier)`, default-identical, founder sign-off, real ring-gate). Phase 1 ships the FULL control UI + cost meter + voice selection; voice within ElevenLabs already honored on outbound (agent.py:485). `/tiers.ob_prov_pending=true` + `phase_note` surface this honestly.

## FRONTEND (NEXT WAVE — not in this backend wave)
F1 lib/api.ts extend (getVoices(provider), getProviders(), getTiers(), voicePreviewUrl, campaign fields typing). F4 Run-page "Voice & Providers" card: LEAN/STANDARD/PREMIUM segmented slider + Advanced disclosure (3 per-role selects + voice dropdown w/ Play) + live cost-meter strip (₹/min + projected spend + quality pill + latency dot + savings line) + Recommended badge + provider-health row + voice favorites. F3/F5 super-admin api-keys page: "Add custom provider" card + "Tiers" read-only map. All token-pure Core_2; deploy FORTRESS after other panel waves.
