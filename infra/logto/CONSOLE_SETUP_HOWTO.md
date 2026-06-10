# Logto first-time setup — 10-minute click-by-click (FOUNDER)

Logto (our new self-hosted login/auth system) is **deployed and running** on the hatchet server.
Everything internal is firewalled, so you reach its control panel through a secure SSH tunnel.
This one-time setup creates the admin login + the app config that the platform's backend will later use.

Nothing here touches the live panel.famit.in — it's all on the separate auth server.

---

## STEP 1 — Open the secure tunnel (one command)

Open a terminal **on this same computer** (the SSH key is here) and paste this. Leave it running:

```
ssh -i C:\Users\kunal\.ssh\do-blr-test\id_ed25519 -L 3002:127.0.0.1:3002 -L 3001:127.0.0.1:3001 root@68.183.94.38
```

You'll get a normal server prompt. Keep this window open the whole time. (Closing it just closes the tunnel — nothing breaks.)

## STEP 2 — Open the Logto admin console

In your browser go to:  **http://localhost:3002**

You'll see a "Create admin account" screen (this is the very first visit).

## STEP 3 — Create the admin account

- Pick a **username** (e.g. `admin`) and a **strong password**. Write them in your password manager.
- This is the master login for the auth system. There is no signup page for anyone else — you create users.
- After this you land on the Logto dashboard.

## STEP 4 — Create ONE organization

- Left menu → **Organizations** → **Create organization**.
- Name it **`Famit`** (this represents the first tenant). Save.
- You'll see it gets an **Organization ID** (a random string like `abc123…`). **Copy it** — write it down as `FAMIT_ORG_ID`.

## STEP 5 — Create the API resource

- Left menu → **API resources** → **Create API resource**.
- Name: `Famit API`. **API identifier**: type exactly `https://api.famit.in`  (this is a label, not a website — it does not need to exist).
- Save.

## STEP 6 — Create organization roles + permissions (so login tokens carry access)

- Left menu → **Organization template** (or **Organizations → Roles**).
- Create 3 **organization roles**: `admin`, `manager`, `agent`.
- Create permissions on the `https://api.famit.in` resource: `read`, `write`, `manage_tenants`.
- Give the `admin` role all three permissions; `manager` → read+write; `agent` → read. Save.
  (If the UI is fiddly, at minimum give `admin` the `read` and `write` permissions — that's enough to test.)

## STEP 7 — Create the login app for the panel (OIDC web app)

- Left menu → **Applications** → **Create application** → choose **Traditional Web** (IMPORTANT: pick
  **Traditional Web**, NOT "Single Page App / SPA" — Traditional Web gives you an **App Secret**, which we
  need here. An SPA app has NO secret on purpose, so if you pick SPA you'll hunt for a secret field that
  isn't there.)
- Name: `Famit Panel`.
- **Redirect URI**: `https://panel.famit.in/callback`
- **Post sign-out redirect URI**: `https://panel.famit.in`
- Save. Then on the app page **copy these values** and write them down:
  - **App ID** → `PANEL_CLIENT_ID`
  - **App Secret** → `PANEL_CLIENT_SECRET`  (only Traditional Web shows this — that's why we chose it)
  - (the Endpoint shows `http://localhost:3001` for now — that's expected, it becomes `https://auth.famit.in` later)

## STEP 8 — Create the Management app (for the migration script)

- **Applications** → **Create application** → choose **Machine-to-Machine**.
- Name: `Famit Management`.
- After creating, open its page → **Roles** / **API access** → grant it the **Management API** with role **`all`** (sometimes shown as "Logto Management API").
- Copy and write down:
  - **App ID** → `M2M_APP_ID`
  - **App Secret** → `M2M_APP_SECRET`

## STEP 9 — Make BOTH the admin user AND the Management app members of the Famit org

- **Organizations** → open `Famit` → **Members**:
  - Add your **admin user** → give it the `admin` org role.
  - Add the **`Famit Management` M2M app** → give it the `admin` org role too.
- (A token only carries the `organization_id` the backend needs if the principal is an org member with a
  role. Adding the M2M app here now saves the later backend test from failing confusingly.)

---

## STEP 10 — Send these 6 values back (paste into chat or save to a note)

```
FAMIT_ORG_ID      = ...        (from step 4)
PANEL_CLIENT_ID   = ...        (from step 7)
PANEL_CLIENT_SECRET = ...      (from step 7)
M2M_APP_ID        = ...        (from step 8)
M2M_APP_SECRET    = ...        (from step 8)
ADMIN_USERNAME    = ...        (from step 3, no need to share the password)
```

That's it. Once you send these, the backend integration (later phase) can be wired up. You can close the tunnel window.

> Note: Don't worry that the URLs say `localhost:3001` right now. The real address `https://auth.famit.in`
> gets switched on later when DNS is ready — everything you created here stays valid.
