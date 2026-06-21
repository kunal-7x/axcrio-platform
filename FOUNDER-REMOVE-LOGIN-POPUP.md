# Fix the "Sign in — panel.famit.in" username/password popup

**What it is (one line):** The panel's API backend answers "you're not logged in"
with a header (`WWW-Authenticate: Basic`) that tells the *browser itself* to pop a
native username/password box — instead of letting the panel show its own pretty
`/login` page. We just need to delete that one header line.

**Why incognito didn't help:** The popup isn't a saved password — it's the server
sending that header on every page load, so a fresh/incognito window shows it too.

---

## The exact cause (for whoever makes the change)

- It is **NOT** Cloudflare, **NOT** nginx, and **NOT** the panel (frontend) box.
- It is the **API backend** (`caller.py`, the FastAPI app on the voice/API box).
- When the panel loads it calls `GET /api/me`, `/api/leads`, etc. With no session,
  the backend returns **`401` with `Www-Authenticate: Basic realm="Famit"`**.
  That header is what makes the browser pop the native login box.
- Proven from the edge (this machine, not the box):
  - `GET https://panel.famit.in/api/me`     → `401  Www-Authenticate: Basic realm="Famit"`
  - `GET https://panel.famit.in/api/leads`   → `401  Www-Authenticate: Basic realm="Famit"`
  - `GET https://panel.famit.in/api/billing` → `401  Www-Authenticate: Basic realm="Famit"`
  - (`/`, `/login`, `/super-admin` are clean `200` — only the protected `/api/*` 401s carry the header)
- A previous check missed this because it used a `HEAD` request (returns `405`, no body/headers checked)
  and only looked inside nginx. The header is set by the Python app on **GET** 401s, not by nginx/Cloudflare.

## The one-line fix (on the voice/API box, in `caller.py`)

There is a single helper that builds every 401 — `need_auth()` (~line 592). It is
called in 76 places, so changing this one function fixes the popup everywhere.

Change it from:

```python
def need_auth() -> Response:
    return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Famit"'})
```

to (drop the Basic header; keep the 401 so the panel still redirects to /login):

```python
def need_auth() -> Response:
    # 401 with NO `WWW-Authenticate: Basic` header → the browser does NOT pop a
    # native username/password box; the panel's own /login handles the 401.
    return Response(status_code=401)
```

(Optional, if you want a header for debugging that does NOT trigger the popup:
`headers={"X-Auth-Required": "session"}` — any header name other than
`WWW-Authenticate: Basic` is safe.)

Then redeploy `caller.py` to the box and restart the API service (the usual
caller.py deploy + `systemctl restart famit-caller`). **Do not touch `agent.py`,
the voice agent, the wallet, or the firewall** — only this one line in `caller.py`.

This is a frontend/UX-only change to a 401 response; it does NOT weaken security:
the route still returns 401 and still refuses to return data without a valid session.

## Verify after the change (run on any machine)

```
curl -s -D - -o NUL -X GET https://panel.famit.in/api/me
```
- BEFORE: `HTTP/1.1 401 Unauthorized` + `Www-Authenticate: Basic realm="Famit"`
- AFTER : `HTTP/1.1 401 Unauthorized` and **NO** `Www-Authenticate` line.

Then open `https://panel.famit.in` in a fresh incognito window — it should land
straight on the panel's own `/login` page with **no popup**. Log in normally; the
panel must still refuse data until you're logged in (it will — the 401 stays).

---

## Cloudflare investigation result (why this guide instead of an API fix)

The Cloudflare API token in `fortress/cred.md` (token #1, `cfut_…`) is **zone-list
only** — it can see the `famit.in` zone but is denied on Workers routes, Rulesets,
Transform/Configuration Rules, Page Rules, and Access apps (`code 10000 / 9109`).
Token #2 (`cfat_…`) is **invalid** (`code 1000 Invalid API Token`). So the Cloudflare
config could not be enumerated or edited via API — but it didn't need to be: the
edge serves clean `200`s with no Basic challenge on the app routes, and the Basic
header provably originates from the backend `/api/*` 401s, not from Cloudflare.
