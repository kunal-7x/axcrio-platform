# CLAUDE.md — axcrio-platform (Famit / Axcrio)

Repo map for any agent or teammate working here. Read this + `ARCHITECTURE.md`
(the detailed map) before touching code.

## What this is
Famit / Axcrio = an AI Revenue Workforce SaaS (live at `panel.famit.in`): an AI
voice + WhatsApp agent that calls leads, follows up, books appointments, and
feeds conversion signals back to Meta/Google ads. Multi-tenant, paise-metered
billing, immutable audit, a super-admin control plane.

## Layout (the three code surfaces)
- **`famit-panel/`** — the FRONTEND. Next.js (App Router) + TypeScript admin
  panel. Pages under `app/` (crm, booking, forms, funnels, workflows, run,
  ai-manager, super-admin, billing, login). Shared UI in `components/`. Talks to
  the backend via `lib/api.ts`. This is the bulk of active UI work.
- **`droplet_work/`** — the BACKEND source (Python). The live voice/agent box:
  `caller.py` (FastAPI app, tenant/auth/routes), `agent.py` (LiveKit voice
  agent), plus `wallet.py` (ACID credit ledger), `firewall.py` (PIN/step-up
  action firewall), `audit.py`, `aidecision.py`. **NOT tracked in git** (kept as
  local scratch — it holds backups + secret-risk files; see `.gitignore`). Deploy
  by copying the curated `.py` to the box.
- **`growth-os/`** — the next-gen monorepo (contracts/, packages/, services/) —
  event-envelope schema, shared UI tokens, core service scaffold.

## Design + specs (read before building a feature)
- **`design/`** — execution-ready specs: AI Manager (`aim-*`), Control Layer
  (`control-*`, `spec-control-layer.md`), Run-Campaign, Workflow builder,
  Core_2 reuse map. Always reuse the Core_2 Capsy dashboard kit — never build UI
  from scratch.
- Master prompts at repo root: `AI_MANAGER_MASTER_PROMPT.md`,
  `CREATIVE_STUDIO_MASTER_PROMPT.md`, `Z.MD` (control-layer).
- **`memory/`** — durable brain + per-wave build logs (`build_log/`). Read these
  to recover context on any subsystem. `MASTER_BUILD_STATE.md` is the wave ledger.

## Infra (the live boxes — DigitalOcean, blr1)
- **famit-panel-2** `143.110.247.249` — hardened frontend box (Cloudflare-fronted).
- **famit-livekit / voice box** — runs `caller.py` + `agent.py` (the voice agent).
- **famit-hatchet** `68.183.94.38` — Hatchet-lite durable orchestration + self-
  hosted Logto OIDC (Docker, localhost-only).
- Fortress hardening playbook + box access live in `fortress/` (NOT in git).

## Secrets — NEVER COMMIT
Secrets live ONLY in `.env` files shared out-of-band (one-time-secret / encrypted),
never on GitHub. `.gitignore` blocks them; a gitleaks staged-scan is the net.
The secret-bearing files (give to teammates separately): `.env`, `.env.local`
(GEMINI_API_KEY etc.), `final_env.md` (Vobiz token), `**/ALL_CREDENTIALS.md`,
`ai_manager_cred.md`, `infra/logto/app_id_secret*`, `groq_api.md`,
`fortress/cred.md`, the SSH key `id_ed25519`. See `TEAMMATE_HANDOVER.md`.

## Working rules
- Branch + PR; never push straight to `main`. Commit per verified unit.
- Reuse Core_2 UI components; don't invent from scratch.
- Before any commit: `git add -A` then confirm `gitleaks protect --staged` = 0.
- The detailed system map is `ARCHITECTURE.md`.
