# KERNEL OUTBOUND STAGING (W1–W7) — EARNER-CRITICAL — STATE

Branch: `fix/realtime-voice-kernel-v2`. Box: `ssh -i ~/.ssh/do-blr-test/id_ed25519 famit@168.144.153.145` `/opt/famit-agent/`.
THE LAW: never touch TTS constructors (TTS md5 `805c4acb`), `.env` (`EL_STABILITY=0.55`), never flip `KERNEL_OUTBOUND`.

## Goal
Stage W1–W7 kernel brain onto live outbound agent.py via the OFF-is-identity adapter
`voice_kernel.integrations.outbound`. Deploy with `KERNEL_OUTBOUND=0` (byte-identical / no behavior change).
W5 (speech planner) MUST be force-disabled (it broke the voice before). Do NOT flip on — founder flips+tests.

## Plan / progress
- [x] STEP 1a: W5OffSpeechPlanner (plan()->None) added to voice_kernel/null_impls.py — DONE
- [x] STEP 1b: gated speech impl in outbound._build_kernel_with_impls behind w5_speech_enabled() (W5_SPEECH; default Null even when KERNEL_OUTBOUND=1) — DONE
- [x] STEP 1c: updated tests + added gate-off proof; 45 integ + 53 unit pass — DONE
- [x] STEP 1d: committed local f03b6f3 (gitleaks clean) — DONE. Box ship pending.
- [x] STEP 2: WIRED on .kernelstage/agent.box.actual.py — DONE (py_compile OK; +89/-1 lines).
      4 seams + guarded import `_vk`. Voice block (elevenlabs.TTS..AgentSession close) BYTE-IDENTICAL
      live-vs-wired: md5 f20e13482945b27e81ba8e16a4c61b76 on BOTH. Disjointness logic (W-VOICE-HEART
      landmarks) ALL PASS: brain anchors (instr_seam, lead_name) OUTSIDE every engine span; opener_say
      outside constructors; VoiceSettings nests, voice_id outside it.
      NOTE: golden `805c4acb` is a STALE earlier-version hash; current live TTS block hashes f20e1348.
      The authoritative proof is live==wired byte-identity (proven). Will report honestly.
- [x] STEP 2-DEPLOY: DONE. voice_kernel W5-gate shipped + py_compile OK on box (backups *.A4bak.20260619-092230).
- [x] STEP 3: DONE. Wired agent.py shipped (md5 9db54337). Backup agent.py.A4bak.20260619-092230 (md5 7791e50f).
      Restarted famit-agent (no active call). New MainPID 4178754, NRestarts=0, worker "capsy" re-registered (AW_ZRXX4qGSY5Nz).
- [x] STEP 4: VOICE-SAFE PROVEN. TTS+session voice block BYTE-IDENTICAL live-vs-wired (md5 f20e1348 on box backup AND new).
      EL_STABILITY=0.55. drop-in + /proc/4178754/environ KERNEL_OUTBOUND=0. Box import check: kernel_outbound_enabled()=False,
      w5_speech_enabled()=False. 45 mandatory local tests pass (incl. OFF byte-identity). Only "error" since restart = benign
      systemd cgroup-kill notice on OLD-proc shutdown (no Python error/traceback on new PID).
- [x] STEP 5: STAGED, NOT FLIPPED. KERNEL_OUTBOUND stays 0. Founder flips + tests.

## DROP-IN ALREADY EXISTS: /etc/systemd/system/famit-agent.service.d/kernel-outbound.conf = `Environment=KERNEL_OUTBOUND=0`.

## EXACT FLIP-ON (founder test) — adds KERNEL_OUTBOUND=1 + W5_SPEECH=0 to the drop-in, reload, restart:
```
ssh -i ~/.ssh/do-blr-test/id_ed25519 famit@168.144.153.145 'sudo tee /etc/systemd/system/famit-agent.service.d/kernel-outbound.conf >/dev/null <<EOF
[Service]
Environment=KERNEL_OUTBOUND=1
Environment=W5_SPEECH=0
EOF
sudo systemctl daemon-reload && sudo systemctl restart famit-agent'
```
(W5_SPEECH=0 keeps the speech-planner force-off = the gate that protects the voice. NEVER set W5_SPEECH=1 for the first test.)

## EXACT ROLLBACK (any failure):
```
ssh -i ~/.ssh/do-blr-test/id_ed25519 famit@168.144.153.145 'cd /opt/famit-agent && cp agent.py.A4bak.20260619-092230 agent.py && sudo systemctl restart famit-agent'
```
(To also revert the W5 gate files: cp voice_kernel/null_impls.py.A4bak.20260619-092230 + voice_kernel/integrations/outbound.py.A4bak.20260619-092230 back, but they are OFF-inert so not required.)
- [ ] STEP 3: deploy with KERNEL_OUTBOUND=0 (leave absent); restart famit-agent (no active call)
- [ ] STEP 4: voice-safe proof (TTS md5 805c4acb, identity tests pass, EL_STABILITY=0.55, worker capsy re-registers, NRestarts=0, import check=False)
- [ ] STEP 5: DO NOT flip. Leave staged. Report flip-command + rollback.

## Key facts (verified from code)
- outbound.py `_build_kernel_with_impls` ~line 240-248 registers router+speech (W5).
- `assemble_turn` (live hot path via on_turn) does NOT call speech.plan — W5 only reachable via plan_speech() (which the 4-seam wiring does NOT wire). Gate = defense in depth.
- env flag pattern: `os.getenv("NAME","0") in ("1","true","True")`.
- local agent.py EXISTS (55752 bytes, Jun 18). Box golden md5 differs.
- rollback: `cp agent.py.A4bak.<ts> agent.py && sudo systemctl restart famit-agent`
