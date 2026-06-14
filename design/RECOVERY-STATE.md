# RECOVERY-STATE.md — Authoritative Source Map + Live Flag State + Open Follow-ups

> **Status as of 2026-06-14** — post repo-recovery-audit wave (P1 drift-map + P2 reconcile).
> This is the single authoritative file for "what file lives where" and "what is actually live on box".
> Update this file whenever you deploy a new file to the box or flip a flag.

---

## 1. CANONICAL SOURCE MAP (per file — where to start every edit)

| File | Canonical start | md5 (box / local) | Notes |
|---|---|---|---|
| `aim_voice_agent.py` | `droplet_work/aim_voice_agent.LIVEBOX.py` | `018c20a7` / `018c20a7` ✅ | Pull box → local reconciled P2. ALWAYS start from this golden, never repo stale. |
| `prompt.py` | `droplet_work/prompt.LIVEBOX.py` | `fb87ea56` / `fb87ea56` ✅ | Pull box → local reconciled P2. Has W1 `build_system_prompt_v2`. |
| `agent.py` (EARNER) | **BOX ONLY** `/opt/famit-agent/agent.py` | `9150fabe` / gitignored | NEVER deploy from local. Local on-disk = `9150fabe` (updated P2); git-ignored; `_inbound_ref/agent.REFERENCE.py` = confirmed accurate read-only mirror. |
| `caller.py` | `droplet_work/caller.py` | `592e6b94` / `592e6b94` ✅ | Already matched box at P1 audit; safe to start edits here. |
| `context_store.py` | `droplet_work/context_store.py` | `245d864f` / `245d864f` ✅ | Matched. |
| `audit.py` | `droplet_work/audit.py` | `190fa1b6` / `190fa1b6` ✅ | Matched. |
| `auth.py` | `droplet_work/auth.py` | `a4397f78` / `a4397f78` ✅ | Matched. |
| `firewall.py` | `droplet_work/firewall.py` | `cd1ac5d1` / `cd1ac5d1` ✅ | Matched. |
| `wallet.py` | `droplet_work/wallet.py` | `1890d41f` / `1890d41f` ✅ | Matched. |
| `entitlements.py` | `droplet_work/entitlements.py` | `9e483325` / `9e483325` ✅ | Matched. |
| `ratelimit.py` | `droplet_work/ratelimit.py` | `ac80252e` / `ac80252e` ✅ | Matched. |
| `obs.py` | `droplet_work/obs.py` | `9fa824e4` / `9fa824e4` ✅ | Matched. |
| `bridge.py` | `droplet_work/bridge.py` | `b15a97b9` / `b15a97b9` ✅ | Matched. |
| `config.py` | `droplet_work/config.py` | `3e1a941f` / `3e1a941f` ✅ | Matched. |
| `store.py` | `droplet_work/store.py` | `2b2b0774` / `2b2b0774` ✅ | Matched. |
| `shadow_diff.py` | `droplet_work/shadow_diff.py` | `679afb08` / `679afb08` ✅ | Matched. |
| `memory.py` | `droplet_work/memory.py` | `cb70e1d7` / `cb70e1d7` ✅ | Matched. |
| `place_call.py` | `droplet_work/place_call.py` | `752cca73` / `752cca73` ✅ | Matched. |
| `backfill.py` | `droplet_work/backfill.py` | `cfd53d38` / `cfd53d38` ✅ | Matched. |
| `backfill_contacts.py` | `droplet_work/backfill_contacts.py` | `9e036175` / `9e036175` ✅ | Matched. |
| `langdetect.py` | `droplet_work/langdetect.py` | `622b1807` / `622b1807` ✅ | Matched. |
| `lead_memory.py` | `droplet_work/lead_memory.py` | `0ab918f3` / `0ab918f3` ✅ | Matched. |
| `whatsapp.py` | `droplet_work/whatsapp.py` | `39006589` / `39006589` ✅ | Matched. |
| `seed_kb_from_campaigns.py` | `droplet_work/seed_kb_from_campaigns.py` | `7eb9caf5` / `7eb9caf5` ✅ | Matched. |
| `kb/__init__.py` | **BOX ONLY** `/opt/famit-agent/kb/__init__.py` | `f6ec3720` / not tracked | RAG module — box-only. Pull before editing. |
| `kb/core.py` | **BOX ONLY** `/opt/famit-agent/kb/core.py` | `3922266f` / not tracked | RAG core — box-only. Pull before editing. |
| `kb/schema.sql` | **BOX ONLY** `/opt/famit-agent/kb/schema.sql` | `fabd3803` / not tracked | RAG DDL — box-only. |
| `_inbound_ref/agent.REFERENCE.py` | Read-only mirror | `9150fabe` | ✅ Accurate read-only mirror of live earner. Never deploy FROM this. |
| `_inbound_ref/aim_voice_agent.DEPLOYED.py` | DEPRECATED | `018c20a7` (updated P2) | Renamed to match box truth; still DEPRECATED scratch. Use `.LIVEBOX.py` instead. |

### STALE / DANGER — never deploy these to box
- `_inbound_ref/aim_voice_agent.LIVE.py` (`4bbd0956`) — obsolete pre-RAG scratch
- `_inbound_ref/aim_voice_agent.NEW.py` (`b44a7ae0`) — obsolete scratch
- `_inbound_ref/aim_voice_agent.VERIFY.py` (`a7d5e0ad`) — obsolete smoke

---

## 2. TRUE LIVE FLAG STATE ON BOX `.env` (as of P1 audit 2026-06-14)

