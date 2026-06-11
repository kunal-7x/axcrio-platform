# AI Manager — UI fix-list (PIN enrollment missing + /history 404)

Diagnostic pass only. The Control Layer build owns the frontend right now — do
NOT apply these yet; this is the punch-list for the polish pass after that lands.

Date: 2026-06-10. Scoped to `famit-panel/app/ai-manager/*`.

---

## TL;DR (founder's two complaints)

1. **"setup page has NO option to add a PIN"** — correct, and partly by design.
   The `/ai-manager/setup` page only holds the PIN *policy* (from which risk
   level a step-up PIN is demanded). The actual PIN *enrollment* form lives on a
   DIFFERENT page, `/ai-manager/users`. BUT that page currently shows a blank
   "coming soon" state because its backend router is not mounted — so the "Set
   PIN" button never appears. Net effect: there is nowhere in the live UI to
   actually enroll a PIN today. See Finding A + B.

2. **"/ai-manager/history is a 404"** — there is no `history` route. Command
   History lives at `/ai-manager/commands`. See Finding C.

---

## Finding A — PIN enrollment UI EXISTS, but on `/users`, not `/setup`

- `app/ai-manager/setup/page.tsx` — the "Confirmation & PIN" section (lines
  ~267-348) is **policy only**: a `require_pin_for_level` selector (L0-L4) + the
  "max bulk leads without a PIN" number. It deliberately does NOT collect a PIN
  value. A founder looking here for "set my PIN" finds nothing — reasonable
  confusion.
- `app/ai-manager/users/page.tsx` — this is where PIN enrollment actually lives:
  - `SetPinModal` (lines ~627-698): 4/6-digit PIN + confirm, posts to
    `POST /api/ai-manager/pin/set` via `setAimUserPin(userId, pin)` (`_lib.ts:367`).
  - `ResetPinModal` (lines ~700-811): two-step reset.
  - Row buttons "Set PIN" / "Reset PIN" (lines ~352-357) toggle on `u.pin_set_at`.
- So the per-user PIN flow is fully built — it's just **not discoverable from the
  page the founder expected** (Setup), and it only renders once there are user
  rows (which need the backend — Finding B).

**Fix options (pick at polish pass):**
- (a) Add a small "Step-up PIN" card to `/setup` for the *current logged-in admin*
  that posts to a PIN-set endpoint keyed on the tenant (mirrors what we just did
  on the box via `firewall.set_pin(tenant_id, pin)`), and/or
- (b) Add a one-line pointer on `/setup`'s PIN section: "Enroll/manage PINs per
  person under Authorized Users →" linking to `/ai-manager/users`.
- Recommended: do BOTH — (a) for the founder's own step-up PIN (the common case),
  (b) so the policy page cross-links the enrollment page.

## Finding B — the whole AI-Manager surface is DORMANT (router not mounted)

- `_lib.ts:5-14` + every page header comment state the `/ai-manager` backend
  router is **DEFINED-NOT-MOUNTED**. `_lib.ts read()` (lines 127-156) maps
  404/501/503 → `{kind:"dormant"}`, so:
  - `/users` renders the "Authorized users coming soon" `DormantPanel`
    (`users/page.tsx` lines ~254-263) with NO rows and NO "Add user" rows → the
    "Set PIN" buttons are unreachable.
  - `/setup` renders read-only with a "read-only until the service is live"
    banner; Save is disabled (`formDisabled = !writable || dormant`).
- **Root cause of "can't add a PIN in the UI":** even though the form code exists,
  the dormant gate hides it because `GET /api/ai-manager/authorized-users` 404s.
- **Fix:** this unblocks itself once the AI-Manager backend router is mounted
  (the Control Layer / AIM backend wave). No frontend change strictly required to
  un-hide it — but see Finding A for making it *discoverable*.
- Interim: the founder's tenant PIN ("admin" tenant) has now been enrolled
  directly via the firewall data layer on the box, so the Test Console step-up
  and phone flow have a working PIN even while the enrollment UI is dormant.

## Finding C — `/ai-manager/history` 404

- No `history/` directory exists under `app/ai-manager/` (dirs: overview,
  command-center, test, commands, approvals, capabilities, setup, users,
  sessions/[id]).
- Nav (`contstants/navigation.tsx:71`) points "Command History" →
  `/ai-manager/commands` (which exists: `commands/page.tsx`). So nothing in-app
  links to `/history`; the 404 is from a typed/bookmarked URL or external doc
  using the wrong path.
- **Fix options:** (a) add an `app/ai-manager/history/page.tsx` that redirects to
  `/ai-manager/commands` (cheap alias, kills the 404 for anyone with the old
  URL), or (b) just confirm the correct path is `/ai-manager/commands` and update
  whatever doc/bookmark pointed at `/history`. Recommend (a) — a 2-line redirect
  is the safest.

---

## Backend endpoints these flows expect (for the mounting wave)

From `_lib.ts`:
- `GET /api/ai-manager/authorized-users` → `{users:[...]}`  (gates the whole list)
- `POST /api/ai-manager/authorized-users`                   (add user)
- `PATCH/DELETE /api/ai-manager/authorized-users/:id`
- `POST /api/ai-manager/pin/set` `{user_id, pin}`           (enroll PIN)
- `POST /api/ai-manager/pin/reset/request` `{user_id}`
- `POST /api/ai-manager/pin/reset/confirm` `{user_id, code, pin?}`
- `GET/PUT /api/ai-manager/profile`                         (setup policy)

These map onto the existing `firewall.py` primitives (`set_pin`, `check_pin`,
`has_pin`, `mint_step_up`, `verify_step_up_token`) — the data layer is already
real and proven (PIN just set + verified on the box for tenant `admin`). The
gap is purely the HTTP router that exposes them + the `authorized_users` store.
