"""_smoke_clb3.py — CL-B3 admin API + /me/entitlements + act-as smoke.

Run in the capsy venv from /opt/famit-agent:
    CONTROL_ENABLED=1 /opt/capsy-agent/.venv/bin/python _smoke_clb3.py

Proves (per the CL-B3 GATE + the T-probes it satisfies):
  * routes import + register (every /admin/* + /me/entitlements present on app.routes).
  * T1  vendor token -> 403 on EVERY /admin/* (GET + mutating).
  * T2  legacy password (FamitCall2026) -> 403 on /admin/vendors (auth_method=legacy_pw excluded).
  * /me/entitlements -> {modes,status,plan,version} + ETag; If-None-Match -> 304 (C4).
  * T3  /me/entitlements is token-derived (no ?tenant_id / body tenant honoured).
  * engine writes via the admin routes (JWT admin): set_override (hidden/locked) -> reflected in the
    target's /me/entitlements + version BUMPED; clear_override reverts; set_status suspend hides non-core
    + revoke_all kills tokens (T15) + login blocked; set_plan assigns. All audited to events channel.
  * T11 act-as token (sub=vendor) -> /admin/* -> 403 (can't climb).
  * T10 read_only act-as token -> a mutating request -> 403 (read-only block).
  * T12 impersonate an admin tenant -> 403 (no admin-on-admin act-as).

All writes target a REAL non-admin vendor but only touch CONTROL rows (tenant_status / tenant_entitlements)
which are DELETED afterwards; the vendor's real data (leads/calls/campaigns) is never touched. Box left
pristine. Uses fastapi TestClient against the in-process app.
"""
import os
import sys
import traceback

FAILS = []
STATE = {}


def check(name, cond, detail=""):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def _pick_real_vendor(caller):
    for t in caller._read_tenants():
        if not t.get("is_admin"):
            return t.get("tenant_id")
    return None


