"""Offline test for provider_registry.registry + health (W3) — resolve, RLS, fallback, breaker.

Spec acceptance (PROVIDER-FRAMEWORK-PLAN §10.6 / §10.8 / §14 W3):
  * get_provider(A,'video_gen') returns A's enabled provider, NEVER B's (RLS via the store seam);
  * a disabled / circuit-open provider FALLS BACK by priority;
  * no provider -> 'not_configured' (dormant); flag OFF -> 'registry_disabled';
  * the credential is fetched ONLY through the get_secret seam (a cross-tenant ciphertext copy ->
    decrypt InvalidTag -> that provider is SKIPPED, never returned with B's key);
  * health: 3 consecutive fails -> circuit OPEN; backoff doubles 60->120->240; a success closes it.

No network, no real PG. A FAKE engine that ENFORCES the RLS GUC in pure Python backs store.py, so
the RLS isolation is exercised the same way the real Postgres policy would scope it.
Run: python -m provider_registry.tests.test_registry_offline
"""
from __future__ import annotations

import sys
import uuid


# ---------------------------------------------------------------------------
# A fake db.engine that ENFORCES RLS in Python: session(tenant_id, is_admin) scopes every
# SELECT to (is_admin) OR (tenant_id == GUC) OR (provider_definitions: tenant_id == '_global').
# This mirrors the §5 policies exactly so the store's RLS discipline is provably exercised offline.
# ---------------------------------------------------------------------------
class _FakeResult:
    def __init__(self, rows, cols):
        self._rows = rows
        self._cols = cols

    def keys(self):
        return list(self._cols)

    def fetchall(self):
        return [tuple(r.get(c) for c in self._cols) for r in self._rows]


class _FakeSession:
    def __init__(self, store_ref, tenant_id, is_admin):
        self._s = store_ref
        self._tid = tenant_id or ""
        self._admin = bool(is_admin)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt)).lower()
        params = params or {}
        if "from provider_definitions" in sql:
            return self._select_defs(sql, params)
        if "from provider_credentials" in sql:
            return self._select_creds(sql, params)
        return _FakeResult([], [])

    # --- RLS-enforced def select ---
    def _visible_def(self, row):
        if self._admin:
            return True
        return row["tenant_id"] == self._tid or row["tenant_id"] == "_global"

    def _select_defs(self, sql, params):
        cols = ["id", "tenant_id", "slug", "display_name", "provider_type", "capabilities",
                "base_url", "auth_scheme", "auth_header_name", "auth_value_tmpl", "transform_type",
                "named_provider", "request_field_map", "response_field_map", "model_default",
                "cost_per_unit_micros", "cost_unit", "health_check_path", "health_interval_s",
                "priority", "rate_limit_rpm", "is_enabled", "is_platform_default", "created_by",
                "created_at", "updated_at"]
        rows = [r for r in self._s.defs if self._visible_def(r)]
        if "id = cast(:id as uuid)" in sql and params.get("id"):
            rows = [r for r in rows if r["id"] == params["id"]]
        if params.get("cap_json"):
            import json
            cap = json.loads(params["cap_json"])[0]
            rows = [r for r in rows if cap in (r.get("capabilities") or [])]
        if "is_enabled = true" in sql:
            rows = [r for r in rows if r.get("is_enabled")]
        rows = sorted(rows, key=lambda r: (r.get("priority", 100), not r.get("is_platform_default", False)))
        return _FakeResult(rows, cols)

    # --- RLS-enforced cred select (STRICTLY tenant-private; no _global share) ---
    def _select_creds(self, sql, params):
        cols = ["id", "tenant_id", "provider_def_id", "ciphertext", "wrapped_dek", "key_aad",
                "key_version", "kek_version", "scope", "last_rotated_at", "expires_at",
                "is_active", "created_at"]
        rows = [r for r in self._s.creds
                if (self._admin or r["tenant_id"] == self._tid)]
        if params.get("id"):
            rows = [r for r in rows if r["provider_def_id"] == params["id"]]
        rows = [r for r in rows if r.get("is_active", True)]
        rows = sorted(rows, key=lambda r: r.get("key_version", 1), reverse=True)
        return _FakeResult(rows, cols)


