"""Offline unit test for connectors.base — retry/backoff via a MOCKED httpx transport.

NO real network: every request is served by an httpx.MockTransport scripted with a queue of
responses. Sleep is stubbed (no real backoff delay) and we assert the backoff was CALLED the right
number of times. Run:
    python -c "import sys; sys.path.insert(0,'droplet_work'); import ads_engine.connectors.test_base as t; t.main()"

Asserts:
  1. 200 first try            -> ok, 1 attempt, 0 sleeps.
  2. 429 then 200             -> ok, 2 attempts, 1 sleep (retried).
  3. 503,500 then 200         -> ok, 3 attempts, 2 sleeps (5xx retried).
  4. 400                      -> NOT ok, error=invalid_request, 1 attempt, 0 sleeps (terminal 4xx).
  5. 401                      -> NOT ok, error=permission_denied, 1 attempt.
  6. all 429 (exhausted)      -> NOT ok, error=rate_limited, max attempts, attempts-1 sleeps.
  7. Retry-After honored      -> the recorded sleep delay == the Retry-After value.
  8. SSRF: path escapes host  -> ssrf_blocked, 0 requests issued.
  9. timeout then 200         -> ok after retrying a TimeoutException.
"""

from __future__ import annotations

import asyncio
import sys


def _imports():
    try:
        import httpx  # noqa: F401
    except Exception as e:  # noqa: BLE001
        print(f"SKIP (httpx unavailable): {e!r}")
        return None
    from ads_engine.connectors.base import BaseConnector, ConnectorError
    return httpx, BaseConnector, ConnectorError


class _Probe:
    """A BaseConnector subclass pinned to a known host, with a recording sleep + auth header."""
    pass


def _make_connector(httpx, BaseConnector, responses, *, base_url="https://graph.test"):
    """Build a connector whose httpx client uses a MockTransport serving `responses` in order.
    Returns (connector, sleeps_list)."""
    sleeps: list = []

    queue = list(responses)

    def _handler(request):
        if not queue:
            return httpx.Response(599, json={"_exhausted": True})
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    transport = httpx.MockTransport(_handler)
    client = httpx.AsyncClient(transport=transport)

    class _Conn(BaseConnector):
        channel = "test"

        def _auth_headers(self):
            return {"Authorization": "Bearer TESTTOKEN"}

    async def _fake_sleep(d):
        sleeps.append(d)

    conn = _Conn(base_url=base_url, http=client, sleep_fn=_fake_sleep)
    return conn, sleeps


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) \
        if False else asyncio.run(coro)