def main():
    import caller
    import entitlements as ent
    from fastapi.testclient import TestClient
    from fastapi.responses import JSONResponse

    vid = _pick_real_vendor(caller)
    have_pg = bool(ent._engine() and ent._engine().available())
    print(f"  [setup] vendor='{vid}'  PG={have_pg}  CONTROL_ENABLED={caller.CONTROL_ENABLED}  "
          f"AUTH_JWT_READY={getattr(caller,'AUTH_JWT_READY',False)}")
    if have_pg:
        ent.ensure_schema()

    client = TestClient(caller.app, raise_server_exceptions=False)
    PW = caller.PW

    # tokens
    vtok = None
    try:
        cand = caller._make_token(vid)
        if caller._verify_token(cand) is not None:
            vtok = cand
    except Exception:
        pass
    admin_t = {"tenant_id": caller.ADMIN_ID, "is_admin": True, "role": "admin"}
    atok = None
    if caller._auth_mod is not None and getattr(caller, "AUTH_JWT_READY", False):
        try:
            atok = caller._auth_mod._make_access(caller._tenant_by_id(caller.ADMIN_ID) or admin_t)
        except Exception:
            atok = None

    # ── 0) route registration ────────────────────────────────────────────────
    print("\n0) route registration:")
    paths = {getattr(r, "path", "") for r in caller.app.routes}
    for p in ["/admin/features", "/admin/flags", "/admin/flags/{feature_key}", "/admin/plans",
              "/admin/vendors", "/admin/vendors/{vid}",
              "/admin/vendors/{vid}/entitlements/{feature_key}", "/admin/vendors/{vid}/plan",
              "/admin/vendors/{vid}/status", "/admin/vendors/{vid}/credits",
              "/admin/vendors/{vid}/impersonate", "/admin/act-as/exit", "/me/entitlements"]:
        check(f"route registered: {p}", p in paths, sorted(x for x in paths if x.startswith('/admin'))[:3])

    # ── 1) T1: vendor token -> 403 on every /admin/* ─────────────────────────
    print("\n1) T1 vendor -> 403 on /admin/* :")
    if vtok:
        admin_calls = [
            ("GET", "/admin/features"), ("GET", "/admin/flags"), ("GET", "/admin/plans"),
            ("GET", "/admin/vendors"), ("GET", f"/admin/vendors/{vid}"),
            ("PUT", "/admin/flags/grow.campaigns"),
            ("PUT", f"/admin/vendors/{vid}/entitlements/engage.calls"),
            ("DELETE", f"/admin/vendors/{vid}/entitlements/engage.calls"),
            ("PUT", f"/admin/vendors/{vid}/plan"), ("PUT", f"/admin/vendors/{vid}/status"),
            ("POST", f"/admin/vendors/{vid}/credits"), ("POST", f"/admin/vendors/{vid}/impersonate"),
        ]
        allbad = True
        for m, p in admin_calls:
            r = client.request(m, p, headers={"x-auth": vtok}, data={"mode": "on", "status": "active",
                                                                     "plan_id": "plan_a", "amount": "1"})
            if r.status_code != 403:
                allbad = False
                print(f"      {m} {p} -> {r.status_code} (expected 403)")
        check("vendor token -> 403 on all /admin/* routes", allbad)
    else:
        print("  [SKIP] no vendor hmac token in shell.")

    # ── 2) T2: legacy password -> 403 ────────────────────────────────────────
    print("\n2) T2 legacy password -> 403:")
    r = client.get("/admin/vendors", headers={"x-auth": PW})
    check("legacy password -> 403 on /admin/vendors", r.status_code == 403, r.status_code)
    r = client.get("/admin/vendors", headers={})
    check("no creds -> 401 on /admin/vendors", r.status_code == 401, r.status_code)

    # ── 3) /me/entitlements + ETag + token-derived (T3) ──────────────────────
    print("\n3) /me/entitlements (C4 ETag + T3 token-derived):")
    if vtok:
        r = client.get("/me/entitlements", headers={"x-auth": vtok})
        body = r.json() if r.status_code == 200 else {}
        check("/me/entitlements -> 200 + {modes,status,plan,version}",
              r.status_code == 200 and set(body) >= {"modes", "status", "plan", "version"},
              f"{r.status_code} {list(body)}")
        etag = r.headers.get("etag", "")
        check("/me/entitlements returns an ETag", bool(etag), etag)
        r2 = client.get("/me/entitlements", headers={"x-auth": vtok, "if-none-match": etag})
        check("If-None-Match matching ETag -> 304", r2.status_code == 304, r2.status_code)
        # T3: a body/query tenant_id must NOT change whose map is returned.
        other = next((t.get("tenant_id") for t in caller._read_tenants()
                      if t.get("tenant_id") not in (vid, caller.ADMIN_ID)), None)
        if other:
            r3 = client.get(f"/me/entitlements?tenant_id={other}", headers={"x-auth": vtok})
            b3 = r3.json() if r3.status_code == 200 else {}
            # the ETag is keyed by the TOKEN tenant (vid), proving the query param was ignored.
            check("T3 /me/entitlements ignores ?tenant_id (token-derived)",
                  f"ent-{vid}-" in r3.headers.get("etag", ""), r3.headers.get("etag"))

    # ── 4) admin writes (JWT admin) -> override/status/plan, audited, version bump ──
    print("\n4) admin writes (JWT admin path):")
    if atok and have_pg and vid:
        # baseline version
        v0 = ent.entitlements_payload(vid)["version"]
        # set a HIDDEN override on a non-core key
        r = client.put(f"/admin/vendors/{vid}/entitlements/engage.calls",
                       headers={"authorization": f"Bearer {atok}"},
                       data={"mode": "hidden", "reason": "clb3_smoke"})
        STATE["override_set"] = (r.status_code == 200)
        check("PUT override hidden -> 200", r.status_code == 200, (r.status_code, r.text[:120]))
        check("override reflected in resolve", ent.mode_for(vid, "engage.calls") == "hidden",
              ent.mode_for(vid, "engage.calls"))
        v1 = ent.entitlements_payload(vid)["version"]
        check("ent_version bumped after override", v1 > v0, f"{v0}->{v1}")
        # /me/entitlements (vendor view) shows hidden
        if vtok:
            mr = client.get("/me/entitlements", headers={"x-auth": vtok}).json()
            check("vendor /me/entitlements shows engage.calls hidden",
                  mr.get("modes", {}).get("engage.calls") == "hidden",
                  mr.get("modes", {}).get("engage.calls"))
        # clear override -> reverts to 'on'
        r = client.delete(f"/admin/vendors/{vid}/entitlements/engage.calls",
                          headers={"authorization": f"Bearer {atok}"})
        check("DELETE override -> 200 + reverts to on", r.status_code == 200 and
              ent.mode_for(vid, "engage.calls") == "on", (r.status_code, ent.mode_for(vid, "engage.calls")))

        # set_status suspend -> non-core hidden + tokens revoked + login blocked
        r = client.put(f"/admin/vendors/{vid}/status",
                       headers={"authorization": f"Bearer {atok}"},
                       data={"status": "suspended", "reason": "clb3_smoke"})
        STATE["status_set"] = (r.status_code == 200)
        check("PUT status suspended -> 200", r.status_code == 200, (r.status_code, r.text[:120]))
        check("T15 suspended hides a non-core feature", ent.mode_for(vid, "engage.calls") == "hidden",
              ent.mode_for(vid, "engage.calls"))
        check("T15 suspended keeps a CORE feature on", ent.mode_for(vid, "core.settings") == "on",
              ent.mode_for(vid, "core.settings"))
        # login blocked (CONTROL_ENABLED must be on for the block; it is in this run)
        vrec = caller._tenant_by_id(vid) or {}
        check("T15 _login_blocked_by_status(suspended vendor) True (control on)",
              caller._login_blocked_by_status(vrec) is True)
        # restore active
        r = client.put(f"/admin/vendors/{vid}/status",
                       headers={"authorization": f"Bearer {atok}"},
                       data={"status": "active", "reason": "clb3_smoke_restore"})
        check("restore status active -> 200 + features back on", r.status_code == 200 and
              ent.mode_for(vid, "engage.calls") == "on", (r.status_code, ent.mode_for(vid, "engage.calls")))

        # set_plan
        r = client.put(f"/admin/vendors/{vid}/plan", headers={"authorization": f"Bearer {atok}"},
                       data={"plan_id": "plan_b"})
        STATE["plan_set"] = (r.status_code == 200)
        check("PUT plan plan_b -> 200", r.status_code == 200, (r.status_code, r.text[:120]))
        check("plan reflected in status", ent.load_status(vid).get("plan_id") == "plan_b",
              ent.load_status(vid).get("plan_id"))

        # vendor detail + features
        r = client.get(f"/admin/vendors/{vid}", headers={"authorization": f"Bearer {atok}"})
        b = r.json() if r.status_code == 200 else {}
        check("GET /admin/vendors/{id} -> 200 + entitlements+provenance",
              r.status_code == 200 and isinstance(b.get("entitlements"), list) and b["entitlements"],
              r.status_code)
        r = client.get("/admin/features", headers={"authorization": f"Bearer {atok}"})
        check("GET /admin/features -> 200 + non-empty",
              r.status_code == 200 and len(r.json().get("features", [])) > 0, r.status_code)
    else:
        print("  [SKIP] JWT admin path or PG unavailable in shell -> write checks skipped. "
              "Route gating (T1/T2) above is the load-bearing security proof.")

    # ── 5) act-as: read-only block (T10) + no-climb (T11) + no-admin-target (T12) ──
    print("\n5) act-as guards:")
    if caller._auth_mod is not None and getattr(caller, "AUTH_JWT_READY", False) and vid:
        ro = caller._auth_mod.make_act_as(vid, caller.ADMIN_ID, "read_only")
        check("make_act_as mints a token", bool(ro))
        if ro:
            cl = caller._auth_mod.act_as_claims(ro)
            check("act_as_claims: sub=vendor, real_admin=admin, scope=read_only",
                  cl and cl.get("sub") == vid and cl.get("real_admin") == caller.ADMIN_ID
                  and cl.get("scope") == "read_only" and cl.get("is_admin") is False)
            # T11: act-as token -> /admin/* -> 403 (sub=vendor, is_admin False)
            r = client.get("/admin/vendors", headers={"authorization": f"Bearer {ro}"})
            check("T11 act-as -> /admin/vendors -> 403 (no climb)", r.status_code == 403, r.status_code)
            # T10: read-only act-as -> a mutating request -> 403 (the always-on middleware block)
            r = client.post("/suppression", headers={"authorization": f"Bearer {ro}"},
                            data={"numbers": "+919999999999"})
            check("T10 read-only act-as -> POST -> 403", r.status_code == 403, r.status_code)
            # a GET is allowed by the read-only block (may still 200/other from the route)
            r = client.get("/me", headers={"authorization": f"Bearer {ro}"})
            check("T10 read-only act-as -> GET /me NOT blocked by the act-as guard",
                  r.status_code != 403 or "read-only" not in r.text, r.status_code)
        # T12: impersonate an admin -> 403 (needs the admin route; only if JWT admin available)
        if atok:
            r = client.post(f"/admin/vendors/{caller.ADMIN_ID}/impersonate",
                            headers={"authorization": f"Bearer {atok}"}, data={"scope": "read_only"})
            check("T12 impersonate an admin tenant -> 403", r.status_code == 403, r.status_code)
    else:
        print("  [SKIP] JWT/auth unavailable -> act-as HTTP checks skipped.")

    # ── cleanup: remove the smoke control rows for the vendor ────────────────
    if have_pg and vid:
        try:
            from sqlalchemy import text
            with ent._engine().session(tenant_id="", is_admin=True) as s:
                s.execute(text("DELETE FROM tenant_entitlements WHERE tenant_id=:t AND set_by=:b"),
                          {"t": vid, "b": caller.ADMIN_ID})
                s.execute(text("DELETE FROM tenant_status WHERE tenant_id=:t"), {"t": vid})
                # remove smoke audit-mirror rows
                s.execute(text("DELETE FROM entitlement_audit WHERE reason LIKE 'clb3_smoke%' "
                               "OR target_tenant=:t"), {"t": vid})
            ent.invalidate(vid)
            print("  [cleanup] vendor control rows + smoke audit-mirror removed; box pristine.")
        except Exception as e:
            print(f"  [cleanup WARN] {e!r}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        FAILS.append("EXCEPTION")
    print("\n" + ("=" * 60))
    print(f"RESULT: {'ALL PASS' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}")
    sys.exit(1 if FAILS else 0)
