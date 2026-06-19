# W-OUTBOUND-CUTOVER — voice_kernel cutover onto the live OUTBOUND earner

**deploy = OUTBOUND EARNER CUTOVER: SUCCESS.** `KERNEL_OUTBOUND=1` is LIVE on
`famit-agent`, ready for the founder's dashboard ring-test. NO real PSTN ring was
placed (correct — the founder places it himself).

- BOX: `famit@168.144.153.145` (ssh `~/.ssh/do-blr-test/id_ed25519`, `-o BatchMode=yes -o ConnectTimeout=15`)
- OUTBOUND earner: `/opt/famit-agent/agent.py`, service `famit-agent`
- python `/opt/capsy-agent/.venv/bin/python`, `PYTHONPATH=/opt/famit-agent`, kernel ships to `/opt/famit-agent/voice_kernel/`
- Flag lives ONLY in drop-in `/etc/systemd/system/famit-agent.service.d/kernel-outbound.conf` (`[Service]\nEnvironment=KERNEL_OUTBOUND=0|1`) + daemon-reload — NEVER in shared `.env`.

## Identity / md5 ledger
- OLD golden earner md5: `98655dbfc71d5c3da36bcfe3f848082c`
- BACKUP of golden: `/opt/famit-agent/agent.py.WOUTbak.1781793303` (md5 `98655dbfc71d5c3da36bcfe3f848082c` — verified still intact at end of wave)
- NEW-CLOSURE md5 (intended, computed locally from golden + W-INT-OUTBOUND-PATCH hunks; `py_compile` OK): `480d23c3f2e1daf4814b9a3a9c9695d4`
- LIVE box `agent.py` md5 at wave end: `480d23c3f2e1daf4814b9a3a9c9695d4` (asserted == intended-new-closure; unchanged across both restarts)

## Patch applied (4 flag-gated hunks, ~63 lines added; diff = exactly the intended hunks, each carrying the verbatim legacy expression as the OFF branch)
- **Patch A** — flag + `_OK` slot at top of entrypoint.
- **Patch B+C** — per-call façade build (tenant = `camp["tenant_id"]`, fail-closed) + instruction source (`_legacy_instr()` on OFF/None).
- **Patch D** — SHADOW only: computes+logs the router's TTS engine but keeps `elevenlabs.TTS` unconditional, because the `98655dbf` earner has NO Sarvam TTS factory (per PATCH §3 NOTE; never invent a Sarvam factory under the earner).
- **Patch F** — additive kernel post-call persist after the legacy transcript write.
- **Patch G OMITTED** (per PATCH §7): box import path is `db.engine`, not `droplet_work.db.engine`; W7 memory degrades safely to the kernel's Null impl + today's `mem.save_memory` — additive, never an error. DEFERRED follow-up.
- **Patch E** (optional per-turn shadow) deferred per plan.

## EARNER GATE — BEFORE (PASS)
- `agent.py` md5 = `98655dbfc71d5c3da36bcfe3f848082c` (golden) — PASS
- `famit-agent` active; ActiveEnterTimestamp 2026-06-15 18:12:34 UTC (NOT restarted by task at start) — PASS
- `KERNEL_OUTBOUND` drop-in absent (default OFF) — PASS
- `/health` 8208=200, 8209=200 — PASS

## DEPLOY — flag-OFF first
- `voice_kernel/` already on box (`outbound.py` md5 `b8c99546` = the equivalence-proven reverted copy; `config.py` has `KERNEL_OUTBOUND` wired). Box import of façade = OK; OFF helpers verified (`assemble(None)==legacy`, `choose_tts(None)=="elevenlabs"`).
- Drop-in `/etc/systemd/system/famit-agent.service.d/kernel-outbound.conf` created `KERNEL_OUTBOUND=0`; daemon-reload.
- **RENDER-EQUALITY GATE**: golden campaign `c17e55e9f3` OFF-path system prompt rendered from legacy backup AND patched file = IDENTICAL md5 `0af2e07fdb49a73a62f01459fc0180bf` (14131 chars) — PASS.
- Uploaded patched `agent.py`; box md5 == intended-new-closure `480d23c3` — PASS. Restarted `famit-agent` ONLY.
- **FLAG-OFF SMOKE: PASS** — new master registered worker; `/health` 8208=200, 8209=200; resting build byte-identical to golden render at flag-OFF; zero 5xx.

## FLAG-ON synthetic canary — PASS
- Drop-in flipped to `KERNEL_OUTBOUND=1`; daemon-reload; restarted `famit-agent` ONLY.
- Synthetic canary: façade built per-call (tenant from `camp["tenant_id"]`, fail-closed), kernel instruction source active, TTS shadow logs router engine while `elevenlabs.TTS` stays live; no exceptions, worker registered, `/health` 8208=200 / 8209=200.
- NO real PSTN ring placed (correct — founder places it himself).

## FINAL STATE
- `KERNEL_OUTBOUND=1` — LIVE on `famit-agent`.
- Live `agent.py` md5 `480d23c3f2e1daf4814b9a3a9c9695d4`; golden backup `98655dbf` intact.
- famit-agent active/running; both health ports 200.

## ONE-LINE ROLLBACK
`ssh -i ~/.ssh/do-blr-test/id_ed25519 famit@168.144.153.145 'sudo cp /opt/famit-agent/agent.py.WOUTbak.1781793303 /opt/famit-agent/agent.py && sudo sed -i "s/KERNEL_OUTBOUND=1/KERNEL_OUTBOUND=0/" /etc/systemd/system/famit-agent.service.d/kernel-outbound.conf && sudo systemctl daemon-reload && sudo systemctl restart famit-agent'`
(restores the golden `98655dbf` earner + flag OFF; OR simply flip the drop-in to `KERNEL_OUTBOUND=0` + daemon-reload + restart to keep the new file but force the byte-identical legacy OFF path.)
