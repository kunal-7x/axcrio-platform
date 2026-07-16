# Control Layer — OSS Engine Research (Entitlement / Feature-Flag / AuthZ core)

> READ-ONLY research wave. Source spec: `caps/Z.MD` + `caps/design/spec-control-layer.md`.
> Question: for the Foundation Control Layer (Tier-0 Super-Admin), do we REUSE a production OSS
> engine for the entitlement/flag/authz core, or BUILD a thin home-grown one on our existing
> Postgres + forced-RLS + Logto stack? This file = the comparison + the verdict + sources.

---

## 0. OUR EXACT NEEDS (the scoring rubric — every tool judged against THIS, not generic "feature flags")

The control layer is **not** a classic dev-rollout flag system. It is a **commercial entitlement +
authorization** layer with a specific, unusual shape:

1. **Multi-tenant, per-vendor.** Same feature, different answer per tenant. Tenant from the verified
   token, never the body (our RLS invariant).
2. **Two control axes, THREE states.** Not on/off — `on | hidden | locked`. HIDE = 404 / vanishes
   everywhere; LOCK = 402 + upsell overlay. No off-the-shelf flag tool models a tri-state with a
   "locked-but-visible-for-upsell" semantic — that is product logic we own regardless.
4. **Global baseline + per-vendor override + plan layer + status floor** — a 5-rule
   most-specific-wins resolution (status → tenant override → plan → global default → parent rolldown),
   **fail-closed** (unknown → hidden).
5. **Plans = bundles of flags + usage limits**, assignable to a vendor (commercial packaging).
6. **Enforced on BOTH frontend and backend.** Backend is the REAL boundary (one FastAPI choke point,
   path→feature_key→assert_access). Frontend HIDE is cosmetic.
7. **Real-time across active sessions** (poll-on-version is acceptable; the API denies immediately so
   stale UI can never USE a revoked feature).
8. **Self-hostable** (DO droplets, egress-locked, no SaaS phone-home — see FORTRESS posture). No new
   datastore if avoidable (Postgres already there; droplet limit hit at 3).
9. **Python/FastAPI** backend (`caller.py` + box modules) + **Next.js** panel.
10. **Immutable audit** of every change (we already have the append-only PG `events` leg).
11. **AI Copilot honors the same map** (entitlement read shared into the prompt/tool layer).

Critical framing: **#2 (tri-state HIDE/LOCK), #4 (our precedence rule), #5 (plan→limits), #6 (the
FastAPI choke point), and #11 (Copilot) are PRODUCT LOGIC we must own no matter what.** No OSS tool
ships them. So the only honest question is: does an OSS tool usefully own the **storage + evaluation +
real-time distribution** plumbing underneath our product logic — cheaper and more reliably than ~1
Postgres table + a 150-line `entitlements.py`?

---

## 1. COMPARISON TABLE

Legend — **Fit** = fit for OUR control-layer need (not general quality). ✅ strong · 🟡 partial · ❌ poor.