| Flag | Value | Intended? | Risk/Notes |
|---|---|---|---|
| `LEAD_MEMORY_PG` | `1` | ✅ YES | W4b PG-memory read live |
| `CONTROL_ENABLED` | `1` | ✅ YES | Control-layer enforcing |
| `FIREWALL_ENABLED` | `true` | ✅ YES | Step-up PIN enforcing |
| `AIM_ENABLED` | `1` | ✅ YES | AI Manager routes active |
| `AIM_RECORDING_ENABLED` | `1` | ✅ YES | Inbound recording active |
| `FEATURE_*` (forms/support/workflows/booking/funnels/ai_manager/whatsapp/whatsapp_builder) | All `1` | ✅ YES | All features live |
| `WORKFORCE_ENABLED` | `1` | ✅ YES | |
| `WA_AUTO_FOLLOWUP` | `0` | ✅ YES | Intentionally off |
| `MEMORY_TENANT_SCOPED` | `1` | ✅ YES | |
| `STORE_MODES` | `dual` | ✅ YES | PG strangler pattern |
| `EMBED_API_KEY` | NOT SET | ✅ GOOD | Dense embedder off; FTS-only (C-3 constraint satisfied) |
| **`RAG_INJECT_ENABLED`** | **`1` (in .env since 2026-06-14)** | ✅ YES — W0 DONE: kill-switch built + deployed `8335d4ba`; flag-gate A/B/C PASS; golden 5/5 PASS; set 0 to kill RAG | Kill-switch now live; set `RAG_INJECT_ENABLED=0` for emergency RAG disable |
| **`CTX_CACHE`** | **NOT IN .env** | ⚠️ VERIFY — W2 was deployed; code may default off | Add `CTX_CACHE=1` on next famit-caller-only restart if missing |
| **`INBOUND_PROV_LOCK`** | **NOT IN .env** | ⚠️ VERIFY — wave A committed `flip to 1` but absent from live .env | Verify code default; add if needed on next restart |
| `AIM_KB_GROUNDING_CHARS` / `PREFETCH_K` / `LOOKUP_K` | NOT SET | ✅ OK | Code defaults: 1400/5/3 — safe |

---

## 3. OPEN FOLLOW-UPS (earner-safe, prioritized)

### P0 — ✅ DONE (2026-06-14): W0 RAG_INJECT_ENABLED kill-switch
**W0 DEPLOYED:** `8335d4ba` live on box; `RAG_INJECT_ENABLED=1` in `.env`; flag-gate A/B/C PASS; golden 5/5 PASS; famit-agent PID 1477083 UNCHANGED; agent.py md5 `9150fabe` UNCHANGED; caller /health 200; 0 real 5xx.
- Kill-switch: set `RAG_INJECT_ENABLED=0` in `.env` + `sudo systemctl restart aim-voice-agent` → instant RAG disable (byte-identical render)
- Next: W1 (core.py dense=gate + _global UNION + RLS clause)

### P1 — Flag verify (next famit-caller restart, zero-cost)
- Verify `CTX_CACHE=1` present in box `.env` — add if missing
- Verify `INBOUND_PROV_LOCK=1` present in box `.env` — add if missing (W2/Wave A committed this)
- These are famit-caller restarts only (NOT earner/famit-agent)

### P2 — Branch reconciliation (git-only, no box touch)
- Merge `fe/unify-run-wavec` into `backend/handoff-name-clean-line` (current active branch)
  - This aligns the active branch with deployed FORTRESS FE (BUILD_ID `TU16Mn1DcJVmxnxr2GVyL`)
  - 2 commits unique to unify-run-wavec: `fa99acb` (run+crm unify) + `6a63f6e` (deploy learnings)
- Assess `fix/wafx-whatsapp-meta-error-surfacing`: if Signal Aurora FE loader (`9b7591f`) not on FORTRESS, include in next FE unify deploy
- Consider whether `hrd9-isolation-reliability` FE commits need to be in next unify

### P3 — Pull kb/ module to local tracking (informational, no box change)
- `scp -r box:/opt/famit-agent/kb/ droplet_work/kb/` to track locally
- These are currently box-only (`__init__.py`/`core.py`/`schema.sql`) — fine to track since no secrets
- No deploy needed; pure local-tracking

---

## 4. DEPLOY SAFETY RULES (bank every time)

1. **ALWAYS start a deployed-file edit from the `.LIVEBOX` golden** — `droplet_work/aim_voice_agent.LIVEBOX.py` or `droplet_work/prompt.LIVEBOX.py` — never from repo stale or `_inbound_ref/*.py`.
2. **The box is live truth; the repo can be stale.** The only safe direction for drift is box→local (pull). Never scp local→box blind without verifying the local file's md5 matches the expected box golden.
3. **One authoritative copy per file.** `*.LIVEBOX.py` = the canonical local mirror. `_inbound_ref/*.DEPLOYED.py` is deprecated scratch.
4. **Earner gate before AND after every deploy:** agent.py md5 `9150fabe` UNCHANGED + famit-agent PID `1477083` not restarted + `/health` 200 + 0 5xx + NO ring.
5. **Never flip a flag or restart a service without an earner gate first.** Even a `.env` edit + famit-caller restart needs the gate.
6. **RAG is live and ungated.** Until W0 ships `RAG_INJECT_ENABLED`, the 3 injection sites at aim_voice_agent.py :504/:1695/:2520 are always active. Treat every aim_voice_agent edit as touching live RAG behavior.

---

_Last updated: 2026-06-14 by repo-recovery-audit P3 (final phase)_
_Earner gate at update time: agent.py `9150fabe` / PID `1477083` / /health 200 / 0 5xx / NO ring_
