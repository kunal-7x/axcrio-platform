# PVS — Provider + Voice Switcher + Lean/Standard/Premium tiers (PHASE 1 backend)

Wave: backend/handoff-name-clean-line branch. Spec: design/spec-provider-voice-switcher.md.
Box: famit@168.144.153.145 /opt/famit-agent (caller.py :8209, venv /opt/capsy-agent/.venv, X-Auth FamitCall2026).
EARNER GATE = agent.py md5 9150fabe4ff62b4b4470f9a87df346e5 UNCHANGED + famit-agent MainPID 1477083 / ActiveEnter 2026-06-10 19:58:18 NOT restarted + /health 200 + 0 5xx. NO /run, NO ring (HARD RULE).
RESTART famit-caller ONLY. NEVER touch agent.py / trunks / firewall / SIP.

## EARNER GATE BEFORE = PASS (recorded)
agent.py md5 9150fabe...346e5 OK; MainPID 1477083; ActiveEnter 2026-06-10 19:58:18; /health 200; 0 5xx.

## BUILD UNITS — ALL DONE (PHASE 1 BACKEND COMPLETE 2026-06-14)
- [x] U1 llm_router/tiers.py — rate card + 3 preset triples + cost math (single source of truth)
- [x] U2 llm_router/custom_providers.py — separate Fernet store (var/custom_providers.json.enc)
- [x] U3 B1 /voices — un-strip preview_url + accent/gender; ?provider=sarvam 7-speaker catalogue + sample_url
- [x] U4 B2 /voice-preview — EL 307 redirect to preview_url; sarvam FileResponse audio/wav clip
- [x] U5 B3 /providers — built-in + custom, kinds + available (available_count); by_role grouping
- [x] U6 B4 /tiers — mirrors tiers.py (single source of truth)
- [x] U7 B5 /admin/custom-providers CRUD (super-admin gated; legacy pw 403 by design)
- [x] U8 B6 _coerce_fields — tier + *_provider + custom_provider_id + budget_cap_inr + est_avg_call_min + tier_resolved snapshot + validation
- [x] U9 B7 Sarvam v2 sample set (7 WAV clips, one-time minimal synth) -> var/voice_samples/sarvam/<sp>.wav
- [x] DEPLOY: backup caller.py.PVSbak.20260613-181837, patch+box py_compile, swap, restart famit-caller ONLY
- [x] SMOKE all endpoints PASS
- [x] EARNER GATE AFTER = PASS (agent.py md5 unchanged, famit-agent never restarted, /health 200, 0 5xx)
- [x] commit + gitleaks clean (added .gitleaks.toml allowlist for tiers.py model-name rate-keys)

post-deploy: box caller.py md5 = 3f2c419ee2a9b3e82d869313ec36483c; tracked mirror synced.
NEXT = FRONTEND wave (F1/F3/F4/F5) per spec; then Phase 2 OB-PROV (agent.py, gated, founder sign-off).

## KEY FACTS
- box caller.py md5 e802d30167afa4afc306df9fb8884314 (ahead of tracked mirror; box = source of truth)
- _coerce_fields @ caller.py:3344 (voice_id already passes); POST /campaigns/{cid} @ :3520
- /voices @ :3323 (strips preview_url today); provider-keys @ :6533; _PK_PROVIDERS @ :6526
- auth: resolve_tenant :622, authed :650, need_auth :654, require_super_admin :703, _forbidden :932
- key_store providers fixed = groq/sarvam/sambanova/openrouter (DON'T overload — separate custom store)
- presign helper _rec_presign @ caller.py:4051; recorder.presign(bucket,key) @ ai_manager/recorder.py:226
- Sarvam keys: SARVAM_API_KEY (+ _2.._5). EL: ELEVENLABS_API_KEY. boto3 1.43.28 in venv.
- fastapi.responses imports: only HTMLResponse, JSONResponse today -> add StreamingResponse/RedirectResponse/FileResponse as needed (import locally to be safe)
- Sarvam v2 speakers: anushka, manisha, vidya, arya, abhilash, karun, hitesh
