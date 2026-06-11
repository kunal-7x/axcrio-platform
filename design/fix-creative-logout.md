# FIX — Creative Studio auto-logout (read-only diagnosis)

**Symptom (founder):** clicking `/creative` (or any sub-page) instantly logs him out → back to `/login`.

**Verdict:** NOT the Control Layer. NOT a 402/404. The AI Asset Service (`:8310`) is now
LIVE and reachable (the old 504 blocker is gone), but it **401s every gated `/api/assets/*`
route** because it can't authenticate the panel's login token — and the panel's `handle401`
turns that 401 into an instant logout. Reproduced live below.

---

## 1. Reproduction (live, https://panel.famit.in)

With a credential the MONOLITH accepts (`X-Auth: FamitCall2026`; `/api/me` and `/api/campaigns` → 200):

| Route | Result |
|---|---|
| `GET /api/assets/status` | **200** `{config.enabled:true}` (the only un-gated route) |
| `GET /api/assets/providers` | **401** `{"error":"unauthenticated"}` |
| `GET /api/assets/assets?limit=6` | **401** |
| `GET /api/assets/brand-kits` | **401** |

The same token that authenticates the whole monolith is REJECTED by the asset service.

## 2. The logout chain (frontend)

1. `/creative` (`app/creative/page.tsx`) mounts → `useAssetStatus()` → `getAssetStatus()`
   hits `/api/assets/status` → **200, `enabled:true`** → page renders the FULL studio (not dormant).
2. On `enabled` it immediately fires the gated reads: `getBrandKits()`, `listAssets({limit:6})`
   (`page.tsx:64,71-72`), and `CreatePanel` calls `getProviders()`. Each → **401**.
3. Every `lib/assets.ts` call runs `await handle401(res)` FIRST (`lib/assets.ts:42-49`):
   ```ts
   async function handle401(res){ if(res.status===401){ localStorage.removeItem("famit_token");
     localStorage.removeItem("famit_me"); window.location.href="/login"; throw new Error("Unauthorized"); } }
   ```
   So the 401 → token wiped → hard redirect to `/login`. **Instant logout.**
   (Note: `getAssetStatus`/`getProviders`/`getBrandKits`/`listAssets` have try/catch fallbacks to a
   calm empty/dormant shape, but `handle401` executes its side-effect BEFORE those fallbacks — a 401
   can never reach the graceful path.) `lib/api.ts:16-23` has the identical `handle401`.

## 3. Why the asset service 401s (backend — the real bug)

`ai_asset/auth.py:resolve_tenant` (the injected auth seam) resolves in 2 paths:

- **Path 1 — scoped JWT** (`auth.py:117-140`): verifies the cred as an HS256 **access JWT** signed
  by the shared monolith secret (`access_claims`/`resolve_token`). But the panel's login token is the
  **`tenant_id . hmac(tenant_id, SECRET)` signed token** (caller.py:512-526) or the legacy bare
  password — **NEITHER is a JWT** → path 1 returns nothing.
- **Path 2 — fallback `import caller; caller.resolve_tenant(request)`** (`auth.py:144-151`): this branch
  DOES understand the hmac token + legacy password. **It is DEAD.** The standalone service runs in its
  OWN venv (`/opt/famit-aiasset/.venv`); `import caller` raises
  **`ModuleNotFoundError: No module named 'google'`** (caller.py pulls heavy deps absent from this venv).
  The bare `except` swallows it → `resolve_tenant` returns `None` → 401.

Confirmed on the box:
- `import caller` in the asset venv → `ModuleNotFoundError: No module named 'google'`.
- `import auth` OK but `_ready=False` (path 1 only validates real JWTs anyway).
- Shared secret `/opt/famit-agent/var/secret` IS readable by the `famit` user (the service CAN verify
  hmac itself — it just never does, because the only hmac-aware code path goes through the un-importable `caller`).

So the asset service can authenticate ONLY a properly-signed JWT, while the panel forwards the
hmac/legacy token the rest of the platform uses. Mismatch → 401 → logout.

---

## 4. THE FIX

### 4a. BACKEND (real fix — makes `/creative` work). File `/opt/famit-aiasset/ai_asset/auth.py`.

Teach `resolve_tenant` to verify the **hmac signed token** and the **legacy password** DIRECTLY,
using the shared secret it already loads — instead of depending on the un-importable `caller`. Insert a
Path-1b between the JWT path and the dead `import caller` fallback (the hmac logic is caller.py:521-526):

```python
# 1b) signed hmac token  (tenant_id "." hmac_sha256(tenant_id, SECRET))  — what the panel login mints.
try:
    import hmac, hashlib
    secret = _shared_secret()                 # reads AIASSET_JWT_SECRET_FILE or /opt/famit-agent/var/secret
    if secret and "." in cred:
        tid, sig = cred.rsplit(".", 1)
        expect = hmac.new(secret.encode(), tid.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expect):
            return _normalize({"tenant_id": tid, "id": tid, "role": "admin", "is_admin": True})
except Exception:
    pass
# 1c) legacy bare admin password (== CALLER_PASS / "FamitCall2026") -> admin tenant.
#     OPTIONAL & SECURITY-GATED: only honour if AIASSET_ALLOW_LEGACY_PW=1 (default OFF), because the
#     legacy static password is the #1 un-revocable-admin finding (control-security.md §1.1). The panel
#     forwards the per-tenant hmac token (1b) in normal use, so 1b alone fixes the founder's logout.
```
Add a tiny `_shared_secret()` helper (reuse the existing `_ensure_token_secret()` file-read at
`auth.py:80-87`; it already locates the secret). Then `systemctl restart famit-aiasset`.

*Alternative (heavier, NOT recommended): install caller.py's deps (incl. `google-*`) into the asset
venv so `import caller` works. Bloats the service and reintroduces a hard coupling — the 6-line hmac
verify above is the surgical fix and keeps the service standalone.*

### 4b. FRONTEND (defensive hardening — do regardless). File `famit-panel/lib/assets.ts`.

The asset service must NEVER be able to log a user out of the whole panel — it's an optional,
dormant-by-design surface. Make `handle401` in `lib/assets.ts` **NOT** wipe the session / redirect;
let the existing try/catch fallbacks resolve a 401 to the calm dormant/empty state (same as a 503):

```ts
// assets-service 401 must NOT nuke the panel session (it's optional, dormant-safe).
async function handle401(_res: Response) { /* no-op: 401 is handled as a soft failure below */ }
```
and in `getAssetStatus`/`getProviders`/`getBrandKits`/`listAssets`, treat `res.status===401` exactly
like `503/404` → return the empty/`{enabled:false}` shape. `lib/api.ts handle401` (the MONOLITH client)
is the ONE place allowed to log out, and it stays as-is. Net: even if `:8310` mis-auths, `/creative`
shows the dormant card instead of ejecting the user. Then rebuild + FORTRESS-deploy the panel.

**Order:** ship 4a first (lights up Creative Studio for real); 4b is the seatbelt so a future asset-auth
regression can't ever log the founder out again. Backend change is additive + gated → no risk to the
live earner (monolith `/api/*` untouched; regression-gate `/campaigns /leads /me` 200 + services active).
