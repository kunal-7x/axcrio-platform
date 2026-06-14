"""Offline test for comm.endpoints.build_router — the /comm HTTP surface (Wave 1).

Acceptance (COMMUNICATION-MASTER-PLAN §7 + the build_router tenant-isolation pattern):
  * build_router returns an APIRouter (FastAPI present) with the expected routes + prefix /comm;
  * every route is COMM_ENABLED-gated -> dormant (flag off) returns 404 (resting byte-identical);
  * authenticated routes 401 when resolve_tenant returns None (no token);
  * the webhook route exists, is UNAUTHENTICATED, and fails closed (403) for a bad/no secret;
  * with the flag off, the webhook route ALSO 404s (resting byte-identical);
  * a write route is forbidden (403) for a read-only role.

Uses FastAPI's TestClient if available; if FastAPI is absent, the test asserts build_router is
None (the documented degrade) and passes. No network, no PG.
Run: python -m comm.tests.test_endpoints_offline
"""
from __future__ import annotations

import os
import sys

from comm.endpoints import build_router


def _fake_resolve_factory(tenant):
    def _resolve(request):
        return tenant
    return _resolve


def _can(t, action):
    role = (t or {}).get("role", "read")
    if action == "write":
        return role in ("admin", "manager")
    return True


def main() -> int:
    fails = []

    def check(name, cond):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            fails.append(name)

    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except Exception:
        r = build_router(_fake_resolve_factory(None), _can)
        check("fastapi_absent.build_router_none", r is None)
        print(f"\n{'ALL PASS' if not fails else 'FAILURES'}")
        return 0 if not fails else 1

    # ---------- flag OFF: every route 404 (resting byte-identical) ----------
    for k in ("COMM_ENABLED", "COMM_TELEGRAM_ENABLED"):
        os.environ.pop(k, None)
    app_off = FastAPI()
    admin = {"tenant_id": "admin", "is_admin": True, "role": "admin"}
    router_off = build_router(_fake_resolve_factory(admin), _can)
    check("build_router.not_none", router_off is not None)
    app_off.include_router(router_off)
    c_off = TestClient(app_off)
    check("dormant.channels_404", c_off.get("/comm/channels").status_code == 404)
    check("dormant.sessions_404", c_off.get("/comm/sessions").status_code == 404)
    check("dormant.webhook_404",
          c_off.post("/comm/webhook/telegram/admin", content=b"{}").status_code == 404)

    # ---------- flag ON ----------
    os.environ["COMM_ENABLED"] = "1"
    os.environ["COMM_TELEGRAM_ENABLED"] = "1"

    # authed app (admin token present)
    app_on = FastAPI()
    app_on.include_router(build_router(_fake_resolve_factory(admin), _can))
    c_on = TestClient(app_on)
    check("on.channels_200", c_on.get("/comm/channels").status_code == 200)
    body = c_on.get("/comm/channels").json()
    check("on.channels_shape", "channels" in body and body["channels"][0]["channel"] == "telegram")

    # unauth app (resolve_tenant -> None) -> 401 on authed routes
    app_noauth = FastAPI()
    app_noauth.include_router(build_router(_fake_resolve_factory(None), _can))
    c_noauth = TestClient(app_noauth)
    check("noauth.channels_401", c_noauth.get("/comm/channels").status_code == 401)
    check("noauth.sessions_401", c_noauth.get("/comm/sessions").status_code == 401)

    # webhook is UNAUTHENTICATED but FAILS CLOSED (no/bad secret -> 403, never 401/200)
    os.environ["COMM_WEBHOOK_SIGNING_SECRET"] = "endpoint-test-secret"
    wh = c_noauth.post("/comm/webhook/telegram/admin", content=b"{}")
    check("webhook.unauth_failclosed_403", wh.status_code == 403)

    # read-only role cannot hit a write route (set-webhook) -> 403
    reader = {"tenant_id": "admin", "is_admin": False, "role": "read"}
    app_reader = FastAPI()
    app_reader.include_router(build_router(_fake_resolve_factory(reader), _can))
    c_reader = TestClient(app_reader)
    sw = c_reader.post("/comm/channels/telegram/set-webhook", json={"webhook_url": "https://x/y"})
    check("readonly.write_forbidden_403", sw.status_code == 403)

    for k in ("COMM_ENABLED", "COMM_TELEGRAM_ENABLED", "COMM_WEBHOOK_SIGNING_SECRET"):
        os.environ.pop(k, None)

    print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
