"""
twenty_crm.client — thin async HTTP client for a Twenty CRM instance.

Talks to Twenty's auto-generated **Core REST API** (https://twenty.com,
github.com/twentyhq/twenty). Server-to-server ONLY: the workspace API key (a
signed JWT) lives on the Haptica backend and is NEVER exposed to the browser.
Every call is best-effort — transport / auth / rate-limit failures become a
structured ``TwentyError`` the router turns into a calm JSON shape, the same
dormant-safe philosophy the rest of caller.py uses.

Twenty quirks handled here (verified against the v0.32 source + the developer
docs):

* **Auth** — ``Authorization: Bearer <api_key>``
* **Base** — ``<workspace_url>/rest`` for records, ``/rest/metadata`` for schema
* **Filter** — ``?filter=field[op]:value`` (the *colon* form, NOT ``bracket=``);
  ``op ∈ {eq,neq,in,is,gt,gte,lt,lte,startsWith,like,ilike}``
* **Order** — ``?order_by=field[DescNullsLast]``
* **Paging** — ``?limit=N`` (default 60); cursor via ``starting_after`` /
  ``ending_before`` (no offset)
* **depth** — relation-expansion depth. Self-hosted v2.14.4 allows ONLY ``0|1``
  (newer ``main`` allows ``2``); we cap at 1 (one relation level covers every view),
  which is valid on every version.
* **Money** — Currency composite ``{amountMicros, currencyCode}`` — micros = ×1e6
* **Composite fields** — FullName ``{firstName,lastName}``; Emails
  ``{primaryEmail}``; Phones ``{primaryPhoneNumber,...}``; Links (``domainName``)
  ``{primaryLinkUrl,...}``; Address ``{addressCity,...}``
* **Stage** — Opportunity.stage is a *customizable* SELECT enum (defaults
  NEW/SCREENING/MEETING/PROPOSAL/CUSTOMER); read live options from metadata.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

# Singular form for every plural object name we touch — the single-record REST
# envelope wraps the record under the SINGULAR key (e.g. {"data": {"person": …}}).
SINGULAR = {
    "companies": "company",
    "people": "person",
    "opportunities": "opportunity",
    "notes": "note",
    "tasks": "task",
    "noteTargets": "noteTarget",
    "taskTargets": "taskTarget",
}

# Default Twenty opportunity-stage SELECT options (value/label) used as a fallback
# when the live metadata can't be read. The real instance may rename/add options,
# so the router always prefers metadata and only falls back to this.
DEFAULT_STAGES = [
    {"value": "NEW", "label": "New", "color": "red"},
    {"value": "SCREENING", "label": "Screening", "color": "purple"},
    {"value": "MEETING", "label": "Meeting", "color": "sky"},
    {"value": "PROPOSAL", "label": "Proposal", "color": "turquoise"},
    {"value": "CUSTOMER", "label": "Customer", "color": "yellow"},
]


class TwentyError(Exception):
    """A structured failure talking to Twenty. ``status`` mirrors the HTTP code
    (0 = transport/timeout). The router maps these to calm JSON, never a 500."""

    def __init__(self, status: int, message: str, detail: Any = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.detail = detail


class TwentyClient:
    """One short-lived client bound to a single workspace (base_url + api_key).

    Construct per-request (cheap) so a tenant's connection swap is picked up
    immediately and no key is cached across tenants. All methods are async and
    open/close their own ``httpx.AsyncClient``.
    """

    def __init__(self, base_url: str, api_key: str, *, timeout: float = 15.0):
        # Normalise: strip a trailing slash and a trailing /rest|/graphql the user
        # may have pasted, so we can always append the REST path ourselves.
        b = (base_url or "").strip().rstrip("/")
        for suffix in ("/rest", "/graphql", "/api"):
            if b.endswith(suffix):
                b = b[: -len(suffix)].rstrip("/")
        self.base = b
        self.api_key = (api_key or "").strip()
        self.timeout = timeout

    # ── low-level ────────────────────────────────────────────────────────────
    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(self, method: str, path: str, *,
                       params: dict | None = None, json: Any = None) -> Any:
        if not self.base or not self.api_key:
            raise TwentyError(0, "Twenty CRM is not connected")
        url = f"{self.base}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as cli:
                res = await cli.request(method, url, headers=self._headers,
                                        params=params, json=json)
        except httpx.TimeoutException:
            raise TwentyError(0, "Twenty CRM timed out")
        except httpx.HTTPError as e:  # connection / DNS / TLS
            raise TwentyError(0, f"Cannot reach Twenty CRM: {e!s}")
        if res.status_code == 401:
            raise TwentyError(401, "Twenty API key is invalid or expired")
        if res.status_code == 403:
            raise TwentyError(403, "Twenty API key lacks permission for this action")
        if res.status_code == 429:
            raise TwentyError(429, "Twenty rate limit hit — try again in a moment")
        if res.status_code == 404:
            raise TwentyError(404, "Not found in Twenty CRM")
        if res.status_code >= 400:
            # Surface Twenty's own message when present, else a generic one.
            msg = ""
            try:
                body = res.json()
                msg = (body.get("messages") or [body.get("error")] or [""])[0] \
                    if isinstance(body, dict) else ""
                if not msg and isinstance(body, dict):
                    msg = str(body.get("message") or body.get("error") or "")
            except Exception:  # noqa: BLE001
                pass
            raise TwentyError(res.status_code, msg or f"Twenty request failed ({res.status_code})")
        if res.status_code == 204 or not res.content:
            return {}
        try:
            return res.json()
        except Exception:  # noqa: BLE001
            raise TwentyError(res.status_code, "Twenty returned a non-JSON response")

    # ── envelope helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _unwrap_list(resp: Any, plural: str) -> tuple[list[dict], dict]:
        """Pull the record list + pageInfo/totalCount out of Twenty's envelope,
        tolerant of the shapes seen across versions:
          {"data": {plural: [...]}, "pageInfo": {...}, "totalCount": N}
          {plural: [...]}                  {"data": [...]}        [...]"""
        page = {}
        if isinstance(resp, list):
            return resp, page
        if not isinstance(resp, dict):
            return [], page
        page = {
            "totalCount": resp.get("totalCount"),
            "pageInfo": resp.get("pageInfo") or {},
        }
        data = resp.get("data", resp)
        if isinstance(data, list):
            return data, page
        if isinstance(data, dict):
            recs = data.get(plural)
            if isinstance(recs, list):
                return recs, page
            # last resort: a dict-of-records under some key
            for v in data.values():
                if isinstance(v, list):
                    return v, page
        return [], page

    @staticmethod
    def _unwrap_one(resp: Any, plural: str) -> dict:
        singular = SINGULAR.get(plural, plural)
        if not isinstance(resp, dict):
            return {}
        data = resp.get("data", resp)
        if isinstance(data, dict):
            if isinstance(data.get(singular), dict):
                return data[singular]
            if isinstance(data.get(plural), dict):
                return data[plural]
            # a bare record dict
            if "id" in data:
                return data
        return {}

    # ── REST verbs ────────────────────────────────────────────────────────────
    @staticmethod
    def _safe_depth(d) -> int:
        # Cap at 1: valid on every Twenty version (self-host v2.14.4 rejects depth=2)
        # and one relation level is all any Haptica view needs.
        try:
            return max(0, min(int(d), 1))
        except Exception:  # noqa: BLE001
            return 1

    async def list(self, plural: str, *, filter: str | None = None,
                   order_by: str | None = None, limit: int = 60,
                   depth: int = 1, starting_after: str | None = None) -> tuple[list[dict], dict]:
        params: dict[str, Any] = {"limit": max(1, min(int(limit or 60), 60)),
                                  "depth": self._safe_depth(depth)}
        if filter:
            params["filter"] = filter
        if order_by:
            params["order_by"] = order_by
        if starting_after:
            params["starting_after"] = starting_after
        resp = await self._request("GET", f"/rest/{plural}", params=params)
        return self._unwrap_list(resp, plural)

    async def get(self, plural: str, rec_id: str, *, depth: int = 1) -> dict:
        resp = await self._request("GET", f"/rest/{plural}/{rec_id}",
                                   params={"depth": self._safe_depth(depth)})
        return self._unwrap_one(resp, plural)

    async def create(self, plural: str, data: dict, *, depth: int = 1) -> dict:
        resp = await self._request("POST", f"/rest/{plural}", params={"depth": depth}, json=data)
        return self._unwrap_one(resp, plural)

    async def update(self, plural: str, rec_id: str, data: dict, *, depth: int = 1) -> dict:
        resp = await self._request("PATCH", f"/rest/{plural}/{rec_id}",
                                   params={"depth": depth}, json=data)
        return self._unwrap_one(resp, plural)

    async def delete(self, plural: str, rec_id: str) -> None:
        await self._request("DELETE", f"/rest/{plural}/{rec_id}")

    # ── connection / schema probes ────────────────────────────────────────────
    async def ping(self) -> dict:
        """Verify the connection cheaply. Returns {ok, workspace?, error?}. Hits a
        1-row companies read (always present in a standard workspace) so a bad
        URL / key / unreachable host is caught at connect time, not first use."""
        try:
            await self._request("GET", "/rest/companies", params={"limit": 1, "depth": 0})
            return {"ok": True}
        except TwentyError as e:
            return {"ok": False, "status": e.status, "error": e.message}

    async def opportunity_stages(self) -> list[dict]:
        """Live stage SELECT options from the metadata API, falling back to the
        documented defaults. Never raises — a metadata hiccup just yields defaults."""
        try:
            resp = await self._request("GET", "/rest/metadata/objects",
                                       params={"limit": 60})
            objs, _ = self._unwrap_list(resp, "objects")
            for o in objs:
                name = (o.get("nameSingular") or o.get("name") or "").lower()
                if name in ("opportunity", "opportunities"):
                    fields = o.get("fields") or {}
                    flist = fields.get("edges") if isinstance(fields, dict) else fields
                    flist = flist if isinstance(flist, list) else []
                    for fe in flist:
                        f = fe.get("node", fe) if isinstance(fe, dict) else {}
                        if (f.get("name") or "").lower() == "stage":
                            opts = (f.get("options") or [])
                            parsed = [
                                {"value": op.get("value"), "label": op.get("label") or op.get("value"),
                                 "color": op.get("color")}
                                for op in opts if isinstance(op, dict) and op.get("value")
                            ]
                            if parsed:
                                return parsed
        except Exception:  # noqa: BLE001 — metadata is best-effort
            pass
        return list(DEFAULT_STAGES)


async def gather_limited(coros: list, *, concurrency: int = 4) -> list:
    """Run awaitables with a small concurrency cap (Twenty rate-limits 100/min).
    Exceptions are captured per-item (returned in place) so one failure never
    sinks the whole batch."""
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _run(c):
        async with sem:
            try:
                return await c
            except Exception as e:  # noqa: BLE001
                return e

    return await asyncio.gather(*[_run(c) for c in coros])