| Tool | Category | What it gives us | Self-host fit | Per-tenant + plans model | Real-time propagation | Integration cost vs our PG+RLS+Logto | Fit |
|---|---|---|---|---|---|---|---|
| **OpenFeature** | Flag **spec/SDK** (vendor-agnostic API + provider abstraction) | A standard `boolean/string/object` evaluation API + a **custom-provider** hook (`AbstractProvider`, `resolve_*_details_async`) we can back with OUR engine. Decouples call-sites from the backend. Python + JS SDKs, FastAPI async (`ContextVarsTransactionContextPropagator`). | N/A — it's a client lib, no server. Pairs with any backend or our own. | None natively. **We supply** per-tenant logic inside our custom provider; OpenFeature `EvaluationContext` carries `tenant_id`. | None natively — provider decides (we'd push our version-poll through it). | **LOW.** Wraps our `entitlements.py` as a provider. Keeps call-sites clean and swappable. Doesn't replace the engine — standardizes the *interface* to it. | 🟡→✅ (as a thin facade, not the engine) |
| **Unleash** | Feature-flag platform (server + SDKs) | Mature flag server, **per-environment** configs, activation strategies (% / userId / custom constraints), **Unleash Edge** with millisecond **streaming**, 15+ SDKs, audit, RBAC, OpenFeature provider. Most-starred OSS flag tool. | ✅ Self-host (Docker + its own Postgres). But = **a 4th service + DB** to run/secure on a droplet-capped, egress-locked box. | 🟡 "Environments" ≠ tenants. Per-tenant = custom constraints / context fields; **no first-class plan→entitlement bundle**. Modeling 1 vendor = 1 env doesn't scale to N tenants. | ✅ Streaming via Edge (best-in-class). | **MED-HIGH.** New service+DB+ops; still hand-roll HIDE/LOCK, plans, the FastAPI 404/402 gate, status floor. Buys distribution we can already do with a poll. | 🟡 (overkill; tenant model misaligned) |
| **Flagsmith** | Feature-flag platform (server + SDKs) | MIT, **Python/Django + PostgreSQL** (matches our stack!), Docker self-host <10 min, **per-identity/segment overrides** (closest OSS analog to per-vendor override), remote config (not just bool), 4-eyes approval, audit, RBAC, real-time via Edge. | ✅ Strong self-host; **same DB family (Postgres)** — no Mongo. Still a separate service. | ✅🟡 **Best tenant-shaped of the flag tools:** "identity" ≈ vendor, per-identity traits + segment overrides ≈ per-vendor mode. But "plan = bundle of flags+limits" and tri-state HIDE/LOCK are still ours to add on top. | ✅ Edge API real-time. | **MED.** Closest fit *if* we wanted a managed flag UI, but it brings its own admin UI/DB that duplicates the admin UI we're already porting from Core_2, and still no HIDE/LOCK/plan/limits/402 semantics. | 🟡 (closest flag tool; still not the engine) |
| **GrowthBook** | Feature flags + **experimentation** | Polished UI, strong A/B test + stats. | 🟡 Self-host **but MongoDB-dependent** — a NEW datastore we don't run and don't want (droplet/ops cost, egress posture). | 🟡 Segments/attributes; experimentation-first, not entitlement-first. | 🟡 SDK poll/stream. | **HIGH** (Mongo). Experimentation focus is orthogonal to commercial entitlements. | ❌ (Mongo dep + wrong focus) |
| **Cerbos** | **Authorization** PDP (policy-as-code) | Stateless PDP; **YAML + CEL** resource policies; **excellent multi-tenancy** (tenantId as principal+resource attr → `request.principal.attr.tenantId == request.resource.attr.tenantId`); FastAPI SDK; self-host container / air-gapped; ~17× faster than an OPA impl per their bench. | ✅ Great self-host (single stateless binary, no DB of its own — policies in git/bundle). Egress-friendly. | ✅ ABAC/RBAC per-tenant via attributes; **plans expressible as derived roles / attribute bundles.** But entitlement *data* (which vendor has which mode) is dynamic admin-edited state, NOT git-deployed policy — Cerbos wants policy in code, so our per-vendor toggles would live as *context data we pass in*, with policy just doing the precedence math. | 🟡 No built-in push; you redeploy policy bundles. Dynamic per-tenant data is passed per-request (we already have it). | **MED.** Could own the *precedence rule* as reviewable policy + give clean FastAPI deny. But our rule is ~30 lines of Python; adding a PDP service to evaluate it is heavy. Strong **option for the backend gate** if we want policy-as-code auditability. | 🟡→✅ (best AuthZ fit if we externalize the rule) |
| **OPA** | General policy engine (Rego) | The CNCF standard; Rego is very expressive; huge ecosystem (incl. OPAL). | ✅ Self-host (sidecar/daemon). | 🟡 No built-in tenancy; you implement it in Rego or run per-tenant data. | 🟡 Needs OPAL (below) for live data/policy push. | **MED-HIGH.** Rego learning curve; overkill for a 5-rule precedence. Better for k8s/infra policy than app entitlements (Cerbos itself migrated OFF OPA for app authz). | 🟡 (powerful but heavy for this) |
| **OPAL** | Real-time data/policy **sync** for OPA/Cedar | **WebSocket pub/sub** that pushes policy+data updates to agents in realtime; **`opal-fetcher-postgres`** brings authz state straight FROM Postgres; battle-tested (powers Permit.io). | ✅ Self-host (server + client). | N/A (transport, not a model). | ✅ **This is the real-time piece** — our "version bump → propagate" done properly, sourced from our existing Postgres. | **MED.** Pairs with OPA/Cerbos; if we go policy-engine route, OPAL+postgres-fetcher is the clean real-time spine. Standalone (without a policy engine) it's not useful to us. | 🟡 (valuable ONLY if we adopt OPA/Cedar) |
| **Oso (OSS lib)** | **Authorization** library (Polar DSL) | Embedded in-process AuthZ; Polar models RBAC/ABAC/ReBAC; Python-first; good traceability. | ✅ Library, no service — but the *managed* power (central data, real-time, distribution) is **Oso Cloud** (SaaS, paid, $149+/mo startup). OSS lib alone is policy-in-code. | 🟡 RBAC/ReBAC modeling; per-tenant via facts. Plans = roles/facts. | ❌ OSS lib has no built-in distribution; that's Oso Cloud. | **MED.** Polar is another DSL to learn; the compelling real-time/data features push you to paid Cloud. For a 5-rule precedence it's more concept than we need. | 🟡 (lib fine; value is in paid Cloud) |
| **Casbin (PyCasbin)** | **Authorization** library (model + policy) | Embedded, dependency-light, **Python native**; **RBAC-with-domains = first-class multi-tenant** (same user, different roles per domain/tenant); **Postgres adapter** (policy IN our DB); **filtered/subset policy loading** for big multi-tenant; **watchers** (incl. a Postgres watcher) for cross-node real-time reload. Apache-licensed, no service, no phone-home. | ✅ **Best self-host story** — it's a library that reads policy from OUR Postgres. Zero new service, zero new datastore, egress-safe. | ✅ **RBAC-with-domains maps tenants natively**; policy rows live in our Postgres next to RLS; filtered loading scales per-tenant. Plans = role/grouping policies. Tri-state HIDE/LOCK still our product layer, but the storage+match engine is reused. | 🟡 Watcher (etcd/Postgres/messaging) propagates reloads; for us the version-poll is simpler and Casbin's in-proc enforcer re-evaluates live. | **LOW-MED.** Embeds in FastAPI, policy in our DB, no new infra. Adds a model file + enforcer; we still own precedence/HIDE/LOCK/plans/limits/402. Reuses the *match+store* engine without a server. | 🟡→✅ (the embedded option, if we externalize matching) |
| **Permit.io** | Managed AuthZ + flags (built ON OPA/OPAL) | Polished entitlement+flag UX, ABAC/RBAC/ReBAC, **OPToggles** = OPA-as-source-of-truth for feature visibility (exactly our "authz drives what's visible" idea), AI-agent authz. | 🟡 **Control plane is SaaS**; only the **PDP runs self-hosted**. ABAC/advanced needs the Edge PDP in-network. Core admin = their cloud (phone-home; conflicts with FORTRESS egress-lock + founder's self-host bias). | ✅ Strong plan/entitlement modeling (it's their pitch). | ✅ Via OPAL. | **HIGH (posture).** Great product, but SaaS control plane + per-MAU pricing ($150/mo @10k MAU) and external dependency clash with our egress-locked, own-everything posture. Its OSS parts = OPA+OPAL (evaluate those directly). | ❌ (SaaS control plane; use its OSS parts instead) |
| **Stripe Entitlements** | **Billing-driven** entitlements | Define `feature`s, attach to `product`s; a subscription auto-creates **active entitlements** per customer; `GET /entitlements/active-entitlement` to check. Plan/packaging changes without in-house access logic. | ❌ SaaS (Stripe). External dependency, US billing rails. | ✅ **Plan→feature is literally its model** (best of all for "plan grants features"). | 🟡 Webhook-driven (subscription change → entitlement change). | **HIGH (coupling).** Couples entitlement truth to Stripe billing + network. We have our OWN wallet/billing (F4) and an egress-locked box. Tri-state HIDE/LOCK, the FastAPI gate, status floor are all still ours. | ❌ (couples to Stripe; we own billing already) |

