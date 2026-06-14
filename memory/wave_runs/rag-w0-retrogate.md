# RAG W0 — retro-gate the live RAG grounding (RAG_INJECT_ENABLED kill-switch)

Wave log. Each phase appends its tight conclusion below.

## W0 — BUILD + verify (2026-06-14)

**Scope:** build the `RAG_INJECT_ENABLED` kill-switch the v1 design wrongly assumed existed; wrap all 3
live grounding sites so flag-OFF ⇒ no kb retrieval + grounding="" ⇒ byte-identical no-RAG inbound render;
flag-ON ⇒ today's behaviour unchanged.

**Earner gate (before + after, PASS):** agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED ·
famit-agent MainPID `1477083` NOT restarted · caller `/` → 200 · 0 5xx (15m) · NO ring (DID resting).
Box `aim_voice_agent.py` confirmed `018c20a7` == local `droplet_work/aim_voice_agent.py` &
`.LIVEBOX.py` before editing (PLAYBOOK 16/17 respected). `EMBED_API_KEY` stays UNSET (FTS-only).

**Edits — `droplet_work/aim_voice_agent.py` (+ synced to `.LIVEBOX.py`), backup
`aim_voice_agent.LIVEBOX.py.W0bak.20260614-164325`:**
- `:506-513` module-level `RAG_INJECT_ENABLED = (os.getenv("RAG_INJECT_ENABLED","1")…) not in {0/false/no/off/""}`
  — default 1 (absence preserves today; will be set explicitly in .env).
- `:515-525` `_kb_retrieve` — **the central chokepoint**: `if not RAG_INJECT_ENABLED: return []` BEFORE
  any kb access (no FTS/embed/PG hit). Covers all 3 sites by itself.
- Site 1 `lookup` tool (`~:1742`) — flag-OFF returns the no-facts answer WITHOUT kb retrieval.
- Site 2 `pick_campaign` re-ground (`~:1698`) — flag-OFF skips retrieval, `self._grounding=""`.
- Site 3 connect-prefetch (`~:2530`) — flag-OFF guards the whole `_prefetch_grounding` spawn.
- `prompt.py` NOT touched (kill-switch lives in aim_voice_agent.py only).

**Proofs:**
- **Golden 5/5 byte-identical** (local AND on box vs LIVE prompt.py): `_golden/verify_golden.py` exit 0
  — earner render unchanged.
- **Flag CI** `_golden/verify_rag_flag.py` (run on box `/opt/capsy-agent/.venv`, read-only staging, exit 0):
  - A: flag-OFF → `_kb_retrieve()==[]` with a boom-kb (raises if touched) NEVER called → no retrieval.
  - B: `_build_sales_instructions(grounding="")` **byte-identical flag-off == flag-on (18938 chars)** →
    **flag-off == no-RAG baseline render** (the required CI assert).
  - C: a non-empty grounding appends EXACTLY the GROUNDING block → gate is effective, not a dead no-op.
- `py_compile` OK (local + box venv).

**Commit:** `8bc8780` on `fe/unify-run-wavec`; pre-commit gitleaks staged scan = 0 leaks.

**NOT done in this wave (follow-up deploy step):** the edited file is NOT yet copied to the box (box
still runs `018c20a7`) and `.env RAG_INJECT_ENABLED=1` is NOT yet set. This wave is build+verify only;
the box deploy (backup-first → md5-gate scp → restart **aim-voice-agent ONLY** → set `.env` flag →
earner re-gate → 1 real inbound call sanity) is the next box-mutating step. `_golden/verify_rag_flag.py`
is gitignored (lives under `_golden/`, local-scratch) like the rest of the golden harness.

**STATUS: ✅ DONE (build+verify) — earner UNTOUCHED.**

## W0 — DEPLOY (2026-06-14)

**Scope:** SCP W0-built `8335d4ba` to box; set `RAG_INJECT_ENABLED=1` in .env; restart aim-voice-agent ONLY; full earner gate + flag CI on box.

**Pre-deploy box state:** `aim_voice_agent.py` = `018c20a7` (old, pre-W0). `agent.py` = `9150fabe` (earner — unchanged). famit-agent PID `1477083`. Backup: `aim_voice_agent.py.W0deploy.bak.<ts>`.

**Deploy steps:**
1. `scp aim_voice_agent.py famit@168.144.153.145:/opt/famit-agent/` → box md5 confirmed `8335d4ba`.
2. `py_compile` on box venv = OK.
3. `echo 'RAG_INJECT_ENABLED=1' >> /opt/famit-agent/.env` (sed-removed any prior line first).
4. `sudo systemctl restart aim-voice-agent` → new PID `2660527`; `starting worker` + all plugins + Postgres OK.

**Earner gate (PASS):**
- agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED.
- famit-agent PID `1477083` NOT restarted.
- caller `/health` → 200.
- 0 real 5xx (false-positive count was port substrings, not HTTP errors).
- NO ring.

**Flag CI on box (PASS):**
- A: flag-OFF → `_kb_retrieve()==[]` (boom-kb never called) ✅
- B: `_build_sales_instructions(grounding="")` byte-identical flag-off==flag-on (18938 chars) ✅
- C: non-empty grounding appends EXACTLY the GROUNDING block ✅
- `RAG_INJECT_ENABLED=True` confirmed from live module.

**Golden (PASS):** `_golden/verify_golden.py` exit 0 — 5/5 byte-identical on box.

**CTX_CACHE / INBOUND_PROV_LOCK audit result:** CTX_CACHE is a future W2 feature (code doesn't exist in current box file); INBOUND_PROV_LOCK defaults safely to False in code. Neither needs to be added to .env now.

**Kill-switch usage (for founder):**
```
sed -i 's/^RAG_INJECT_ENABLED=.*/RAG_INJECT_ENABLED=0/' /opt/famit-agent/.env
sudo systemctl restart aim-voice-agent
```
→ Instant RAG disable. Render byte-identical to no-RAG. Restore: change 0→1 + restart.

**STATUS: ✅ DONE (build + verify + deploy) — earner UNTOUCHED. RAG grounding ON (kill-switch exists).**

**NEXT:** W1 — `core.py` `dense=`-gate + `_global` UNION + RLS clause + `kb_query_log` FORCE-RLS (offline-only, no box mutations until W1 CI is green).
