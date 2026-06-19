# W-DEPLOY-INBOUND — Voice Kernel inbound brain: FLAG-ON canary deploy

**Wave:** W-DEPLOY-INBOUND (flag-ON canary)
**Status:** ✅ SUCCESS — `KERNEL_INBOUND=1` is LIVE and left ON for the founder ring-test.
**Deploy timestamp (UTC):** 2026-06-18T13:17:04Z (canary + flip completed; verified at this time)
**Box:** famit@168.144.153.145 (DO blr1 voice box)
**Service flipped:** `aim-voice-agent` (inbound AI-Manager worker, `agent_name="manager"`, :8091)
**Earner NOT touched:** outbound earner `agent.py` / `famit-agent` / `famit-caller` / SIP / firewall — never edited, imported, or restarted.

---

## INBOUND DID — the number the founder should call

**☎️ +918071583488**

Confirmed from the box, not a guess:
- The live golden agent header (`/opt/famit-agent/aim_voice_agent.py`) documents the AI-Manager DID and routing: the inbound SIP dispatch routes the AI-Manager DID **+918071583488** to `agent_name="manager"`.
- `agent_name="manager"` IS the worker we flipped (`aim-voice-agent`, MainPID 3954188, registered worker `AW_LPfSopkFx6cJ`). The outbound earner is a SEPARATE worker `agent_name="capsy"`.
- Same number is referenced consistently across `trunk_registry/` (rotation alerts, offline tests) and the DID-swap backup `var/did_swap_backup/outbound_trunks.20260615-164817.json`.
- SIP trunk on box: `LIVEKIT_SIP_TRUNK_ID=ST_bpGqmc9TL9Ph` (in `/opt/famit-agent/.env`).

---

## EARNER GATE — before / after each phase (proving agent.py never drifted)

Frozen golden earner md5 = **`98655dbfc71d5c3da36bcfe3f848082c`**

| Phase | agent.py md5 | famit-agent | caller /health | aim-voice-agent |
|---|---|---|---|---|
| BEFORE (pre-canary, pre-flip) | `98655dbfc71d5c3da36bcfe3f848082c` ✅ | active | 200 | active |
| AFTER (post-flip, post-restart, verified 13:17Z) | `98655dbfc71d5c3da36bcfe3f848082c` ✅ **UNCHANGED** | active | 200 (ports 8209/8208) | active |

- **ZERO drift.** agent.py byte-identical before and after.
- **NO outbound ring performed.** `famit-agent` (MainPID 3112900, :8090) and `famit-caller` never restarted or touched. agent.py never edited or imported by the kernel path.
- caller `/health` = 200 confirmed live on the real uvicorn caller ports (8209 + 8208). (A transient 000 in one probe was a wrong-port guess on my side, not a caller fault — corrected on re-probe.)

---

## BACKUP / GOLDEN PATHS

- **Frozen golden inbound agent (intended unchanged base):** `/opt/famit-agent/aim_voice_agent.py` — golden md5 **`1614be09bfc10c8e3d91c2f68ea64e56`**.
- **Local golden mirror:** `droplet_work/aim_voice_agent.LIVEBOX.py`.
- **Patch set applied for kernel wiring:** golden + the hunks in `design/W-INT-INBOUND-PATCH.md`.
- **Kernel shipped to:** `/opt/famit-agent/voice_kernel/`.
- **Prior on-box agent backups present:** `/opt/famit-agent/aim_voice_agent.py.IV0bak.20260612-031454`, `…py.VFbak.20260611-184619`.
- **Outbound earner golden:** `/opt/famit-agent/agent.py` md5 `98655dbfc71d5c3da36bcfe3f848082c` (frozen; do not touch).

---

## FLAG STATE (current = ON)

- Drop-in: `/etc/systemd/system/aim-voice-agent.service.d/kernel-inbound.conf`
  ```ini
  [Service]
  Environment=KERNEL_INBOUND=1
  ```
- Flipped `0 → 1`; `daemon-reload` done; **only** `aim-voice-agent` restarted.
- Running process env (MainPID 3954188) confirms the merged drop-in flags intact:
  `KERNEL_INBOUND=1`, `VENDOR_SCRIPT_INJECT=1`, `CTX_CACHE=1`, `INBOUND_PROV_LOCK=1`.
- **CRITICAL:** `KERNEL_INBOUND` lives ONLY in this systemd drop-in — NEVER in the shared `/opt/famit-agent/.env` (that would leak the flag to the outbound earner). Verified: flag is in the drop-in only.
- **CURRENT FLAG STATE: `KERNEL_INBOUND=1` (ON)** — left ON for the founder ring-test.

---

## SYNTHETIC CANARY VERDICT (no telephony) — PASS

Ran against the wired per-call kernel (`build_for_call` / `assemble_inbound_instructions` / `choose_tts`):

- `prompt_ok`: **TRUE** — assembled a non-empty **3632-char** inbound prompt via the per-call kernel (did NOT fall back to `legacy_render`).
- `no_banned_phrase`: **TRUE** — no "AI assistant" phrase. W2 structural-identity fix visibly present: prompt instructs *"ek warm insaan ki tarah, kabhi AI ya assistant kehkar nahi"*.
- `vendor_script_present`: **TRUE** — vendor-script content (canary mark) is in the assembled prompt; the vendor script is authoritative.
- **TTS routing (W5 ProviderRouter authoritative-Sarvam fix):** `tts_lean = sarvam`, `tts_standard = sarvam` — both correctly resolved.
- `errors`: **[]** (zero) on the build/assemble/choose path.
- **Sarvam audio synth:** soft-fail, **EXPECTED, NON-GATING.** The LiveKit Sarvam plugin requires the agent-worker http/job context (raised *"Attempted to use an http session outside of a job context… wrap with livekit.agents.utils.http_context.open()"*). This is the plugin's lifecycle requirement, not a kernel defect — the kernel only owns the routing DECISION (proven = sarvam). Real audio bytes are produced by the live worker during the founder's actual ring-test, which has that context. This was the optional "if feasible" check and never gated the wave.

### Journal status (aim-voice-agent): clean
New MainPID 3954188 healthy after restart — Postgres available (sync+async) on all workers; all 4 workers `process initialized` + `AIM prewarm: Silero VAD loaded`; inference executor up; HTTP server on :8091; `registered worker` (id `AW_LPfSopkFx6cJ`). The `exit code 255` lines all belonged to the OLD pre-restart generation (parent PID 3953385) being torn down — normal restart teardown, not a flag-ON error. No new errors post-canary. Temp canary files removed from the box.

---

## 🔴 ONE-COMMAND ROLLBACK (instant disable of the inbound kernel)

```bash
ssh -i ~/.ssh/do-blr-test/id_ed25519 -o BatchMode=yes famit@168.144.153.145 'echo -e "[Service]\nEnvironment=KERNEL_INBOUND=0" | sudo tee /etc/systemd/system/aim-voice-agent.service.d/kernel-inbound.conf && sudo systemctl daemon-reload && sudo systemctl restart aim-voice-agent'
```

This flips the kernel OFF (legacy inbound render path) and restarts ONLY `aim-voice-agent`. The earner (`agent.py`/`famit-agent`/`famit-caller`) is never touched by this command.