---

## 2. KEY FINDINGS (what the table means for us)

- **Flag platforms (Unleash/Flagsmith/GrowthBook) solve the WRONG half.** They are world-class at
  *dev rollout* (% gates, environments, experiments). Our need is *commercial entitlement* (which
  paying tenant gets which packaged capability, hidden vs locked). The overlap is "boolean per
  context," but every load-bearing piece — tri-state HIDE/LOCK, plan→limits bundles, the precedence
  rule, the 404/402 backend gate, the status floor, the Copilot gate — is product logic none of them
  ship. Adopting one buys real-time distribution (which a version-poll already gives us) at the cost
  of **a 4th service + sometimes a new datastore** on a droplet-capped, egress-locked box, plus a
  **second admin UI** that duplicates the Core_2 admin we're already porting.
- **Of the flag tools, Flagsmith is the closest** (Python/Django + Postgres, per-identity/segment
  overrides ≈ per-vendor override, MIT, clean self-host). If we EVER want a vendor-facing flag UI we
  didn't build, it's the pick. But it still isn't the engine.
- **AuthZ engines (Cerbos/OPA/Oso/Casbin) solve the RIGHT half** (multi-tenant, fail-closed deny, a
  clean FastAPI boundary) but are **heavier than our actual rule**. Our resolution is a deterministic
  5-step precedence over ONE tenant's row set — ~30 lines of Python, not a Rego/Polar/CEL program.
  Cerbos models multi-tenancy beautifully and gives policy-as-code auditability; **Casbin is the only
  one that needs no new service and stores policy in OUR Postgres** (RBAC-with-domains = native
  tenancy, Postgres adapter, filtered loading, watchers).
