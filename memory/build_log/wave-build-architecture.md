# Wave: Architecture Documentation (master ARCHITECTURE.md + 6 deep-dives)

> Durable build report for the architecture-documentation wave. READ-ONLY: docs only, no app
> code edited, no deploy, no git. Every box/edge in every doc grounded in real `file:line`.

## 2026-06-11 — SYNTHESIS: master ARCHITECTURE.md written (repo root)

**Deliverable:** `C:\Users\kunal\Desktop\caps\ARCHITECTURE.md` — the single onboarding map a new
Claude-Code teammate reads to understand the whole Famit/Axcrio platform. Assembles the six
`docs/architecture/*.md` deep-dives into one comprehensive, GitHub-renderable document.

**Structure (the 10 required parts, in order):**
1. What-is-this (1 paragraph).
2. System-context Mermaid `graph` (platform + 4 user types + 6 external systems).
3. Container/topology Mermaid `graph` (2 prod droplets + hatchet box, services, ports, VPC,
   Cloudflare, firewalls).
4. Codebase `mindmap` (frontend / backend / sibling services / data / Growth OS / infra planes).
5. Per-area sections (backend, AI-asset, frontend, deployment, growth-os) each pulling in its
   validated Mermaid diagram(s).
6. End-to-end flow `sequenceDiagram`s (closed loop, run-campaign, AI-Manager) + the ER data model
   (`erDiagram` for core 17 tables + wallet) + the request choke-point spine graph.
7. File-map tables (backend / ai-asset / frontend / growth-os — where every major thing lives).
8. Tech stack table.
9. How-to-run + boxes/services/ports/nginx quick-reference.
10. Glossary (the moat, closed loop, Revenue-Truth Signal Loop, strangler, RLS, Control Layer,
    Tenant Zero, Origin Connector, signed ActionPlan, step-up, two enforcement walls).

**Mermaid validation (all GitHub-renderable):** 13 mermaid blocks, 26 fence lines (13 balanced
pairs), all open with ` ```mermaid `. Diagram types: 5×graph, 1×mindmap, 4×sequenceDiagram,
2×erDiagram (the system-context, topology, mindmap are NEW synthesis diagrams; the rest are lifted
verbatim from the already-validated source docs). Verified: every mermaid block has a valid
diagram-type first line; all 5 sequenceDiagram blocks have alt/loop/opt/end balance = 0; mindmap
uses plain-text nodes with only `root((...))` parens (correct root syntax).

## Source deep-dives (the six section docs under docs/architecture/)

| Doc | Covers | Key diagrams |
|---|---|---|
| `01-backend.md` | `caller.py` modular monolith, module mounts, AI-Manager pipeline, auth/control gating | module-dependency graph, AI-Manager sequenceDiagram, auth/control graph |
| `02-ai-asset-service.md` | standalone Creative Studio `:8310`, 2-stage pipeline, providers, wallet reuse | topology graph, generation sequenceDiagram, provider-routing graph, `ai_asset_*` erDiagram |
| `03-frontend.md` | `famit-panel` Next.js, shell/nav, control-layer client, data clients | wiring graph, resolveNav flow, page tree, control sequenceDiagram, client map |
| `04-deployment.md` | live topology, boxes/services/ports, nginx, firewalls, integrations | topology graph, nginx-precedence flowchart, request-path sequenceDiagram |
| `05-growth-os.md` | new microservices monorepo (Phase-0 scaffold), 7 planes, event backbone, Origin Connector | 7-plane flowchart, core-loop sequenceDiagram, Origin-Connector bridge graph |
| `06-flows-data.md` | 5 end-to-end journeys + full PG data model | 5 flow sequenceDiagrams + 7 erDiagrams + context/choke-point graphs |

## Verification notes / open items (honest)
- All grounding inherited from the six source docs, which cite real `file:line` (read from
  `caps/droplet_work`, `caps/famit-panel`, `caps/growth-os` + live boxes read-only via
  ss/systemctl/ufw/docker/nginx).
- Caveat carried forward from 02: the AI-Asset author could not SSH the backend box
  (`168.144.153.145` rejected the provided key) so the live `/status` probe is unverified;
  everything else grounded in code + the live frontend-box nginx.
- Caveat carried forward from 01 (`mod-ai-manager.md` §B4): the live box's `ai_manager` internals
  can be NEWER than the local tree — re-sync before AI-Manager edits.
- No app code edited, no deploy, no git (per the READ-ONLY mandate).