class _FakeEngine:
    def __init__(self):
        self.defs = []
        self.creds = []

    def available(self):
        return True

    def session(self, tenant_id="", is_admin=False):
        return _FakeSession(self, tenant_id, is_admin)


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

    import os
    os.environ["PROVIDER_REGISTRY_ENABLED"] = "1"
    os.environ["PROVIDER_REGISTRY_KEYSTORE_SECRET"] = "offline-master-secret-for-tests-only"

    from provider_registry import registry, store, health, credentials, config
    from provider_registry.schema import AuthScheme, ProviderDef, TransformType

    # A fixed test key-deriver (32 bytes) so encrypt/decrypt are deterministic offline.
    def fixed_key(tenant_id, provider_def_id, key_version):
        import hashlib
        return hashlib.sha256(b"offline-master-secret-for-tests-only").digest()

    fake = _FakeEngine()
    # Point store._engine at the fake (admin_store reuses store._engine).
    store._engine = lambda: fake  # type: ignore

    A = "tenant-A"
    B = "tenant-B"
    DEF_A = str(uuid.uuid4())
    DEF_B = str(uuid.uuid4())
    DEF_A2 = str(uuid.uuid4())   # A's second (lower-priority) video provider, for fallback

    def _def_row(id_, tenant, slug, priority, *, capability="video_gen", named="fal",
                 enabled=True, auth="bearer"):
        return {
            "id": id_, "tenant_id": tenant, "slug": slug, "display_name": slug,
            "provider_type": "hosted_api", "capabilities": [capability], "base_url": "",
            "auth_scheme": auth, "auth_header_name": None, "auth_value_tmpl": "Bearer {key}",
            "transform_type": "named_provider", "named_provider": named,
            "request_field_map": None, "response_field_map": None, "model_default": "m",
            "cost_per_unit_micros": None, "cost_unit": None, "health_check_path": None,
            "health_interval_s": 60, "priority": priority, "rate_limit_rpm": None,
            "is_enabled": enabled, "is_platform_default": False, "created_by": None,
            "created_at": None, "updated_at": None,
        }

    def _cred_row(tenant, def_id, plaintext, *, scope="integration"):
        enc = credentials.encrypt_credential(tenant, def_id, plaintext, 1, get_key=fixed_key)
        return {
            "id": str(uuid.uuid4()), "tenant_id": tenant, "provider_def_id": def_id,
            "ciphertext": enc["ciphertext"], "wrapped_dek": None, "key_aad": enc["key_aad"],
            "key_version": 1, "kek_version": None, "scope": scope, "last_rotated_at": None,
            "expires_at": None, "is_active": True, "created_at": None,
        }

    # Seed: A owns DEF_A (priority 10) + DEF_A2 (priority 50); B owns DEF_B (priority 5).
    fake.defs = [
        _def_row(DEF_A, A, "a-fal", 10),
        _def_row(DEF_A2, A, "a-replicate", 50, named="replicate"),
        _def_row(DEF_B, B, "b-fal", 5),
    ]
    fake.creds = [
        _cred_row(A, DEF_A, "KEY-A-PRIMARY"),
        _cred_row(A, DEF_A2, "KEY-A-SECONDARY"),
        _cred_row(B, DEF_B, "KEY-B-SECRET"),
    ]

    # ===================== RLS: A resolves A's provider, NEVER B's =====================
    def t_rls_a_gets_own():
        health.reset_all()
        client = registry.get_provider(A, "video_gen", get_key=fixed_key)
        assert client.ok, f"A should resolve a provider: {client.reason}"
        assert client.definition.tenant_id == A, client.definition.tenant_id
        assert client.definition.slug == "a-fal", client.definition.slug  # priority 10 wins
        assert "b-fal" not in client.tried, f"A must never even SEE B's provider: {client.tried}"
    check("rls_A_resolves_own_provider", t_rls_a_gets_own)

    def t_rls_b_gets_own():
        health.reset_all()
        client = registry.get_provider(B, "video_gen", get_key=fixed_key)
        assert client.ok and client.definition.tenant_id == B
        assert client.definition.slug == "b-fal"
        assert "a-fal" not in client.tried and "a-replicate" not in client.tried, \
            f"B must never see A's providers: {client.tried}"
    check("rls_B_resolves_own_provider", t_rls_b_gets_own)

    def t_rls_store_xtenant_zero():
        # the store itself: A's list never contains a B-owned def (the SQL-policy guarantee).
        defs_a = store.list_definitions(A, capability="video_gen")
        owners = {d.tenant_id for d in defs_a}
        assert B not in owners, f"A's definition list leaked tenant B: {owners}"
        # and A can NEVER read B's credential (strictly tenant-private).
        cred_b_via_a = store.get_active_credential(A, DEF_B)
        assert cred_b_via_a is None, "A must not be able to read B's credential row"
    check("rls_store_cross_tenant_zero", t_rls_store_xtenant_zero)

    # ===================== cross-tenant ciphertext copy -> skipped (AAD) =====================
    def t_xtenant_cred_copy_skipped():
        health.reset_all()
        # Forge: paste B's ciphertext under A's DEF_A row (a DB-level tamper). The AAD in
        # decrypt is recomputed from A||DEF_A||1, but the ciphertext was sealed under B||DEF_B||1
        # -> InvalidTag -> registry SKIPS it (never returns B's key as A's). With only the tampered
        # cred present for DEF_A, A falls back to DEF_A2.
        b_cred = next(c for c in fake.creds if c["tenant_id"] == B)
        saved = [dict(c) for c in fake.creds]
        try:
            # replace A/DEF_A cred ciphertext with B's sealed-under-B blob, keep tenant_id=A
            for c in fake.creds:
                if c["tenant_id"] == A and c["provider_def_id"] == DEF_A:
                    c["ciphertext"] = b_cred["ciphertext"]
            client = registry.get_provider(A, "video_gen", get_key=fixed_key)
            # DEF_A (priority 10) decrypt fails (InvalidTag) -> fall back to DEF_A2 (priority 50)
            assert client.ok, f"should fall back after the tampered cred: {client.reason}"
            assert client.definition.slug == "a-replicate", \
                f"tampered DEF_A must be skipped, fall back to DEF_A2: {client.definition.slug}"
        finally:
            fake.creds[:] = saved
    check("xtenant_ciphertext_copy_skipped", t_xtenant_cred_copy_skipped)

    # ===================== circuit-open fallback by priority =====================
    def t_circuit_open_fallback():
        health.reset_all()
        # open DEF_A (the priority-10 provider) with 3 failures -> A should fall back to DEF_A2.
        for _ in range(3):
            health.record_failure(A, DEF_A)
        assert health.is_open(A, DEF_A), "DEF_A circuit should be open after 3 fails"
        client = registry.get_provider(A, "video_gen", get_key=fixed_key)
        assert client.ok and client.definition.slug == "a-replicate", \
            f"circuit-open DEF_A must fall back to DEF_A2: {client.definition.slug if client.ok else client.reason}"
        assert "a-fal" in client.tried, "DEF_A should have been tried + skipped"
        health.reset_all()
    check("circuit_open_falls_back_by_priority", t_circuit_open_fallback)

    # ===================== routing_hint pins a provider first =====================
    def t_routing_hint():
        health.reset_all()
        client = registry.get_provider(A, "video_gen", routing_hint="a-replicate", get_key=fixed_key)
        assert client.ok and client.definition.slug == "a-replicate", \
            f"routing_hint should pin a-replicate first: {client.definition.slug if client.ok else client.reason}"
    check("routing_hint_pins_provider", t_routing_hint)

    # ===================== not_configured (no provider) + disabled flag =====================
    def t_not_configured():
        health.reset_all()
        client = registry.get_provider(A, "embed", get_key=fixed_key)  # no embed provider seeded
        assert not client.ok and client.reason == "not_configured", client.reason
    check("no_provider_not_configured", t_not_configured)

    def t_flag_off_disabled():
        os.environ["PROVIDER_REGISTRY_ENABLED"] = "0"
        try:
            client = registry.get_provider(A, "video_gen", get_key=fixed_key)
            assert not client.ok and client.reason == "registry_disabled", client.reason
        finally:
            os.environ["PROVIDER_REGISTRY_ENABLED"] = "1"
    check("flag_off_registry_disabled", t_flag_off_disabled)

    # ===================== HEALTH: 3-fail open + backoff 60->120->240 + close =====================
    def t_breaker_open_backoff_close():
        health.reset_all()
        clock = {"t": 1000.0}
        now = lambda: clock["t"]
        # 2 fails: not open yet
        health.record_failure(A, DEF_A, "e", now_fn=now)
        health.record_failure(A, DEF_A, "e", now_fn=now)
        assert not health.is_open(A, DEF_A, now_fn=now), "2 fails must not open"
        # 3rd fail: OPEN with base backoff 60
        st = health.record_failure(A, DEF_A, "e", now_fn=now)
        assert health.is_open(A, DEF_A, now_fn=now), "3 fails must open"
        assert st.backoff_s == 60, st.backoff_s
        assert int(st.open_until - now()) == 60
        # advance past the window -> half-open (is_open False), a trial fails -> backoff 120
        clock["t"] += 61
        assert not health.is_open(A, DEF_A, now_fn=now), "should be half-open after the window"
        st = health.record_failure(A, DEF_A, "e", now_fn=now)
        assert st.backoff_s == 120, f"backoff should double to 120: {st.backoff_s}"
        # advance + another failed trial -> 240
        clock["t"] += 121
        st = health.record_failure(A, DEF_A, "e", now_fn=now)
        assert st.backoff_s == 240, f"backoff should double to 240: {st.backoff_s}"
        # a SUCCESS closes it + resets the backoff
        st = health.record_success(A, DEF_A, now_fn=now)
        assert not health.is_open(A, DEF_A, now_fn=now) and st.fails == 0 and st.backoff_s == 60
        health.reset_all()
    check("breaker_open_backoff_close", t_breaker_open_backoff_close)

    def t_breaker_probe_orchestrator():
        health.reset_all()
        d = ProviderDef(id=DEF_A, slug="a-fal")
        # a failing prober 3x opens; a healthy prober closes.
        fail_probe = lambda _d: (False, 0, "503")
        ok_probe = lambda _d: (True, 12, "")
        for _ in range(3):
            health.run_probe(A, d, fail_probe)
        assert health.is_open(A, DEF_A)
        health.run_probe(A, d, ok_probe)  # but is_open won't half-open until window... force success
        # run_probe on success calls record_success -> closes immediately
        assert not health.is_open(A, DEF_A), "a healthy probe must close the circuit"
        health.reset_all()
    check("breaker_probe_orchestrator", t_breaker_probe_orchestrator)

    return _report("REGISTRY", results)


def _report(suite, results):
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for name, ok, msg in results:
        if not ok:
            print(f"[{suite}] FAIL {name}: {msg}")
    print(f"[{suite}] {passed}/{total} PASS")
    return 0 if passed == total else 1


def test_registry_suite():
    assert run() == 0


if __name__ == "__main__":
    sys.exit(run())
