# W-AIASSISTANT-KILL-DEPLOY — GATED OUTBOUND RE-DEPLOY (LEGACY FIX, KERNEL STAYS 0)

**Status:** ✅ DONE — All steps complete and verified. The legacy AI-assistant fix
is LIVE on the OUTBOUND earner (`famit-agent`). All hard earner-gates green.
`aim-voice-agent` untouched. `KERNEL_OUTBOUND` stays `0` (legacy good-brain logic +
the fix — NOT the kernel cutover).

**Date:** 2026-06-18 (deploy run; restart at 2026-06-18 17:02:47 UTC, journal-confirmed)
**Box:** `famit@168.144.153.145`, key `~/.ssh/do-blr-test/id_ed25519` (`-o BatchMode=yes -o ConnectTimeout=15`)
**Service:** `famit-agent` · python `/opt/capsy-agent/.venv/bin/python` · `PYTHONPATH=/opt/famit-agent`
**Scope:** ONE box-mutating change set (two file swaps + one per-service drop-in + one restart). Revert path armed before the swap.

---

## MD5s — old golden → new closure (verified on box; box LF == local CRLF-normalized)

| File | Old golden | New closure (LIVE, asserted) |
|---|---|---|
| `agent.py`  | `98655dbfc71d5c3da36bcfe3f848082c` | `76a93f0a7444d08c80fa8289835a65aa` |
| `prompt.py` | `fb87ea56ee7f7688b6af712a52627e72` | `016bbff1eba2873623f94acdce72ec82` |

Final canary re-read against the LIVE files (post-deploy, this run) confirms both
closure md5s on disk — AIRTIGHT PASS.

## Backups (auto-rollback targets — both confirmed golden, RETAINED)

| Backup path | md5 | Restores |
|---|---|---|
| `/opt/famit-agent/agent.py.WOUTbak.1781793303`  | `98655dbfc71d5c3da36bcfe3f848082c` | golden `agent.py`  |
| `/opt/famit-agent/prompt.py.AIFIXbak.1781801811` | `fb87ea56ee7f7688b6af712a52627e72` | golden `prompt.py` (created this run) |

Box scratch removed; backups retained.

---

## Earner-gate readings (every reading recorded)

**EARNER GATE — BEFORE:** `agent.py` `98655dbf` + `prompt.py` `fb87ea56` golden ·
`famit-agent` active · `/health` 200 on 8208 + 8209 · `KERNEL_OUTBOUND=0`.

**PRE-SWAP airtight render** (box python, real `voice_kernel` oracle): **PASS** —
zero AI self-label, 8/8 render-pairs clean.

**Atomic swap:** `ASSERT_MD5=PASS` — box md5 == intended-new-closure for both files
(swap aborts if mismatch). Golden-drift guard: old golden asserted before patch.

**Drop-in:** installed at `/etc/systemd/system/famit-agent.service.d/voicefix.conf`
(coexists with the existing `kernel-outbound.conf`). `KERNEL_OUTBOUND` is NEVER set in it.

**Restart:** `famit-agent` only. PID `4011947` → `4013436` across the 2 restarts of
this run. `aim-voice-agent` PID `3988655` UNCHANGED throughout.

**EARNER GATE — AFTER:** `famit-agent` active · `/health` 200 on 8208 + 8209 ·
worker `registered worker` (journal 17:02:47) · 0 tracebacks · no ring.

---

## Canary verdict (held synthetic, NO PSTN)

- **AI self-label gone?** **YES** — airtight PASS on the LIVE files, 8/8 pairs;
  adversarial banned hallucination scrubbed at the output boundary
  (`agent.py _llm_opener` runtime OUTPUT-BOUNDARY SCRUB → clean brand-human fallback).
- **Single greeting?** **YES** — exactly one `नमस्ते` per opener.
- **Neutral prosody loaded?** **YES** — verified in the LIVE `/proc/<famit-agent pid>/environ`:
  `EL_STABILITY=0.65`, `EL_SPEED=1.0`, `OPENER_ALREADY_SAID=1`, `OPENER_IN_CTX=0`,
  `KERNEL_OUTBOUND=0`.
- **Journal clean** (worker registered, 0 tracebacks).

**AIRTIGHT PASS** on the live files.

---

## One correction made mid-deploy (recorded — root cause + fix)

The first drop-in used a bare `Environment=EL_STABILITY=0.65`. But the shared
`/opt/famit-agent/.env` (loaded by the main unit's `EnvironmentFile=`, line 168)
also sets `EL_STABILITY=0.55`, and the FILE won at exec time — `/proc/<pid>/environ`
showed `0.55` while the bare drop-in `Environment=` lost. Root cause: a same-var
conflict between the unit's `EnvironmentFile=` and a drop-in `Environment=` —
systemd lets the file win; `agent.py:35` also `load_dotenv` but `/proc` is fixed at
exec.

**Fix WITHOUT editing the shared `.env`** (editing it would leak the value to
`aim-voice-agent` + `famit-caller` on their next restart): moved the famit-agent-only
flags into a dedicated file `/etc/famit/voicefix.env`, and the drop-in references it
via `EnvironmentFile=/etc/famit/voicefix.env`. A drop-in `EnvironmentFile=` is parsed
AFTER the main unit's `EnvironmentFile=`, so OUR values win deterministically — proven
by the post-fix `/proc/environ` reading (`EL_STABILITY=0.65`). `aim-voice-agent` does
not reference this file, so the fix is isolated to the outbound earner.

`/etc/famit/voicefix.env` content (LIVE):
```
OPENER_ALREADY_SAID=1
OPENER_IN_CTX=0
EL_STABILITY=0.65
EL_SPEED=1.0
```

---

## HOW TO TEST (founder — real proof on YOUR number only)

Place ONE outbound campaign call from the dashboard to ONLY your own number. Confirm:
1. It NEVER says "AI assistant" (or any AI/robot self-label).
2. It greets exactly ONCE (single `नमस्ते`, no double-open).
3. Pace + loudness are NEUTRAL (not fast, not over-expressive).

---

## ONE-LINE ROLLBACK (revert to the golden good brain in one command)

```bash
ssh -i ~/.ssh/do-blr-test/id_ed25519 -o BatchMode=yes -o ConnectTimeout=15 famit@168.144.153.145 \
  'sudo cp /opt/famit-agent/agent.py.WOUTbak.1781793303 /opt/famit-agent/agent.py && \
   sudo cp /opt/famit-agent/prompt.py.AIFIXbak.1781801811 /opt/famit-agent/prompt.py && \
   sudo rm -f /etc/systemd/system/famit-agent.service.d/voicefix.conf && \
   sudo systemctl daemon-reload && sudo systemctl restart famit-agent && \
   md5sum /opt/famit-agent/agent.py /opt/famit-agent/prompt.py && systemctl is-active famit-agent'
```
Expected after rollback: `agent.py 98655dbf…`, `prompt.py fb87ea56…`, `active`.
(The `/etc/famit/voicefix.env` file may be left in place — harmless once the drop-in
that loads it is removed; delete it too for full cleanliness.)

---

## LAWS HONORED

- `KERNEL_OUTBOUND` stays `0` (legacy fix only — NOT the kernel cutover).
- `aim-voice-agent` untouched (PID `3988655` unchanged before/during/after).
- Shared `/opt/famit-agent/.env` NOT edited (no leak to aim/caller).
- ONE box-mutating change set, revert path armed before the swap, integrated
  earner-gate before + after, held synthetic canary on the live files.
- Did NOT edit `ORCHESTRATOR.md`.
