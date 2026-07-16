"""ai_manager.tools.transport — the authenticated localhost loopback to caller.py /api.

The LIVE catalog (catalog.py) reaches the REAL platform endpoints over this transport instead of
duplicating any business logic. Two functions only — `call()` (loopback to caller.py) and
`call_service()` (loopback to an external micro-service, e.g. the AI Asset Service :8310) — both
returning the uniform `{ok, data, reason, status}` shape the catalog's `_result`/`_result_parkable`
consume (spec §I, tools-catalog-contract §3).

DORMANT until `config.aiwf_service_token()` is set: while dormant every call returns
`{"ok":False,"reason":"transport_dormant","status":404,"data":{}}` (which `_result_parkable` maps to
a clean `not_configured` park). `httpx` is imported LAZILY — absent or any connection error degrades
to `{"ok":False,"reason":"transport_error","status":503,"data":{}}`. Every request carries the per-run
Bearer (`Authorization: Bearer <run_token>`) so the loopback is RLS-scoped to the run's org, plus the
shared `X-Auth: config.x_auth_value()` header. Import does ZERO I/O; nothing here ever raises.
"""
from __future__ import annotations

from typing import Optional

# Default timeout (seconds) for a loopback request: connect should be near-instant on localhost,
# read bounded so a stuck route degrades to transport_error rather than hanging the run.
_TIMEOUT_S = 15.0


def _dormant() -> dict:
    """Transport is dormant until AIWF_SERVICE_TOKEN — a 404 the catalog parks as not_configured."""
    return {"ok": False, "reason": "transport_dormant", "status": 404, "data": {}}


def _error(reason: str = "transport_error") -> dict:
    """httpx absent / connection error / unexpected failure — a 503 (service unreachable) park."""
    return {"ok": False, "reason": reason, "status": 503, "data": {}}


def _headers(run_token: str) -> dict:
    """Auth headers for the loopback. Lazy config import; X-Auth has a safe default so a blank env
    still authenticates against caller.py's legacy X-Auth gate. run_token may be '' (unauthenticated)."""
    from .. import config  # noqa: PLC0415 (lazy — call-time env reads, never at import)

    try:
        x_auth = config.x_auth_value()
    except Exception:  # noqa: BLE001
        x_auth = ""
    return {
        "Authorization": f"Bearer {run_token or ''}",
        "X-Auth": x_auth or "",
    }


def _parse(resp) -> dict:
    """Map an httpx Response -> the uniform {ok, data, reason, status} shape. 2xx -> ok with the JSON
    body as `data`; non-2xx -> ok:False carrying `reason` (server reason if any) + the HTTP `status`."""
    status = getattr(resp, "status_code", 0)
    body = {}
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001 (non-JSON / empty body -> {} data)
        body = {}
    if not isinstance(body, dict):
        body = {"data": body}
    if 200 <= int(status) < 300:
        data = body.get("data") if isinstance(body.get("data"), dict) else body
        return {"ok": True, "data": data or {}, "reason": None, "status": status}
    # non-2xx: prefer a server-supplied reason/detail, else stringify the status.
    reason = body.get("reason") or body.get("detail") or body.get("error") or str(status)
    if not isinstance(reason, str):
        reason = str(reason)
    return {"ok": False, "data": body if isinstance(body, dict) else {}, "reason": reason, "status": status}


def _request(method: str, url: str, *, run_token: str,
             params: Optional[dict] = None, json: Optional[dict] = None,
             data: Optional[dict] = None) -> dict:
    """Lazy-httpx single request against a fully-qualified URL. Never raises; any transport-level
    failure (httpx missing, connect refused, timeout, DNS) -> transport_error/503."""
    try:
        import httpx  # noqa: PLC0415 (lazy — only on a live loopback call)
    except Exception:  # noqa: BLE001
        return _error()
    try:
        with httpx.Client(follow_redirects=False, timeout=_TIMEOUT_S) as cli:
            resp = cli.request(
                (method or "GET").upper(),
                url,
                headers=_headers(run_token),
                params=params or None,
                json=json if json is not None else None,
                data=data if data is not None else None,
            )
        return _parse(resp)
    except Exception:  # noqa: BLE001 — any connection/timeout/protocol failure = unreachable park
        return _error()


def call(method: str, path: str, *, run_token: str,
         params: Optional[dict] = None, json: Optional[dict] = None,
         data: Optional[dict] = None) -> dict:
    """Authenticated loopback to caller.py /api. Returns {ok, data, reason, status}.

    Dormant until AIWF_SERVICE_TOKEN -> {"ok":False,"reason":"transport_dormant","status":404,"data":{}}.
    httpx absent / connection error -> {"ok":False,"reason":"transport_error","status":503,"data":{}}.
    `params` is the GET query-string; `json` and `data` are mutually-exclusive bodies (`data` = a
    FastAPI Form(...) body). Header: Authorization: Bearer <run_token> + X-Auth. Never raises."""
    from .. import config  # noqa: PLC0415 (lazy — dormancy + base URL read at call time)

    try:
        if not config.aiwf_service_token():
            return _dormant()
        base = config.loopback_base()
    except Exception:  # noqa: BLE001 — config glitch degrades to dormant (fail-closed)
        return _dormant()
    url = f"{(base or '').rstrip('/')}{path}"
    return _request(method, url, run_token=run_token, params=params, json=json, data=data)


def call_service(method: str, path: str, *, run_token: str,
                 base: str, json: Optional[dict] = None) -> dict:
    """Authenticated loopback to an external micro-service (e.g. the AI Asset Service :8310) at
    `base+path`. Same {ok, data, reason, status} shape as `call`. The service derives the tenant from
    the per-run Bearer (a body tenant_id is ignored).

    Dormant until AIWF_SERVICE_TOKEN -> transport_dormant/404. httpx absent / connection error ->
    transport_error/503 (the catalog maps 503 -> not_configured park). Never raises."""
    from .. import config  # noqa: PLC0415 (lazy — dormancy gate read at call time)

    try:
        if not config.aiwf_service_token():
            return _dormant()
    except Exception:  # noqa: BLE001
        return _dormant()
    url = f"{(base or '').rstrip('/')}{path}"
    return _request(method, url, run_token=run_token, json=json)
