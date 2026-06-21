# 🔐 VAULT — TEAMMATE HANDOFF (build with ultracode on a fresh session)

> Hand this whole file to the teammate. It points to the full design + bundles the HARD RULES their
> ultracode session must follow so it can't break the live earning product. Vault is the PIN-gated,
> per-vendor, encrypted secret store — and the `get_secret()` backend that the Video provider-framework
> (and every future tool) will consume.

## 📍 THE PLAN (the architecture + the phased build waves)
**`C:\Users\kunal\Desktop\caps\design\VAULT-MASTER-PLAN.md`** ← the master design (BE + FE + DB + AI + security + the build roadmap). Build from this.

## 📖 READ FIRST, IN THIS ORDER (so the fresh session has full context)
1. `design\VAULT-MASTER-PLAN.md` — the Vault architecture + build waves (the spec).
2. `MASTER_DNA_PLAN.md` — the whole product's DNA (what Famit is, every subsystem, why each was born).
3. `PLAYBOOK.md` — the mistakes-checklist (do NOT relearn these the hard way).
4. `WORKFLOW_LEDGER.md` — every wave built so far + its outcome (so you don't redo or collide).
5. `AGENT_LEARNINGS.md` + `design\RECOVERY-STATE.md` — the hard-won lessons + the canonical-source map.

## 🟥 HARD RULES (non-negotiable — the live product EARNS money; don't break it)
- **EARNER-SAFE:** NEVER edit or restart `agent.py` (the live outbound voice earner, md5 `9150fabe4ff62b4b4470f9a87df346e5`, PID `1477083`), nor trunks/SIP, nor change existing `firewall.py` PIN behavior. Vault is ADDITIVE. **Earner gate every box step:** re-baseline `agent.py` md5 FRESH from the box (the literal can go stale) = UNCHANGED + famit-agent PID not restarted + caller `/health` 200 + 0 5xx + **NO outbound call** (the DID is carrier-resting; never place test calls).
- **EDIT FROM THE BOX GOLDEN:** the live box is the source of truth; the local repo can be stale. Before editing any deployed file, pull the box copy and edit THAT; NEVER scp the repo over the box blind (it silently reverts live changes). See `RECOVERY-STATE.md` for the canonical-source map.
- **CROSS-PRODUCT `caller.py` SERIALIZATION:** only ONE of {RAG, Video, Vault} edits `caller.py` at a time. The MAIN session is building RAG + Video — coordinate (the main session edits `caller.py`); Vault should add its own module + a single mount line, ideally on its own backend file, and merge the `caller.py` mount when the main session is idle.
- **BRANCH DISCIPLINE:** the panel deploys MUST build from the canonical branch **`fe/unify-run-wavec`** (it has ALL the UI). NEVER build the panel from a lone feature branch — it silently reverts other features' live UI (this bit us once).
- **MODEL ROUTING (limited weekly limits — don't waste, don't cheap out):** Haiku = explore/grep/mechanical; Sonnet = research/web-search/frontend/verify/compress; Opus = design + the security-critical backend surgery + synthesis. Decide routing at AUTHOR time; never change a model on an already-run phase (forces a wasteful re-run).
- **WORKFLOW PERSISTENCE:** every workflow phase APPENDS its conclusion to `memory\wave_runs\<wave>.md` + the final phase appends one line to `WORKFLOW_LEDGER.md` (so compaction never loses the output).
- **FRONTEND:** invoke the `frontend-design` skill for layout + reuse the Core_2 kit, Inter Display, ZERO raw hex.
- **SECURITY (Vault is the most-secure system):** encrypt secrets at rest (libsodium/age/KMS + a master key — NEVER plaintext, never in logs or API responses), per-tenant RLS, PIN/firewall step-up to reveal, full audit of every access, rotation/expiry, SSRF/injection guards. **`gitleaks protect --staged` = 0 before every commit.** Flag-gate the rollout (default off → byte-identical resting), with a rollback.

## 🔑 THE SEAM (why Vault matters now)
The Video Studio "Universal Provider/Connector Framework" (being designed in the main session) calls a
`get_secret(tenant, key_ref)` seam for all API keys + self-hosted creds. Today that seam uses the existing
key-store/firewall; **Vault is the production backend that slots behind it.** Design Vault to BE that backend
(same `get_secret`/`put_secret` contract) so the framework upgrades transparently when Vault ships.

## 🖥️ BOX ACCESS + CREDS (share these OUT-OF-BAND — never commit)
- Backend (voice/API) box: `famit@168.144.153.145` (SSH key `id_ed25519`). Source at `/opt/famit-agent/`.
- Frontend FORTRESS box: `root@143.110.247.249`, panel at `/opt/famit-panel` — deploy recipe in `MASTER_PLAN.md §6`.
- Credentials live in `fortress/cred.md` + `lead/ALL_CREDENTIALS.md` (NOT in git). Share with the teammate
  via one-time-secret / encrypted, never in this file or any commit.

## ▶️ HOW TO BUILD (the teammate's first move)
Open an ultracode session in `C:\Users\kunal\Desktop\caps`, say *"read VAULT-HANDOFF.md and follow it"*, then
launch an ultracode **Workflow** per the build waves in `VAULT-MASTER-PLAN.md` — backend on Opus, frontend on
Sonnet + frontend-design, ONE box-mutating wave at a time, each earner-gated + flag-gated + verified + committed
(gitleaks 0) + logged to the WORKFLOW_LEDGER. Build the encrypted store + `get_secret`/`put_secret` first, then
the PIN-gated reveal + audit, then the crazy Vault UI.
