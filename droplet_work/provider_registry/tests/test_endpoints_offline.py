"""Offline test for provider_registry.endpoints (W4) — the connector API mount surface.

No network, no real PG, no caller.py. A FAKE db.engine that ENFORCES the §5 RLS GUC in Python backs
store.py (the same harness shape as test_registry_offline), extended to support the W4 WRITES
(INSERT/UPDATE/DELETE provider_definitions, upsert provider_credentials). FastAPI handlers are
driven directly (the route endpoint coroutines) with a fake Request + the injected auth-helper
stubs, so the full request path is exercised without a server.

Acceptance (PROVIDER-FRAMEWORK-PLAN §10.7 / §10.1 / §14 W4):
  * resting byte-identical: flag OFF -> every route 404s (dormant), even when mounted.
  * the build_router pattern: tenant ALWAYS from resolve_tenant (token), never the body.
  * super-admin gate: require_super_admin returning a Response (legacy-pw / non-admin) -> the
    /providers/admin/* routes return it (the legacy-pw exclusion is enforced by caller.py's
    require_super_admin; here we prove the route HONORS a denial Response).
  * SSRF: a self_hosted base_url resolving to metadata/loopback -> 400 ssrf_blocked (admin create).
  * vendor cannot create a self_hosted endpoint -> 403.
  * field-map injection: a custom_field_map with a non-JSONPath/eval string -> 400.
  * credential create + masked list (never plaintext); reveal POLICY: an 'ai_provider' (platform)
    credential is NOT vendor-revealable -> 403; an 'integration' (own) credential IS -> 200.
  * reveal step-up: no token -> 403 step_up_required; a minted single-use token reveals once;
    REPLAY of the same token -> 403 (single-use jti, the live replay gap closed).

Run: python -m provider_registry.tests.test_endpoints_offline
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid


# ---------------------------------------------------------------------------
# Fake RLS-enforcing engine (read shape mirrors test_registry_offline; + writes for W4).
# ---------------------------------------------------------------------------
_DEF_COLS = ["id", "tenant_id", "slug", "display_name", "provider_type", "capabilities",
             "base_url", "auth_scheme", "auth_header_name", "auth_value_tmpl", "transform_type",
             "named_provider", "request_field_map", "response_field_map", "model_default",
             "cost_per_unit_micros", "cost_unit", "health_check_path", "health_interval_s",
             "priority", "rate_limit_rpm", "is_enabled", "is_platform_default", "created_by",
             "created_at", "updated_at"]
_CRED_COLS = ["id", "tenant_id", "provider_def_id", "ciphertext", "wrapped_dek", "key_aad",
              "key_version", "kek_version", "scope", "last_rotated_at", "expires_at",
              "is_active", "created_at"]


class _Res:
    def __init__(self, rows, cols):
        self._rows, self._cols = rows, cols

    def keys(self):
        return list(self._cols)

    def fetchall(self):
        return [tuple(r.get(c) for c in self._cols) for r in self._rows]

    def fetchone(self):
        if not self._rows:
            return None
        return tuple(self._rows[0].get(c) for c in self._cols)


class _Sess:
    def __init__(self, eng, tid, admin):
        self.eng, self.tid, self.admin = eng, tid or "", bool(admin)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def _vis_def(self, r):
        return self.admin or r["tenant_id"] == self.tid or r["tenant_id"] == "_global"

    def _write_check_def(self, tenant_id):
        # §5 WITH CHECK: admin GUC, OR own-tenant AND not '_global'.
        if self.admin:
            return True
        return tenant_id == self.tid and tenant_id != "_global"

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        low = sql.lower()
        params = params or {}
        if low.startswith("insert into provider_definitions"):
            tid = params.get("_tid", "")
            if not self._write_check_def(tid):
                raise PermissionError("RLS WITH CHECK blocked def insert")
            row = {c: None for c in _DEF_COLS}
            row["id"] = str(uuid.uuid4())
            row["tenant_id"] = tid
            row["created_by"] = params.get("_cby", "")
            for c in _DEF_COLS:
                if c in params:
                    row[c] = params[c]
            # jsonb params arrive as JSON text in the real path; decode for the dataclass.
            for jc in ("capabilities", "request_field_map", "response_field_map"):
                if isinstance(row.get(jc), str):
                    try:
                        row[jc] = json.loads(row[jc])
                    except Exception:  # noqa: BLE001
                        pass
            self.eng.defs.append(row)
            return _Res([row], _DEF_COLS)
        if low.startswith("update provider_definitions"):
            did = params.get("_id")
            for r in self.eng.defs:
                if r["id"] == did and self._vis_def(r):
                    for c in _DEF_COLS:
                        if c in params:
                            r[c] = params[c]
                    return _Res([r], _DEF_COLS)
            return _Res([], _DEF_COLS)
        if low.startswith("delete from provider_definitions"):
            did = params.get("_id")
            keep, deleted = [], []
            for r in self.eng.defs:
                if r["id"] == did and self._vis_def(r):
                    deleted.append(r)
                else:
                    keep.append(r)
            self.eng.defs = keep
            if deleted:
                self.eng.creds = [c for c in self.eng.creds if c["provider_def_id"] != did]
            return _Res([{"id": did}] if deleted else [], ["id"])
        if "insert into provider_credentials" in low:
            pdid = params.get("_pdid")
            for c in self.eng.creds:
                if c["provider_def_id"] == pdid and c.get("is_active"):
                    c["is_active"] = False
            row = {c: None for c in _CRED_COLS}
            row.update({"id": str(uuid.uuid4()), "tenant_id": params.get("_tid"),
                        "provider_def_id": pdid, "ciphertext": params.get("_ct"),
                        "key_aad": params.get("_aad"), "key_version": params.get("_kv", 1),
                        "scope": params.get("_scope", "integration"), "is_active": True})
            self.eng.creds.append(row)
            return _Res([row], ["id", "tenant_id", "provider_def_id", "key_version", "scope",
                                "is_active", "created_at"])
        if "insert into provider_health_log" in low:
            return _Res([], [])
        if "from provider_definitions" in low:
            rows = [r for r in self.eng.defs if self._vis_def(r)]
            if "id = cast(:id as uuid)" in low and params.get("id"):
                rows = [r for r in rows if r["id"] == params["id"]]
            if params.get("cap_json"):
                cap = json.loads(params["cap_json"])[0]
                rows = [r for r in rows if cap in (r.get("capabilities") or [])]
            if "is_enabled = true" in low:
                rows = [r for r in rows if r.get("is_enabled")]
            rows = sorted(rows, key=lambda r: (r.get("priority", 100) or 100,
                                               not r.get("is_platform_default", False)))
            return _Res(rows, _DEF_COLS)
        if "from provider_credentials" in low:
            rows = [r for r in self.eng.creds if (self.admin or r["tenant_id"] == self.tid)]
            if params.get("id"):
                rows = [r for r in rows if r["provider_def_id"] == params["id"]]
            rows = [r for r in rows if r.get("is_active", True)]
            rows = sorted(rows, key=lambda r: r.get("key_version", 1), reverse=True)
            return _Res(rows, _CRED_COLS)
        return _Res([], [])


class _Eng:
    def __init__(self):
        self.defs, self.creds = [], []

    def available(self):
        return True

    def session(self, tenant_id="", is_admin=False):
        return _Sess(self, tenant_id, is_admin)


# ---------------------------------------------------------------------------
def run() -> int:
    results = []

    def check(name, fn):
        try:
            fn()
            results.append((name, True, ""))
        except AssertionError as e:
            results.append((name, False, str(e)))
        except Exception as e:  # noqa: BLE001
            results.append((name, False, f"UNEXPECTED {type(e).__name__}: {e}"))

    os.environ["PROVIDER_REGISTRY_KEYSTORE_SECRET"] = "offline-endpoints-secret"

    import provider_registry as pr
    from provider_registry import store, config
    import firewall

    # init firewall so mint/consume reveal step-up work (uses a temp var dir).
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp())
    firewall.init(secret="offline-firewall-secret", pin_file=tmp / "pins.json")

    fake = _Eng()
    store._engine = lambda: fake  # type: ignore

    # injected auth-helper stubs (the build_router contract).
    from fastapi.responses import JSONResponse

    STATE = {"super_admin_denied": False}

    def resolve_tenant(req):
        return getattr(req, "tenant", {"tenant_id": "vendor-1", "role": "admin", "is_admin": False})

    def can(t, action):
        return True

    def need_auth():
        return JSONResponse({"error": "401"}, status_code=401)

    def forbidden(msg="x"):
        return JSONResponse({"error": msg}, status_code=403)

    def require_super_admin(req):
        if STATE["super_admin_denied"]:
            return JSONResponse({"error": "super-admin required"}, status_code=403)
        return {"tenant_id": "admin", "role": "admin", "is_admin": True}

    def audit(*a, **k):
        pass

    router = pr.build_router(resolve_tenant, can, need_auth, forbidden,
                             require_super_admin=require_super_admin, firewall=firewall, audit=audit)
    H = {(sorted(r.methods - {"HEAD"})[0], r.path): r.endpoint
         for r in router.routes if r.methods}

    class Req:
        def __init__(self, body=None, headers=None, tenant=None):
            self._b = body or {}
            self.headers = headers or {}
            if tenant is not None:
                self.tenant = tenant

        async def json(self):
            return self._b

    # the router's real prefix (derived, so the test is prefix-agnostic). Routes are registered as
    # /provider-registry/...; the test writes paths as /providers/... and we remap below.
    _PFX = "/provider-registry"

    def call(method, path, **kw):
        # normalize the test's /providers/... path onto the router's real prefix.
        if path == "/providers":
            path = _PFX
        elif path.startswith("/providers/"):
            path = _PFX + path[len("/providers"):]
        # map a concrete path to its registered template (e.g. .../{id}/reveal) for lookup.
        if (method, path) in H:
            fn = H[(method, path)]
        else:
            fn = None
            for (m, tmpl), endpoint in H.items():
                if m != method:
                    continue
                t_parts, p_parts = tmpl.strip("/").split("/"), path.strip("/").split("/")
                if len(t_parts) != len(p_parts):
                    continue
                if all(tp.startswith("{") or tp == pp for tp, pp in zip(t_parts, p_parts)):
                    fn = endpoint
                    break
            assert fn is not None, f"no route for {method} {path}"
        return asyncio.run(fn(**kw))

    def jbody(resp):
        return json.loads(bytes(resp.body).decode())

    VENDOR = {"tenant_id": "vendor-1", "role": "admin", "is_admin": False}

    # ===================== flag OFF -> dormant 404 =====================
    def t_dormant():
        os.environ.pop("PROVIDER_REGISTRY_ENABLED", None)
        r = call("GET", "/providers", request=Req(tenant=VENDOR))
        assert r.status_code == 404, f"flag-OFF list must 404, got {r.status_code}"
        r = call("POST", "/providers/admin", request=Req(body={"slug": "x"}))
        assert r.status_code == 404, f"flag-OFF admin-create must 404, got {r.status_code}"
    check("dormant_404_when_flag_off", t_dormant)

    os.environ["PROVIDER_REGISTRY_ENABLED"] = "1"

    # ===================== super-admin gate honors a denial Response (legacy-pw exclusion) =====
    def t_admin_gate_denied():
        STATE["super_admin_denied"] = True
        r = call("POST", "/providers/admin", request=Req(body={"slug": "x"}))
        assert r.status_code == 403, f"denied admin gate must 403, got {r.status_code}"
        STATE["super_admin_denied"] = False
    check("admin_gate_honors_require_super_admin_denial", t_admin_gate_denied)

    # ===================== SSRF gate on admin self_hosted create =====================
    def t_ssrf_metadata():
        body = {"slug": "evil", "display_name": "evil", "provider_type": "self_hosted",
                "base_url": "http://169.254.169.254/", "capabilities": ["text_gen"]}
        r = call("POST", "/providers/admin", request=Req(body=body))
        assert r.status_code == 400, r.status_code
        assert "ssrf_blocked" in jbody(r)["error"], jbody(r)
    check("ssrf_blocks_self_hosted_metadata", t_ssrf_metadata)

    def t_ssrf_localhost():
        body = {"slug": "ev2", "display_name": "ev2", "provider_type": "self_hosted",
                "base_url": "http://127.0.0.1:11434/", "capabilities": ["text_gen"]}
        r = call("POST", "/providers/admin", request=Req(body=body))
        assert r.status_code == 400 and "ssrf_blocked" in jbody(r)["error"], jbody(r)
    check("ssrf_blocks_self_hosted_localhost", t_ssrf_localhost)

    # ===================== vendor cannot create self_hosted =====================
    def t_vendor_no_selfhosted():
        body = {"slug": "v-self", "provider_type": "self_hosted", "base_url": "https://a.b"}
        r = call("POST", "/providers", request=Req(body=body, tenant=VENDOR))
        assert r.status_code == 403, r.status_code
    check("vendor_cannot_create_self_hosted", t_vendor_no_selfhosted)

    # ===================== field-map injection refused =====================
    def t_fieldmap_injection():
        body = {"slug": "cfm", "display_name": "cfm", "provider_type": "hosted_api",
                "transform_type": "custom_field_map", "base_url": "https://api.example.com",
                "capabilities": ["text_gen"], "request_field_map": {"$.prompt": "__import__('x')"}}
        r = call("POST", "/providers/admin", request=Req(body=body))
        assert r.status_code == 400 and "field_map" in jbody(r)["error"], jbody(r)
    check("custom_field_map_eval_refused", t_fieldmap_injection)

    # ===================== vendor create (hosted, https) + BYO key + masked list =====================
    created = {}

    def t_vendor_create_with_key():
        body = {"slug": "my-fal", "display_name": "My fal", "provider_type": "hosted_api",
                "base_url": "https://api.fal.run", "capabilities": ["video_gen"],
                "auth_scheme": "bearer", "api_key": "FAKE-TEST-FIXTURE-not-a-secret"}
        r = call("POST", "/providers", request=Req(body=body, tenant=VENDOR))
        assert r.status_code == 201, jbody(r)
        out = jbody(r)
        assert out["has_credential"] is True and out["tenant_id"] == "vendor-1", out
        created["id"] = out["id"]
        # masked list -> NEVER echoes the plaintext
        r2 = call("GET", "/providers", request=Req(tenant=VENDOR))
        provs = jbody(r2)["providers"]
        mine = [p for p in provs if p["id"] == created["id"]][0]
        assert mine["has_credential"] is True and mine["credential_scope"] == "integration", mine
        assert "FAKE-TEST-FIXTURE-not-a-secret" not in json.dumps(provs), "plaintext leaked in list!"
    check("vendor_create_hosted_with_byo_key_masked", t_vendor_create_with_key)

    def t_vendor_create_http_rejected():
        body = {"slug": "insecure", "provider_type": "hosted_api", "base_url": "http://api.x.com",
                "capabilities": ["text_gen"]}
        r = call("POST", "/providers", request=Req(body=body, tenant=VENDOR))
        assert r.status_code == 400 and "https" in jbody(r)["error"], jbody(r)
    check("vendor_hosted_must_be_https", t_vendor_create_http_rejected)

    # ===================== reveal: no step-up -> 403 step_up_required =====================
    def t_reveal_needs_stepup():
        r = call("POST", f"/providers/{created['id']}/reveal",
                 provider_id=created["id"], request=Req(tenant=VENDOR))
        assert r.status_code == 403 and jbody(r)["error"] == "step_up_required", jbody(r)
    check("reveal_requires_step_up", t_reveal_needs_stepup)

    # ===================== reveal: mint single-use token -> reveals once; REPLAY -> 403 =====================
    def t_reveal_once_then_replay_403():
        minted = firewall.mint_reveal_step_up("vendor-1", created["id"])
        assert minted and minted.get("step_up_token"), "mint failed"
        tok = minted["step_up_token"]
        # first reveal -> 200 + plaintext
        r = call("POST", f"/providers/{created['id']}/reveal", provider_id=created["id"],
                 request=Req(headers={"x-step-up": tok}, tenant=VENDOR))
        assert r.status_code == 200, jbody(r)
        assert jbody(r)["credential"] == "FAKE-TEST-FIXTURE-not-a-secret", "reveal returned wrong plaintext"
        # replay the SAME token -> 403 (single-use jti consumed)
        r2 = call("POST", f"/providers/{created['id']}/reveal", provider_id=created["id"],
                  request=Req(headers={"x-step-up": tok}, tenant=VENDOR))
        assert r2.status_code == 403 and jbody(r2)["error"] == "step_up_invalid", jbody(r2)
    check("reveal_single_use_then_replay_403", t_reveal_once_then_replay_403)

    # ===================== reveal POLICY: an 'ai_provider' (platform) cred is NOT vendor-revealable =====
    def t_platform_cred_not_revealable_by_vendor():
        # seed a platform _global def owned by vendor? No — make a vendor-owned def but stamp its
        # active credential scope='ai_provider' to prove the POLICY branch (is_revealable_by_vendor).
        from provider_registry import credentials as _cr
        did = created["id"]
        enc = _cr.encrypt_credential("vendor-1", did, "PLATFORM-KEY")
        # deactivate the integration cred, push an ai_provider one
        for c in fake.creds:
            if c["provider_def_id"] == did:
                c["is_active"] = False
        fake.creds.append({"id": str(uuid.uuid4()), "tenant_id": "vendor-1", "provider_def_id": did,
                           "ciphertext": enc["ciphertext"], "key_aad": enc["key_aad"],
                           "key_version": 2, "scope": "ai_provider", "is_active": True,
                           "wrapped_dek": None, "kek_version": None, "last_rotated_at": None,
                           "expires_at": None, "created_at": None})
        minted = firewall.mint_reveal_step_up("vendor-1", did)
        r = call("POST", f"/providers/{did}/reveal", provider_id=did,
                 request=Req(headers={"x-step-up": minted["step_up_token"]}, tenant=VENDOR))
        assert r.status_code == 403, f"platform cred must NOT be vendor-revealable, got {r.status_code}"
        assert "platform" in jbody(r)["error"].lower(), jbody(r)
    check("platform_scope_not_vendor_revealable", t_platform_cred_not_revealable_by_vendor)

    # ===================== update + delete (RLS-scoped) =====================
    def t_update_delete():
        did = created["id"]
        r = call("PUT", f"/providers/{did}", provider_id=did,
                 request=Req(body={"display_name": "Renamed fal", "priority": 7}, tenant=VENDOR))
        assert r.status_code == 200 and jbody(r)["display_name"] == "Renamed fal", jbody(r)
        r2 = call("DELETE", f"/providers/{did}", provider_id=did, request=Req(tenant=VENDOR))
        assert r2.status_code == 200 and jbody(r2)["deleted"] is True, jbody(r2)
        # gone now
        r3 = call("PUT", f"/providers/{did}", provider_id=did,
                  request=Req(body={"priority": 1}, tenant=VENDOR))
        assert r3.status_code == 404, r3.status_code
    check("update_then_delete_rls_scoped", t_update_delete)

    # ---- report ----
    passed = sum(1 for _, ok, _ in results if ok)
    failed = [(n, e) for n, ok, e in results if not ok]
    print(f"\nprovider_registry.endpoints (W4) offline: {passed}/{len(results)} PASS")
    for n, ok, e in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {n}" + (f"  -- {e}" if e else ""))
    if failed:
        print("\nFAILURES:")
        for n, e in failed:
            print(f"  {n}: {e}")
        return 1
    return 0


def test_endpoints_suite():
    assert run() == 0


if __name__ == "__main__":
    sys.exit(run())