- **Permit.io and Stripe Entitlements both fail the posture test** — SaaS control plane / billing
  coupling vs our egress-locked, own-everything FORTRESS posture and our existing F4 wallet/billing.
  Their good ideas (OPA-as-visibility-source; plan→feature) are reproducible with OSS parts or already
  ours.
- **OpenFeature and OPAL are the two pieces worth reusing as THIN facades, not as the engine.**
  OpenFeature standardizes the *call-site interface* (a custom provider wrapping our engine → swappable
  later, clean FastAPI/Next.js ergonomics). OPAL is the *real-time spine* — but only earns its keep if
  we adopt OPA/Cedar; with a version-poll we don't need it yet.

---

## 3. RECOMMENDATION — **BUILD the engine, REUSE thin facades. (Mostly BUILD.)**

**Verdict: home-grown entitlement engine backed by Postgres + RLS as the single source of truth — NOT
an adopted flag platform or a PDP service.** The spec's instinct (`spec-control-layer.md` §1-3) is
correct and the research confirms it. Concretely:

### Core (BUILD — own it)
- **One Postgres-backed engine, `entitlements.py`**, exactly as `spec-control-layer.md` §2-3 lays out:
  `feature_registry` + `plans/plan_entitlements/plan_limits` + `tenant_entitlements` overrides + tenant
  `status`, resolved by the deterministic **5-rule most-specific-wins, fail-closed** function. Source
  of truth = our existing **Postgres under forced RLS**. This is small, fully ours, testable, and adds
  **zero new service and zero new datastore** — decisive on a droplet-capped, egress-locked box.
- **The backend boundary is ONE FastAPI dependency** (path→`feature_key`→`assert_access`; hidden→404,
  locked→402, core bypass). This is the real lock and is trivially ours. No external PDP needed for a
  5-rule check; a PDP would add a network hop and a service to secure for logic that is 30 lines.
- **Real-time = the version-bump + poll** (spec §6). The API denies immediately, so the poll is UI
  freshness only. No streaming infra (Unleash Edge / OPAL pub/sub) required for correctness.
- **Audit** rides the existing immutable PG `events` leg (channel=`control`). No new audit tool.

### Thin facades (REUSE — cheap, swappable, low-risk)
- **OpenFeature Python + JS SDK as the evaluation FACADE.** Wrap `entitlements.py` in a custom
  `AbstractProvider` (Python) and a matching JS provider. Call-sites do
  `client.get_string_value(feature_key, "hidden", ctx_with_tenant)`. Cost: ~1 small provider class per
  side. Benefit: clean, standardized call-sites in FastAPI **and** Next.js; `EvaluationContext` carries
  `tenant_id`; and **if** we ever outgrow the home-grown store we can swap the provider to Flagsmith /
  flagd **without touching a single call-site**. This is the cheap insurance that makes "build now"
  safe — we are not painting ourselves into a corner.

### Deferred options (DON'T adopt now; revisit only on a real trigger)
- **Casbin** — keep as the **fallback IF** the precedence rule grows into real RBAC/ABAC complexity
  (e.g., per-action ReBAC across resources). It's the only AuthZ lib that needs no new service and lives
  in our Postgres. Until then, our 5-rule function is simpler than a Casbin model file.
