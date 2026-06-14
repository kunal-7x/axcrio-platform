# _inbound_ref — CANONICAL-SOURCE MAP + DEPRECATION (repo-recovery-audit, 2026-06-14)

> ⚠️ READ THIS BEFORE USING ANY FILE IN THIS DIR AS A BASE FOR AN EARNER EDIT.
> The BOX is the live truth (`famit@168.144.153.145:/opt/famit-agent/`). The local
> repo mirrors are reconciled to the box by the `repo-recovery-audit` wave. Files in
> THIS `_inbound_ref/` dir are historical reference snapshots — most are STALE.

## THE ONE CANONICAL COPY PER FILE (use these, nothing else)

| File | CANONICAL local copy | Box truth (md5) | Notes |
|---|---|---|---|
| inbound voice agent | `droplet_work/aim_voice_agent.py` **and** `droplet_work/aim_voice_agent.LIVEBOX.py` | `018c20a7` | Both reconciled to box `018c20a7` (W4 PG-memory + RAG grounding, 3 sites). Start every edit from the `.LIVEBOX` golden. |
| shared prompt renderer | `droplet_work/prompt.py` **and** `droplet_work/prompt.LIVEBOX.py` | `fb87ea56` | Box v2 (`build_system_prompt_v2`). Reconciled. NEVER overwrite box with a v1 local — patch surgically. |
| outbound EARNER | `droplet_work/agent.py` (gitignored — on-disk scratch only) | `9150fabe` | The sacrosanct earner. Local on-disk copy now matches box for reference; it is NOT git-tracked and must NEVER be deployed from local. |
| inbound caller (FastAPI) | `droplet_work/caller.py` | `592e6b94` | Already matched box; tracked. |
| RAG module | `droplet_work/kb/{__init__.py,core.py,schema.sql}` | `f6ec3720` / `3922266f` / `fabd3803` | Already mirrored + matches box exactly. |

## DEPRECATED / OBSOLETE snapshots in this dir (do NOT base edits on these)

| File | md5 | Status |
|---|---|---|
| `aim_voice_agent.DEPLOYED.py` | `018c20a7` | ✅ REFRESHED 2026-06-14 to the CURRENT box file — the "DEPLOYED" name is now truthful. Was previously stale pre-RAG `3152539f`. |
| `aim_voice_agent.LIVE.py` | `4bbd0956` | 🟡 OBSOLETE pre-RAG scratch. Do not use. (untracked) |
| `aim_voice_agent.NEW.py` | `b44a7ae0` | 🟡 OBSOLETE scratch. Do not use. (untracked) |
| `aim_voice_agent.VERIFY.py` | `a7d5e0ad` | 🟡 OBSOLETE scratch. Do not use. (untracked) |
| `agent.REFERENCE.py` | `9150fabe` | ✅ Matches the live earner — accurate reference, keep. (untracked) |
| `voice_tools.py` | `464db175` | reference snapshot. |

## RULE TO BANK
- The BOX is the deploy target + the live truth. `droplet_work/` is a gitignore-exempt
  mirror that must be re-pulled from the box after every box deploy, or it silently
  goes stale and a future "deploy from local" REVERTS the live box (exactly the
  branch-sprawl class of bug). Edits to a deployed file MUST start from a box-pulled
  `*.LIVEBOX` golden, never from a repo file you didn't just verify against the box.
- `RAG_INJECT_ENABLED` does NOT exist yet (0 hits in box code + 0 in box `.env`).
  RAG grounding is LIVE + UNGATED. Building that kill-switch is wave **W0** (retro-gate)
  per `design/RAG-MASTER-PLAN.md` — a SEPARATE box-mutating wave, NOT done here.