def main() -> int:
    got = _imports()
    if got is None:
        return 0
    httpx, BaseConnector, ConnectorError = got
    R = httpx.Response
    failures = []

    def check(name, cond):
        print(f"  {'PASS' if cond else 'FAIL'} — {name}")
        if not cond:
            failures.append(name)

    # 1. 200 first try.
    async def t1():
        conn, sleeps = _make_connector(httpx, BaseConnector, [R(200, json={"id": "ok"})])
        res = await conn._request("GET", "/me")
        await conn.aclose()
        return res, sleeps
    res, sleeps = _run(t1())
    check("200 -> ok, 1 attempt, 0 sleeps",
          res.ok and res.attempts == 1 and len(sleeps) == 0 and res.data == {"id": "ok"})

    # 2. 429 then 200.
    async def t2():
        conn, sleeps = _make_connector(httpx, BaseConnector, [R(429), R(200, json={"x": 1})])
        res = await conn._request("GET", "/me")
        await conn.aclose()
        return res, sleeps
    res, sleeps = _run(t2())
    check("429->200 -> ok, 2 attempts, 1 sleep",
          res.ok and res.attempts == 2 and len(sleeps) == 1)

    # 3. 503,500 then 200.
    async def t3():
        conn, sleeps = _make_connector(httpx, BaseConnector, [R(503), R(500), R(200, json={})])
        res = await conn._request("GET", "/me")
        await conn.aclose()
        return res, sleeps
    res, sleeps = _run(t3())
    check("503,500->200 -> ok, 3 attempts, 2 sleeps",
          res.ok and res.attempts == 3 and len(sleeps) == 2)

    # 4. 400 terminal.
    async def t4():
        conn, sleeps = _make_connector(httpx, BaseConnector, [R(400, json={"e": "bad"})])
        res = await conn._request("POST", "/x", json={"a": 1})
        await conn.aclose()
        return res, sleeps
    res, sleeps = _run(t4())
    check("400 -> invalid_request, 1 attempt, 0 sleeps",
          (not res.ok) and res.error == ConnectorError.INVALID_REQUEST
          and res.attempts == 1 and len(sleeps) == 0)

    # 5. 401 permission.
    async def t5():
        conn, sleeps = _make_connector(httpx, BaseConnector, [R(401)])
        res = await conn._request("GET", "/x")
        await conn.aclose()
        return res, sleeps
    res, sleeps = _run(t5())
    check("401 -> permission_denied, 1 attempt",
          (not res.ok) and res.error == ConnectorError.PERMISSION and res.attempts == 1)

    # 6. all 429 -> exhausted (max_attempts default 5).
    async def t6():
        conn, sleeps = _make_connector(httpx, BaseConnector, [R(429)] * 8)
        res = await conn._request("GET", "/x")
        await conn.aclose()
        return res, sleeps
    res, sleeps = _run(t6())
    check("all-429 -> rate_limited, 5 attempts, 4 sleeps",
          (not res.ok) and res.error == ConnectorError.RATE_LIMITED
          and res.attempts == 5 and len(sleeps) == 4)

    # 7. Retry-After honored exactly.
    async def t7():
        conn, sleeps = _make_connector(
            httpx, BaseConnector,
            [R(429, headers={"Retry-After": "7"}), R(200, json={})])
        res = await conn._request("GET", "/x")
        await conn.aclose()
        return res, sleeps
    res, sleeps = _run(t7())
    check("Retry-After honored (sleep == 7.0)",
          res.ok and len(sleeps) == 1 and abs(sleeps[0] - 7.0) < 1e-9)

    # 8. SSRF: absolute URL to a different host -> blocked, no request issued.
    async def t8():
        conn, sleeps = _make_connector(httpx, BaseConnector, [R(200)])
        res = await conn._request("GET", "https://evil.example.com/steal")
        await conn.aclose()
        return res, sleeps
    res, sleeps = _run(t8())
    check("SSRF off-host -> ssrf_blocked, 0 attempts",
          (not res.ok) and res.error == ConnectorError.SSRF_BLOCKED and res.attempts == 0)

    # 9. timeout then 200.
    async def t9():
        conn, sleeps = _make_connector(
            httpx, BaseConnector,
            [httpx.ConnectTimeout("slow"), R(200, json={"ok": True})])
        res = await conn._request("GET", "/x")
        await conn.aclose()
        return res, sleeps
    res, sleeps = _run(t9())
    check("timeout->200 -> ok after retry, 1 sleep",
          res.ok and len(sleeps) == 1)

    # 10. auth header actually injected (read it back via the echo handler).
    async def t10():
        seen = {}

        def _h(request):
            seen["auth"] = request.headers.get("authorization")
            return R(200, json={})
        transport = httpx.MockTransport(_h)
        client = httpx.AsyncClient(transport=transport)

        class _C(BaseConnector):
            channel = "test"

            def _auth_headers(self):
                return {"Authorization": "Bearer SEKRET"}

        async def _s(d):
            pass
        conn = _C(base_url="https://graph.test", http=client, sleep_fn=_s)
        await conn._request("GET", "/x")
        await conn.aclose()
        return seen
    seen = _run(t10())
    check("per-request auth header injected", seen.get("auth") == "Bearer SEKRET")

    print(f"\nconnectors.base test: {'ALL PASS' if not failures else 'FAILURES: ' + repr(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
