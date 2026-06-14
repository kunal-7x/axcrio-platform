# Video Framework → Studio (end-to-end) — wave run log

Spec: `design/VIDEO-STUDIO-MASTER-PLAN.md` + `design/PROVIDER-FRAMEWORK-PLAN.md` §14 (the unified
W1–W12 roadmap). Canonical branch `fe/unify-run-wavec`. One box-mutating wave at a time, serialized
vs RAG/Vault/Video on caller.py. Earner-safe (agent.py `9150fabe` NEVER imported/touched; restart
ONLY famit-caller / famit-aiasset / the video worker — NEVER famit-agent).

---

## W5 — strangler video cut-over (REGISTRY_FOR_VIDEO) — ✅ DONE + DEPLOYED (2026-06-14)

**Scope (plan §14 W5):** rewire `media_gen/video/client._resolve_key` so that when
`REGISTRY_FOR_VIDEO` is ON it asks the provider registry (`registry.get_provider(tenant,
"video_gen")`) for the provider+key, and on a registry MISS falls back to the legacy
`config.fal_key(...)` path. Flag default OFF → today behavior (resting byte-identical).

### EARNER GATE — BEFORE
| Check | Value |
|---|---|
| agent.py md5 (box) | `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED |
| famit-agent MainPID | `1477083` (NOT restarted) |
| famit-caller MainPID | `2745889` |
| caller /health (8209) | 200 |
| 5xx (caller, last 15m) | 0 |
| `PROVIDER_REGISTRY_ENABLED` | `1` (registry ON since W4) · `REGISTRY_FOR_VIDEO` absent (default OFF) |
| ring | NO ring (no calls placed) |

### THE CHANGE (file:lines — registry-then-fallback path)
- `droplet_work/media_gen/video/config.py:67-77` (NEW `registry_for_video()`) — call-time read of
  `REGISTRY_FOR_VIDEO`, lenient truthy (`1/true/yes/on/y/t`); default OFF. Purely additive (diff vs
  box golden `b68a1dc6` = `66a67,77`, 0 deletion/modification lines). New box md5 `02bb49dc`.
- `droplet_work/media_gen/video/client.py:304-355` — `_resolve_key` is now a thin dispatcher:
  ```
  def _resolve_key(provider, tenant_id=""):
      if config.registry_for_video():           # flag ON
          key = _registry_resolve_key(provider, tenant_id)   # registry FIRST
          if key:
              return key                          # registry hit wins
      return _legacy_resolve_key(provider, tenant_id)         # MISS / flag-OFF -> legacy env path
  ```
  - `_registry_resolve_key` (`:311-329`): lazy `from provider_registry import registry`; calls
    `registry.get_provider(tenant_id, capability="video_gen", routing_hint=<provider slug>)`; on
    `client.ok` returns `client._key` (decrypted in-process, AAD-bound via the get_secret seam);
    returns `""` on ANY miss (package absent / not ok / empty key / exception → legacy fallback).
    Never raises — a resolution problem degrades to legacy, never breaks a render. NEVER imports
    agent.py (earner-safe); the registry rides caller.py + the AI-asset process.
  - `_legacy_resolve_key` (`:332-345`): the ORIGINAL per-tenant env-var resolution
    (`config.fal_key`/`replicate_token`/`luma_key`/`higgsfield_key`/`selfhost_token`/`generic_key`),
    byte-identical to the pre-W5 `_resolve_key`. This is the flag-OFF path.
  - client.py diff vs box golden `58af1c8a` = additive only (`302a303,309` doc comment +
    `304c311,331` def-rename + `318a346,355` new dispatcher); legacy branch logic unchanged. New box
    md5 `be38c169`.

### FLAG-OFF BYTE-IDENTICAL + REGISTRY-THEN-FALLBACK — 6 OFFLINE PROOFS (all PASS)
1. flag OFF → `_resolve_key == _legacy_resolve_key` for every provider
   (`fal/replicate/luma/higgsfield/selfhost/generic/""`) — byte-identical to today.
2. flag ON + registry `ok` → registry key wins (`REGISTRY_KEY_123`).
3. flag ON + registry `not ok` (miss) → legacy fallback (`LEGACY_FAL_KEY`).
4. flag ON + registry raises (e.g. PG down) → legacy fallback (never breaks render).
5. flag ON + registry `ok` but EMPTY key → legacy fallback (video has no auth='none').
6. flag ON + `provider_registry` package absent (ImportError) → legacy fallback.

### DEPLOY (FORTRESS recipe, famit-caller-only)
- Edited FROM the box golden (local `client.py` `58af1c8a` == box; `config.py` matched box
  `b68a1dc6` — PLAYBOOK rule 16).
- Backups: `client.py.W5bak.20260614-220716` + `config.py.W5bak.20260614-220716` (in
  `/opt/famit-agent/media_gen/video/`).
- scp to /tmp → md5-gate (staged == local: `be38c169` / `02bb49dc`) → caller-venv
  `py_compile` OK → atomic `mv` swap → `chown famit:famit` → box import-check
  `registry_for_video()=False` (flag absent).
- Restarted **famit-caller ONLY** (PID 2745889 → 2757508, NRestarts=0). famit-aiasset (2364219),
  aim-voice-agent (2739156), famit-agent (1477083) all UNTOUCHED.
- `REGISTRY_FOR_VIDEO` NOT added to `.env` (absent → default OFF → resting byte-identical, the
  required end-state for this wave).
- The media_gen/video files live under `/opt/famit-agent` (gitignored scratch); imported lazily by
  `provider_registry/named_transforms.py` (caller.py graph). The video studio submit path that
  actually calls `_resolve_key` is W8 (not yet mounted) — W5 is purely the key-resolution seam.

### EARNER GATE — AFTER (PASS)
| Check | Value |
|---|---|
| agent.py md5 | `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED |
| famit-agent MainPID | `1477083` NOT restarted |
| aim-voice-agent / famit-aiasset | `2739156` / `2364219` UNTOUCHED |
| caller /health (8209) | 200 |
| 5xx / tracebacks (since restart) | 0 |
| `REGISTRY_FOR_VIDEO` | absent → default OFF → resting byte-identical |
| ring | NO ring (no calls placed) |

### ROLLBACK
Set/leave `REGISTRY_FOR_VIDEO` absent or `0` (instant, no deploy — already the resting state; flag
OFF → legacy env path verbatim). To fully remove the code: restore
`client.py.W5bak.20260614-220716` + `config.py.W5bak.20260614-220716`, restart famit-caller.

### NEXT (W6)
VID: engine.py seam fix + PG video schema + live-library bridge (`FEATURE_VIDEO_LIBRARY`) — on the
AI-asset service (`:8310`), NOT caller.py.