- **Cerbos** — the pick **IF** the founder later wants policy-as-code (reviewable YAML policies in PRs,
  air-gapped PDP). Strong multi-tenancy; adds a stateless service. Not worth it for a 30-line rule today.
- **OPAL** — adopt **ONLY** alongside OPA/Cerbos if/when we need true millisecond push instead of poll.
- **Flagsmith** — the one to reach for **IF** we ever want a ready-made flag admin UI/SDK we didn't
  build (Python/Postgres, self-host). Today it duplicates our Core_2 admin port.
- **Unleash / GrowthBook / Permit.io / Stripe Entitlements** — **NOT for this layer.** Unleash =
  service+DB overkill with a tenant model mismatch; GrowthBook = Mongo + experimentation focus;
  Permit.io = SaaS control plane (posture clash); Stripe = couples entitlement truth to billing we
  already own (F4) and to an external network on an egress-locked box.

### One-line justification
> Our load-bearing logic (tri-state HIDE/LOCK, plan→limits, 5-rule fail-closed precedence, the 404/402
> FastAPI gate, status floor, Copilot gate) is product logic **no OSS tool ships** — so the engine must
> be ours. It's also *small* (≈1 table-set + ≈150 LOC) and maps perfectly onto assets we already run
> (Postgres+RLS, `events` audit, Logto admin authority). Reusing a flag platform or a PDP would add a
> service/datastore and a second admin UI to a droplet-capped, egress-locked box **without removing any
> of the work**. We therefore **BUILD the engine** and **REUSE OpenFeature** as a swap-safe evaluation
> facade, holding **Casbin/Cerbos/OPAL/Flagsmith** as named, trigger-gated upgrade paths.

---

## 4. SOURCES

- OpenFeature — providers / custom provider, intro: https://openfeature.dev/docs/reference/concepts/provider/ · https://openfeature.dev/docs/reference/intro/
- OpenFeature Python SDK (custom `AbstractProvider`, FastAPI async): https://openfeature.dev/docs/reference/technologies/server/python/ · https://github.com/open-feature/python-sdk
- flagd (self-hosted OpenFeature daemon, in-process eval): https://flagd.dev/providers/
- Unleash (self-host, environments, strategies, Edge streaming): https://github.com/unleash/unleash · https://docs.getunleash.io/understanding-unleash/hosting-options · https://www.getunleash.io/
- Flagsmith vs GrowthBook (Python/Postgres vs Mongo; segments; self-host): https://www.flagsmith.com/compare/flagsmith-vs-growthbook · https://flagshark.com/blog/open-source-feature-flag-tools-compared-2026/ · https://www.growthbook.io/blog/best-open-source-feature-flagging-tools-compared
- Cerbos vs OPA (multi-tenancy via attrs, YAML+CEL, FastAPI, self-host, perf): https://www.cerbos.dev/blog/cerbos-vs-opa · https://www.cerbos.dev/ecosystem/fastapi · https://www.cerbos.dev/blog/from-opa-to-our-own-engine-cerbos
- Cerbos vs Permit vs OPA (2026 positioning): https://www.pkgpulse.com/guides/cerbos-vs-permit-vs-opa-authorization-as-a-service-2026
- Oso vs Casbin (Polar vs ACM, language/DB support, self-host vs Oso Cloud): https://stackshare.io/stackups/casbin-vs-oso · https://docs.oso.dev/guides/rbac.html
- Casbin RBAC-with-domains (multi-tenant), Postgres adapter, watchers, filtered loading: https://casbin.apache.org/docs/rbac-with-domains/ · https://pypi.org/project/casbin/ · https://casbin.org/docs/policy-subset-loading/
- Permit.io (SaaS control plane + self-host PDP, OPA/OPAL inside, OPToggles, pricing): https://www.permit.io/open-source · https://docs.permit.io/concepts/pdp/overview/ · https://www.permit.io/pricing
- OPAL (real-time pub/sub for OPA/Cedar; Postgres fetcher): https://github.com/permitio/opal · https://github.com/permitio/opal-fetcher-postgres · https://www.permit.io/blog/introduction-to-opal
- Stripe Entitlements (features→products→active entitlements; billing-driven): https://docs.stripe.com/billing/entitlements · https://docs.stripe.com/api/entitlements/feature
