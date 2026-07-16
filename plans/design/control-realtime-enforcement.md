# Control Layer — Real-Time Propagation + Fail-Closed Enforcement

> Tier-0 Foundation Control Layer. Sibling to `design/spec-control-layer.md` (§3 enforcement, §6 real-time).
> This doc DEEPENS those two sections into an execution-ready design, web-researched + grounded against the
> live seams. **READ-ONLY wave — design only, no app code, no deploy, no git.**
>
> Scope: (1) how a permission change reaches an ACTIVE session "instantly"; (2) the single backend
> enforcement choke-point (path → feature_key → assert; 404 for HIDDEN, 402 for LOCKED, fail-closed); how
> the frontend MIRRORS it cosmetically; how URL/API/devtools/saved-token bypass is impossible; (3) caching
> + invalidation of the entitlement map.
>
> Stack: Next.js 15 (App Router, client panel) + FastAPI (`caller.py` on `famit@168.144.153.145`).
> Existing seams it plugs into (all VERIFIED on disk): `useMe`/`getCachedMe` (localStorage `famit_me`, GET
> `/me`) in `lib/auth.ts`; `resolveNav` two-level role filter + `comingSoon` dimmed-pill in
> `components/Sidebar/index.tsx`; `AuthGuard` token-check+redirect in `app/providers.tsx`; backend
> `resolve_tenant` (JWT-additive-over-legacy), the `audit.record` choke-point, lazy import-safe optional
> modules. The entitlement ENGINE (`entitlements.py`, resolution rule, registry) is specified in
> `spec-control-layer.md §2–3`; this doc owns the TRANSPORT, the CHOKE-POINT, and the CACHE.

---

## 0. TL;DR — the decisions

| Question | Decision |
|---|---|
| Real-time channel | **Versioned `/me/entitlements` + ETag/`If-None-Match` short-poll (20–30 s) + on-focus + on-route-change + on-401/402/404**, with a **version-bump on every control write**. SSE is the named, drop-in **Phase-2 upgrade** (one `/me/entitlements/stream` endpoint) — NOT required for correctness. |
| Why not WebSocket | Bidirectional, sticky sessions, heartbeat, proxy/Cloudflare config — overkill; propagation is one-directional (server → client). |
| Why ETag-poll first | Zero new infra, survives Cloudflare/egress-locked box, automatic via `fetch`+`If-None-Match`, and **the poll is cosmetic** — the API already denies a revoked feature on the very next request. |
| Backend enforcement | **ONE dependency-based choke-point** (NOT BaseHTTPMiddleware — see §2.1 gotcha) on the `/api` router: path → `feature_key` → `assert_access`. **HIDDEN → 404, LOCKED → 402, unknown/error → fail-closed deny.** |
| Frontend role | **Cosmetic only.** Nav drop for HIDE, lock-overlay for LOCK, URL-redirect for HIDE — all UX. The backend is the sole authority. |
| No-bypass guarantee | `tenant_id` is token-derived (never body); RLS underneath; the choke-point runs on EVERY `/api/*` before the handler; a saved token / curl / devtools / direct URL all hit the SAME 404/402. |

**Chosen real-time mechanism: versioned-entitlements ETag short-poll (with a server-side version bump on
every control write), SSE as the gated Phase-2 instant-push upgrade.**

---

## 1. REAL-TIME PROPAGATION

### 1.1 The transport decision (researched)

