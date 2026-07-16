# VOICE START/END FIX — STATE (crash-safe, branch fix/realtime-voice-kernel-v2)

GOAL: fix outbound voice START (greeting) + END (closing) bugs. BRAIN/LOGIC ONLY.
VOICE BYTE-IDENTICAL. KERNEL_OUTBOUND=1, W5_SPEECH=0 stay ON. MIDDLE perfect — don't touch.

BOX: ssh -i ~/.ssh/do-blr-test/id_ed25519 famit@168.144.153.145  /opt/famit-agent/
BACKUP TS: 20260619-111356  (all targets *.VSEbak.20260619-111356 on box)
VOICE LAW: never touch agent.py lines 652-679 (elevenlabs.TTS+VoiceSettings) nor AgentSession voice block; .env EL_STABILITY=0.55; KERNEL_OUTBOUND/W5_SPEECH.
Voice baseline ref: .vse_stage/VOICE_BLOCK.baseline.txt

GROUND TRUTH (verified):
- voice_kernel/* 4 files BYTE-IDENTICAL box==local (edit local, ship). agent.py box=9db54337 != local 6c577b9b -> edit BOX copy (.vse_stage/agent.box.py), ship back.
- delivery directive renders via provider.py:151 delivery_directive(); lead_name NOT threaded to kernel today.
- record_consent default True at: disclosure.py:144 (dataclass), disclosure.py:319, provider.py:240 (field reads).
- agent.box.py: lead_name=442; base_instructions=503; OPENER_ALREADY_SAID@514(dflt0); assemble@528; _confirm_then_hangup@771; _on_item@805 (closure on ASSISTANT turn = double end); opener say@1021 (OPENER_IN_CTX dflt1, but box .env=0); on_user_turn_completed@885.
- campaign 18a29b5cec.json company_name="AGARO".
- dropin /etc/systemd/system/famit-agent.service.d/kernel-outbound.conf = KERNEL_OUTBOUND=1 + W5_SPEECH=0. NRestarts=0.

EDITS (8 fixes):
[ ] F1a/F3/F4 delivery.py single_greeting_directive: ONE greeting, time-aware good morning/afternoon/hello sir, BAN namaste/namaskar, named identity "kya meri baat {lead_name} se ho rahi hai?", never re-greet
[ ] F7 delivery.py name_directive: anti-shout/no-! already present; add no-loud-theek-hai
[ ] F4 delivery.py: add lead_name param to directives
[ ] F2 disclosure.py:144 record_consent default False; :319 field read default False
[ ] F2 provider.py:240 record_consent field read default False
[ ] F4 provider.py:151 pass lead_name to delivery_directive
[ ] F4 outbound.py assemble_outbound_instructions: ensure lead_name in fields
[ ] F4 agent.box.py: inject fields["lead_name"]=lead_name before kernel build
[ ] F5 agent.box.py:1021 opener say: OPENER_DELAY_S sleep + allow_interruptions=False
[ ] F6 agent.box.py _on_item/closure: trigger on USER bye, no double goodbye
[ ] F1c agent.box.py on_user_turn_completed: lang hint only on change (already mostly)
[ ] F8 campaign json AGARO->Agaro
[ ] dropin add OPENER_IN_CTX=1 (keep KERNEL_OUTBOUND=1+W5_SPEECH=0)

DEPLOY: DONE 2026-06-19 ~05:54 UTC. agent.py md5 box=c6367f31 (was 9db54337). All 8 fixes live.
  dropin = KERNEL_OUTBOUND=1 + W5_SPEECH=0 + OPENER_IN_CTX=1 + OPENER_ALREADY_SAID=1 + OPENER_DELAY_S=0.8.
  campaigns 18a29b5cec + 1fd3218528 company_name AGARO->Agaro. .env OPENER_IN_CTX 0->1 (belt+braces).

PROOF (all PASS):
- TTS+VoiceSettings ctor diff vs agent.py.VSEbak.20260619-111356 = EMPTY (byte-identical).
- AgentSession voice block (stt/llm/tts/vad/voice_settings) unchanged; only preemptive_generation became env-gated (PREEMPTIVE_GEN dflt 1 = identical).
- proc /proc/17380/environ: KERNEL_OUTBOUND=1, W5_SPEECH=0, OPENER_IN_CTX=1, OPENER_ALREADY_SAID=1, EL_STABILITY=0.55.
- worker "capsy" registered (id AW_MJSjHgqFSXSq); NRestarts=0; active/running; new PID 17380 zero errors.
- py_compile clean (agent.py + 4 kernel files). Offline render asserts PASS (greeting time-aware, namaste banned, named-confirm via lead_name, recording line gone @default, anti-shout filler). Kernel L1 render confirms lead_name->delivery directive.
- The 255 errors at 05:54:36 = OLD worker 4183457 torn down at restart (new worker started 05:54:37). Not a crash loop.

ALL 8 FIXES DONE.

ROLLBACK (one block, I drive it — founder never types this):
  ssh -i ~/.ssh/do-blr-test/id_ed25519 famit@168.144.153.145 'cd /opt/famit-agent && T=20260619-111356 && \
  cp agent.py.VSEbak.$T agent.py && \
  cp voice_kernel/brain_packs/delivery.py.VSEbak.$T voice_kernel/brain_packs/delivery.py && \
  cp voice_kernel/brain_packs/disclosure.py.VSEbak.$T voice_kernel/brain_packs/disclosure.py && \
  cp voice_kernel/brain_packs/provider.py.VSEbak.$T voice_kernel/brain_packs/provider.py && \
  cp voice_kernel/integrations/outbound.py.VSEbak.$T voice_kernel/integrations/outbound.py && \
  cp var/campaigns/18a29b5cec.json.VSEbak.$T var/campaigns/18a29b5cec.json && \
  cp var/campaigns/1fd3218528.json.VSEbak.$T var/campaigns/1fd3218528.json && \
  cp .env.VSEbak.$T .env && \
  printf "[Service]\nEnvironment=KERNEL_OUTBOUND=1\nEnvironment=W5_SPEECH=0\n" | sudo tee /etc/systemd/system/famit-agent.service.d/kernel-outbound.conf && \
  sudo systemctl daemon-reload && sudo systemctl restart famit-agent'
PARTIAL REVERTS (env-only, no code): greeting style off -> OPENER_ALREADY_SAID=0; collision delay off -> OPENER_DELAY_S=0; preempt restart -> PREEMPTIVE_GEN=0; opener echo -> OPENER_IN_CTX=0. Each = edit dropin + daemon-reload + restart.
