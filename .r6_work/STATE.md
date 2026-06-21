# ROUND-6 VOICE BRAIN FIX — STAGED (NOT restarted) — 20260620-000715
Box: famit@168.144.153.145 /opt/famit-agent ; venv /opt/capsy-agent/.venv/bin/python
Pre-R6 md5: agent.py c33c03e2 prompt.py c60b30f4 delivery.py 2b704ea4 langdetect.py 0b1044ee
Backups on box: *.R6bak.20260620-000715 (all 5 files). Service NOT restarted (MainPID 173872 still old code).
Post-R6 staged md5 (on disk, inert until restart): agent e353b775 prompt 759b6f5c langdetect 056d537e delivery 42f8b607 datetime 3dbe1938
VOICE BYTE-IDENTICAL PROVEN: EL TTS / sarvam STT / groq.LLM / AgentSession blocks IDENTICAL vs R6bak. .env EL_STABILITY=0.55 + voice_id unchanged.

## Fixes applied (all BRAIN/LOGIC; voice path untouched):
1. [DONE] GREETING two-step + NO re-intro + BAN namaste — agent.py:354,365-386 (_llm_opener Step-A-only spoken opener + fallback); prompt.py:454 (opener_section STATE MACHINE STEP-B/STEP-C, no-re-greet); P1 delivery.py already two-step+no-regreet.
2. [DONE-ENV] GROQ_MAX_TOKENS — code untouched (in protected region). SET ON DEPLOY: GROQ_MAX_TOKENS=220 in famit-agent drop-in.
3. [DONE] SINGLE ending — agent.py:1187 (_confirm_then_hangup: session.interrupt() cancels in-flight LLM goodbye) + agent.py:503 (_last_assistant_is_farewell scans last 2 assistant turns).
4. [DONE] numbers natural Hindi + "rupees", NEVER RS/digit/symbol — prompt.py:234 SHARED_RULES; P1 delivery.py:138 discussion_directive.
5. [DONE] STT Gurmukhi/Odia/Indic short-affirm -> Hindi — langdetect.py:38 (_ORIYA+Telugu/Kannada/Malayalam), :115 (dominant-script >=60% route maps short 2-char affirmations).
6. [DONE] CURIOSITY phrasing — prompt.py:222; P1 delivery.py discussion_directive.
7. [DONE] speak ONLY real campaign data — prompt.py:228; P1 delivery.py discussion_directive.
8. [DONE] Sarvam-TTS routing — agent.py:39 (import resolve_providers), :1033 (additive Sarvam override AFTER the byte-identical EL constructor; flag SARVAM_TTS_ENABLED default ON; routes tier standard/lean->Sarvam Bulbul), :1151 (Sarvam-aware update_options target_language_code on lang switch).
9. [DONE] booking "sham 5"/"5 baje" -> 17:00 — datetime_resolve.py:109 (match bare "sham" + dopahar/afternoon PM bias).

## DEPLOY (founder/next step — NOT done here):
- Off-hours, JOBS queue empty. Set GROQ_MAX_TOKENS=220 in /etc/systemd/system/famit-agent.service.d/kernel-outbound.conf, daemon-reload, restart famit-agent.
- After restart assert: EL_STABILITY=0.55, voice_id unchanged, KERNEL_OUTBOUND=0, EL/STT/LLM blocks md5 unchanged, worker re-registers, 0 errors. Founder real outbound call test.
- SARVAM_TTS_ENABLED default ON; to test bug 8: run a 'standard'/'lean'-tier campaign (or set fields.tts_provider=sarvam) -> call should speak via Sarvam, not silent.

## ROLLBACK: cp *.R6bak.20260620-000715 back over the 5 files (no restart needed since not yet deployed). After deploy: restore backups + restart.