The 2025/2026 consensus for **feature-flag / entitlement** fan-out — a strictly server→client, low-frequency,
small-payload signal — is: **SSE is the "right" streaming transport, WebSocket is overkill, polling is the
pragmatic floor.** ([twocents](https://www.twocents.software/blog/real-time-features-in-saas/),
[dev.to/haraf](https://dev.to/haraf/server-sent-events-sse-vs-websockets-vs-long-polling-whats-best-in-2025-5ep8),
[FlowVerify 2026](https://www.flowverify.co/blog/sse-websockets-polling-guide-2026)). WebSockets "carry real
infrastructure overhead: sticky sessions on load balancers, custom heartbeat logic, authentication
workarounds, and proxy configuration" — none of which an entitlement signal needs.

For THIS platform the **versioned ETag short-poll is chosen as the V1**, with SSE as a clean Phase-2 upgrade,
for three reasons specific to our constraints:

1. **The poll is not the security boundary — the API is (§2).** A client can be ≤30 s stale on the *UI* and
   still NEVER use a revoked feature, because the backend choke-point denies it on the next request. So we do
   not need millisecond push for *correctness*; we need it only for *UI freshness*. This collapses the
   real-time problem from "hard" to "cheap."
2. **Infra reality (FORTRESS box):** the frontend is Cloudflare-fronted and the backend is egress-locked with
   a strict DO firewall. A long-lived SSE/WS stream through Cloudflare needs proxy buffering off + idle-timeout
   handling; a stateless poll just works through any proxy/CDN with zero config
   ([IO Tools](https://iotools.cloud/journal/websockets-vs-sse-vs-long-polling/)).
3. **It reuses an existing seam.** `useMe()` already loads `/me` on mount and caches in localStorage. A sibling
   `useEntitlements()` that polls `/me/entitlements` is a copy of a tested pattern, not new machinery.

### 1.2 The versioned-entitlements contract

```
GET /me/entitlements
  Headers (req):  Authorization: Bearer <jwt>   (or X-Auth legacy)
                  If-None-Match: "<etag>"        (the client's last-seen version, optional)
  Response 200:   ETag: "ent:<tenant_id>:<version>"
                  Cache-Control: private, no-cache    # must revalidate, never serve stale silently
                  body: { version, status, plan, modes: { feature_key: "on"|"hidden"|"locked", ... } }
  Response 304:   (empty body) when If-None-Match == the current "ent:<tenant>:<version>"
```

- `version` is a **monotonically increasing per-tenant integer** (stored next to the entitlement data; bumped
  on EVERY control write — see §1.4). It is the cache key AND the real-time signal.
- The **ETag = the version**, so polling is a conditional GET: a 304 is a few bytes and **touches no DB / does
  no entitlement resolution** — exactly GitLab's Redis-ETag pattern
  ([GitLab polling docs](https://docs.gitlab.com/development/polling/),
  [Wikipedia ETag](https://en.wikipedia.org/wiki/HTTP_ETag)). The full `modes` map is recomputed and sent only
  on the rare 200 (a real change).

### 1.3 Client behaviour (`lib/entitlements.ts`, NEW — mirrors `lib/auth.ts`)

A single client hook `useEntitlements()` (provider-mounted once, like `useMe`):

- **Loads once on mount** from cache (`localStorage['famit_ent']`) for instant first paint, then revalidates.
- **Polls** `GET /me/entitlements` with `If-None-Match: <cached etag>` on an interval
  (`NEXT_PUBLIC_ENT_POLL_MS`, default **25 000 ms**). A 304 = no-op (cheap). A 200 = swap the map, bump the
  in-memory version, re-render nav, and **if the CURRENT page's `feature_key` just became `hidden`/`locked`,
  bounce/overlay immediately** (downgrade-while-viewing).
- **Refreshes opportunistically** (so the *felt* latency is near-zero without a stream):
  - on **`visibilitychange` → visible** (tab refocus),
  - on **route change** (`usePathname` effect),
  - on **any `402`/`404`/`401` from a data fetch** (the API just told us something changed → re-pull the map
    and reconcile the UI; this is the self-healing path that makes staleness invisible).
- Exposes `modeOf(key) → "on"|"hidden"|"locked"`, `isHidden(key)`, `isLocked(key)`, `version`, `status`.
- **Fail-closed on the client too** for *cosmetics*: if the map can't load AND there's no cache, render the
  **minimal core-only** nav (login/settings) rather than flashing every module — same stance `Sidebar` already
  takes while role is unknown. (The backend remains authoritative regardless.)

### 1.4 Server side: the version bump (the actual "real-time" mechanism)

Every `/admin/*` control mutation (set global flag, set per-vendor override, change plan, change status) ends
with a single best-effort call:

```
entitlements.bump_version(target_tenant_id)      # ++version, invalidate the in-proc cache + the ETag store
```

- For a **global flag** or a **plan edit**, bump the version of **every affected tenant** (all tenants for a
  global flag; all tenants on that plan for a plan edit). Cheap: it's an integer increment + a cache evict, not
  a recompute. (Recompute happens lazily on each tenant's next 200.)
- The bump is what turns the next poll (or focus-refresh, or post-402 refresh) into a 200-with-new-modes.
- **This is the entire "propagate across active sessions instantly" guarantee at the data layer:** a control
  write makes the old ETag stale → the next conditional GET from any of that tenant's open tabs returns the new
  map. With the 25 s poll + focus + post-deny refresh, the worst-case UI lag is one poll interval, and the
  *enforcement* lag is **zero** (next API call denies).

### 1.5 Phase-2 SSE upgrade (named, not built this wave)

When a true sub-second UI flip is wanted, add **one** endpoint `GET /me/entitlements/stream` (SSE):

- The handler holds the request open and writes `event: entitlements\ndata: {version}\n\n` whenever
  `bump_version(tenant)` fires for the connected tenant (in-proc pub/sub; multi-worker → a tiny Redis/Postgres
  `LISTEN/NOTIFY` fan-out keyed on `tenant_id`).
- The client `EventSource` (or a fetch-stream, since `EventSource` can't send an `Authorization` header — pass
  the token as a short-lived query param or use a fetch-based SSE reader) just calls the **same**
  `revalidate()` used by the poll on each event. SSE here carries only the *signal*; the authoritative map
  still comes from `GET /me/entitlements` (so the stream payload stays tiny + the resolution logic stays in one
  place). SSE's spec-level **auto-reconnect** (the `retry:` field) + `Last-Event-ID` make it robust through
  drops ([dev.to/polliog](https://dev.to/polliog/server-sent-events-beat-websockets-for-95-of-real-time-apps-heres-why-a4l)).
- **The poll stays as the fallback** (if the stream drops on a flaky mobile network, the 25 s poll still
  converges). Defense-in-depth: stream for speed, poll for guaranteed convergence.

> Decision: ship the **poll** (correctness-complete, infra-free), keep SSE as a one-endpoint Phase-2 that
> reuses the SAME `bump_version` signal and the SAME `revalidate()` client path — so the upgrade is additive,
> not a rewrite.

---

## 2. BACKEND ENFORCEMENT — the real boundary (fail-closed)

> **Iron rule (spec §9.1): the frontend is theatre; this choke-point is what actually stops a saved token, a
> curl, or devtools.** Every claim below is about the BACKEND.

### 2.1 Why a DEPENDENCY, not `BaseHTTPMiddleware` (researched gotcha)

A naive instinct is a single `@app.middleware("http")` that 404s/402s. **This is a trap in FastAPI/Starlette:**
custom middleware runs *outside* Starlette's `ExceptionMiddleware`, so **raising `HTTPException` inside
middleware does NOT hit the registered handlers — it surfaces as a generic 500**
([FastAPI discussion #10404](https://github.com/fastapi/fastapi/discussions/10404)). A 500 would *leak* (it's
distinguishable from a real 404) and break the no-information-leak guarantee.

Two correct options; **we choose (B)** for clean per-route semantics and because it lives inside the exception
boundary and the existing auth-dependency flow:

- **(A) Pure middleware** — allowed, but it must **`return JSONResponse(status_code=...)` directly**, never
  raise. Path→feature_key mapping happens before `call_next`. Works, but it's blunt (no access to the resolved
  route) and you hand-roll the response.
- **(B) A router-level / global `Depends` enforcer** — `enforce_entitlement(request, tenant=Depends(resolve_tenant))`
  added to the `/api` router's `dependencies=[...]` (or wrapped into the existing auth dependency). It runs
  inside `ExceptionMiddleware`, so it can **raise `HTTPException(404)` / `HTTPException(402)` cleanly**, it
  already has the authenticated `tenant`, and it composes with the `can()`/`need_auth` deps the codebase
  already uses. **This is the choke-point.** ✅

### 2.2 The choke-point logic

```
def enforce_entitlement(request, tenant = Depends(resolve_tenant)):
    if not CONTROL_ENABLED:            # ship default-OFF (resting state byte-identical)
        return
    key = feature_key_for_path(request.method, request.url.path)   # registry api_prefixes → feature_key
    if key is None:
        # path maps to NO registered feature. Core/auth/health paths are explicitly allow-listed
        # (login, /me, /me/entitlements, /health, settings, wallet-pay). Anything else unknown →
        # FAIL-CLOSED: deny. (A new module that forgot to self-register is denied, not silently open.)
        if is_core_or_allowlisted(request.url.path):
            return
        raise HTTPException(404)        # fail-closed: unknown, non-core → does-not-exist
    mode = entitlements.mode_for(tenant["tenant_id"], key)   # cached; status/override/plan/global resolved
    if mode == "hidden":
        audit.record(action="control.denied", channel="control", meta={...,"reason":"hidden"})  # best-effort
        raise HTTPException(404)        # no existence leak — indistinguishable from a real 404
    if mode == "locked":
        raise HTTPException(402, detail={"error":"locked","feature":key,"upgrade":True})
    return                              # "on" → proceed to the handler
```

- **HIDDEN → 404**, deliberately indistinguishable from "route doesn't exist." A vendor cannot even *confirm
  the feature exists* by probing the URL/API. (403 would leak "exists but forbidden"; we do not use 403 for
  hidden.) This matches the security stance that fail-closed hiding should not reveal the resource, and the
  HTTP semantics that **403 is "you can't, even if you try harder"** vs the 402 "pay to unlock" we want for
  LOCK ([MDN 402](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/402)).
- **LOCKED → 402 Payment Required**, the *intended* curiosity/upsell signal. The body carries
  `{error:"locked", feature, upgrade:true}` so the UI renders the overlay and the AI Copilot speaks the upsell
  line. 402 is the modern API-monetization status: "the resource is available — but locked behind a payment
  requirement" — the exact founder semantics ([SatGate](https://satgate.io/blog/http-402-payment-required-use-cases),
  [Abstract API 402 guide](https://www.abstractapi.com/guides/http-status-codes/402)). Research note: "402 means
  *you can have it if you pay*, 403 is *you can't*."
- **Unknown / resolution error / suspended-status → fail-closed DENY** (404). A bug or a missing registry row
  defaults to LESS access, never more (spec §7.4).
- **Core floor:** `/login`, `/me`, `/me/entitlements`, `/health`, settings, wallet-pay are allow-listed and
  bypass — so a misconfiguration can never lock a vendor (or the admin) out of authenticating, reading their
  own entitlements, or paying to upgrade (spec §2.1 `is_core`, §7.5).

### 2.3 Path → feature_key mapping

The `feature_registry.api_prefixes` column (spec §2.1) is the map. `feature_key_for_path` does a
**longest-prefix match** of the request path against the registry's `api_prefixes` (e.g. `/calls/export` →
`engage.calls.export` beats `engage.calls` for `/calls`). Built once into an in-memory prefix trie at startup
+ on registry change, so the lookup is O(path-segments), not a scan. **CI guard (spec §8.11):** every mounted
router prefix MUST have a registry row, else the build fails — closing the "new module forgets to register →
ungoverned" hole at the source rather than relying only on the runtime fail-closed.

### 2.4 Why this is genuinely un-bypassable

| Attack | Why it fails |
|---|---|
| Direct URL in browser | The page is a thin client; data comes from `/api/*`. Every `/api/*` request passes the choke-point → 404/402. The page renders nothing it isn't entitled to. |
| Saved/replayed token (curl/Postman) | `tenant_id` is derived from the **token**, never the body (existing invariant). The choke-point resolves THAT tenant's modes and denies. A leaked token is also scoped to its own tenant by RLS. |
| Devtools — flip a React state / unhide a nav item | Pure cosmetics. The unhidden link still calls `/api/*` → 404/402. No client mutation changes the server's answer. |
| Edit `localStorage['famit_ent']` to set everything `on` | The client cache is advisory only. The server recomputes from its own store on every request; the forged cache changes nothing server-side. |
| Body tenant spoofing (`tenant_id=<victim>`) | Ignored — tenant is token-derived; RLS GUC is set to the attacker's own tenant. (The codebase's repeated body-tenant lesson; the control routes keep token-derivation.) |
| Hit a hidden feature to confirm it exists | Returns the SAME 404 as a nonexistent route. No timing/error-shape difference (resolution is O(1) cached). |
| Race a revoke (use the feature in the 25 s poll window) | The poll window only affects the UI. The API choke-point reads the live (version-bumped, cache-invalidated) map → denies immediately. Enforcement lag = 0. |

### 2.5 Coverage of the non-HTTP surfaces (the founder's "everywhere")

- **AI Copilot / AI Manager:** it actuates tools over the **same `/api/*` loopback** (per
  `workforce/tools/transport.py`, mints a per-run RLS-scoped token). So the choke-point ALREADY gates the
  Copilot's tool calls — a hidden/locked feature returns 404/402 to the tool, and the Copilot must surface the
  upsell line instead of the data (spec §8.6, C10). Additionally, the Copilot loads `/me/entitlements` up front
  to refuse *in the prompt/tool layer* before even attempting the call (defense-in-depth: it shouldn't try).
- **Voice agent (`agent.py` hot loop):** NOT wrapped at the per-request layer (latency moat). Entitlement is
  read at the **run-gate** (`/run`, status check) and the AI-decision actuation layer — never in the per-turn
  voice path (spec §11). Suspended status blocks NEW dials at the run-loop gate; in-flight calls finish (§8.2).

---

## 3. FRONTEND MIRROR — cosmetic, never authoritative

The frontend reproduces the backend's verdict for UX only. Three behaviours, all reusing existing seams:

1. **Nav HIDE** — extend `resolveNav` (`components/Sidebar/index.tsx`). It already drops children by `roles`;
   add a parallel filter: a child whose `feature_key` resolves to `hidden` is dropped exactly like an
   out-of-role child, and a group with no surviving children disappears (the existing empty-group rule). The
   feature_key lives on the nav node in `contstants/navigation.tsx`. One filter added to a tested function.
2. **Nav LOCK** — a `locked` child renders like the EXISTING `comingSoon` pattern in `Sidebar/Dropdown`
   (dimmed, non-link `<div>`, a **"Locked"** pill instead of "Soon"). Pattern already in the codebase; only the
   pill label/colour differs.
3. **Page LOCK overlay** — `components/LockOverlay` (NEW, assembled from the existing `Card` + `.state-block`
   blur + `Modal` styles): the page chrome blurred behind an upsell panel, zero interaction. Rendered when
   `modeOf(routeKey) === "locked"` OR when a data fetch returns **402** (self-healing if the map is stale).
4. **Page HIDE / direct-URL** — the route component (or a small `<EntitlementGuard>` wrapper, sibling to
   `AuthGuard`) calls `isHidden(routeKey)`; if hidden, `router.replace("/")` — the exact shape `AuthGuard`
   already uses for no-token. Also redirect on a **404** from the page's primary fetch.

> **These are cosmetic. The backend 404/402 (§2) is the lock.** The frontend never *grants* access — at most it
> spares the user a flash of a page they can't use. If the frontend were bypassed entirely, the backend still
> denies. This separation is the whole security model (spec §9.1).

---

## 4. CACHING + INVALIDATION (edge → app → client)

Three cache layers, each with an explicit invalidation tied to the **version**:

| Layer | What's cached | Invalidation | Notes |
|---|---|---|---|
| **In-proc engine** (FastAPI worker) | `resolve_modes(tenant) → {key:mode}` + the tenant `version` | `bump_version(tenant)` evicts the entry (and an ETag-store entry) | The hot path. `mode_for` is O(1) off this. Multi-worker: each worker holds its own dict + a cheap version check against the store on a TTL (≤5 s) OR a Postgres `LISTEN/NOTIFY` evict, so a bump on worker A invalidates worker B within the TTL. |
| **HTTP / edge (ETag)** | The `/me/entitlements` 200 body, keyed by `ETag: ent:<tenant>:<version>` | A version bump changes the ETag → the next `If-None-Match` is a *miss* → 200 with the new body; until then, 304s are served cheaply | `Cache-Control: private, no-cache` so Cloudflare/browser **always revalidate** (never serve a stale entitlement silently). This is the GitLab Redis-ETag model: "304 without querying the database at all" on a hit ([GitLab](https://docs.gitlab.com/development/polling/)). |
| **Client (localStorage `famit_ent` + in-memory)** | Last `{version, etag, modes}` | Replaced on any 200; reconciled on focus/route-change/post-402-404 | Instant first paint; advisory only (server is authoritative). Fail-closed to core-only nav if absent. |

**Edge-caching cautions (researched):** entitlements "should be cached cautiously, include a short TTL, and
propagate revocations quickly" ([SatGate](https://satgate.io/blog/http-402-payment-required-use-cases)). Hence
`private, no-cache` (revalidate every time) rather than a positive `max-age` — a revoke must never be masked by
a fresh cache window. The ETag makes "revalidate every time" cheap (304s), giving us *both* low load *and*
instant revocation visibility ([web.dev HTTP cache](https://web.dev/http-cache/),
[Simon Hearne caching](https://simonhearne.com/2022/caching-header-best-practices/)).

**Crucial:** the `/api/*` enforcement choke-point (§2) reads the **in-proc engine cache**, which is invalidated
synchronously on a same-worker bump and within ≤5 s cross-worker. So even if the *client's* ETag cache lags,
the **enforcement** is never stale beyond the worker-sync window — and a single-worker deployment (our box)
makes it exactly zero.

---

## 5. INVARIANTS / EDGE CASES (carried from the spec, transport/enforcement-specific)

- **Resting state byte-identical:** `CONTROL_ENABLED=false` → the choke-point returns immediately; `/me/entitlements`
  returns all-`on`; no behaviour change vs today (F2/F4 discipline).
- **No-leak parity:** the 404 for HIDDEN must be byte-identical to a genuine 404 (same body shape, same timing
  class — O(1) cached resolution avoids a timing oracle).
- **Downgrade-while-viewing:** if the active page's feature flips to hidden/locked, the next poll/focus/route
  event bounces or overlays it; and the page's own data fetch will already be returning 404/402, which the
  client treats as a hard signal to reconcile.
- **Self-lockout floor:** core/allow-listed routes bypass enforcement (login, /me, /me/entitlements, health,
  settings, wallet-pay) so no config can brick auth or the upgrade-payment path.
- **Multi-worker correctness:** a bump must invalidate ALL workers (TTL re-check or LISTEN/NOTIFY), else worker
  B serves a stale `on`. Single-worker today → trivially correct; document the LISTEN/NOTIFY requirement before
  horizontal scaling.
- **Audit:** every deny (`control.denied`) and every control write rides the existing immutable `events`
  channel=`control` (best-effort, never breaks the request).

---

## 6. SOURCES

- [Real-Time Features in SaaS: WebSockets, SSE, or Polling?](https://www.twocents.software/blog/real-time-features-in-saas/)
- [SSE vs WebSockets vs Long Polling: What's Best in 2025? (dev.to/haraf)](https://dev.to/haraf/server-sent-events-sse-vs-websockets-vs-long-polling-whats-best-in-2025-5ep8)
- [SSE vs WebSockets vs Polling: 2026 Decision Guide (FlowVerify)](https://www.flowverify.co/blog/sse-websockets-polling-guide-2026)
- [Server-Sent Events Beat WebSockets for 95% of Real-Time Apps (dev.to/polliog)](https://dev.to/polliog/server-sent-events-beat-websockets-for-95-of-real-time-apps-heres-why-a4l)
- [WebSockets vs SSE vs Long Polling (IO Tools)](https://iotools.cloud/journal/websockets-vs-sse-vs-long-polling/)
- [Handling errors in FastAPI middleware — raise HTTPException → 500 (FastAPI discussion #10404)](https://github.com/fastapi/fastapi/discussions/10404)
- [Use Old 403 Authentication Error Status Codes (FastAPI docs)](https://fastapi.tiangolo.com/how-to/authentication-error-status-code/)
- [402 Payment Required (MDN)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/402)
- [HTTP 402 Payment Required: API and Agent Use Cases (SatGate)](https://satgate.io/blog/http-402-payment-required-use-cases)
- [What Is HTTP Status Code 402? (Abstract API)](https://www.abstractapi.com/guides/http-status-codes/402)
- [Polling with ETag caching (GitLab Docs)](https://docs.gitlab.com/development/polling/)
- [HTTP ETag (Wikipedia)](https://en.wikipedia.org/wiki/HTTP_ETag)
- [Prevent unnecessary network requests with the HTTP Cache (web.dev)](https://web.dev/http-cache/)
- [Caching Header Best Practices (Simon Hearne)](https://simonhearne.com/2022/caching-header-best-practices/)
</content>
</invoke>
