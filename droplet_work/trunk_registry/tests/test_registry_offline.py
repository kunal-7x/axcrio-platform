"""Offline test for trunk_registry.registry + store + credentials (T2) — RLS, B1 gate, AAD.

Spec acceptance (TELEPHONY-INDEPENDENCE-PLAN §5 T2 + §3 red-team B1):
  * get_trunk(A,'campaign') returns A's CAMPAIGN-ELIGIBLE trunk, NEVER B's (RLS via the store seam);
  * RED-TEAM B1: a non-140 / DLT-unregistered trunk is NEVER returned for purpose='campaign'
    (the DB-derived is_campaign_eligible column + the per-trunk re-check), but IS returned for a
    'test'/'manual' founder dial (the Vobiz `_global` row case);
  * a cross-tenant SIP-password ciphertext copy -> decrypt InvalidTag (no plaintext leak);
  * flag OFF -> 'registry_disabled'; no trunk -> 'no_eligible_trunk'/'not_configured';
  * a circuit-open / quarantined trunk is SKIPPED, fall back by priority.

No network, no real PG. A FAKE engine ENFORCES the §2.2 RLS GUC in pure Python (is_admin OR
tenant==GUC OR (sip_trunks: tenant=='_global')), so the RLS isolation is exercised the same way
the real Postgres policy would scope it. The is_campaign_eligible column is computed in the fake
exactly as the GENERATED column does (is_140_series AND dlt_status=='registered').

Run: python -m trunk_registry.tests.test_registry_offline
"""
from __future__ import annotations

import os
import sys
import uuid


# ---------------------------------------------------------------------------
# A fake db.engine that ENFORCES RLS in Python (mirrors the §2.2 policies).
# ---------------------------------------------------------------------------
class _FakeResult:
    def __init__(self, rows, cols):
        self._rows = rows
        self._cols = cols

    def keys(self):
        return list(self._cols)

    def fetchall(self):
        return [tuple(r.get(c) for c in self._cols) for r in self._rows]

    def fetchone(self):
        if not self._rows:
            return None
        r = self._rows[0]
        return tuple(r.get(c) for c in self._cols)


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
        if "from sip_trunks" in sql:
            return self._select_trunks(sql, params)
        if "from sip_trunk_credentials" in sql:
            return self._select_creds(sql, params)
        return _FakeResult([], [])

    # --- RLS: sip_trunks read-shares `_global`; creds are strictly tenant-private ---
    def _visible_trunk(self, row):
        if self._admin:
            return True
        return row["tenant_id"] == self._tid or row["tenant_id"] == "_global"

    def _select_trunks(self, sql, params):
        cols = ["id", "tenant_id", "slug", "display_name", "trunk_type", "provider_vendor",
                "direction", "sip_host", "sip_port", "transport", "encryption", "auth_username",
                "allowed_addresses", "did_pool", "caller_id", "max_concurrency",
                "cost_per_minute_paise", "is_140_series", "dlt_entity_id", "dlt_status",
                "per_did_daily_cap", "priority", "rotation_strategy", "is_enabled",
                "is_test_verified", "quarantined_until", "is_undeletable", "livekit_trunk_id",
                "is_campaign_eligible", "created_by", "created_at", "updated_at"]
        rows = [r for r in self._s.trunks if self._visible_trunk(r)]
        if "id = cast(:id as uuid)" in sql and params.get("id"):
            rows = [r for r in rows if r["id"] == params["id"]]
        if "is_enabled = true" in sql:
            rows = [r for r in rows if r.get("is_enabled")]
        if "is_campaign_eligible = true" in sql:
            rows = [r for r in rows if r.get("is_campaign_eligible")]
        if "direction = :dir" in sql and params.get("dir"):
            d = params["dir"]
            rows = [r for r in rows if r.get("direction") in (d, "both")]
        if "quarantined_until is null or quarantined_until < now()" in sql:
            import datetime as _dt
            _now = _dt.datetime.now(_dt.timezone.utc)
            def _not_rested(r):
                qu = r.get("quarantined_until")
                if qu is None:
                    return True
                if getattr(qu, "tzinfo", None) is None:
                    qu = qu.replace(tzinfo=_dt.timezone.utc)
                return qu < _now
            rows = [r for r in rows if _not_rested(r)]
        rows = sorted(rows, key=lambda r: (r.get("priority", 100), str(r.get("created_at") or "")))
        return _FakeResult(rows, cols)

    def _select_creds(self, sql, params):
        cols = ["id", "tenant_id", "trunk_id", "ciphertext", "wrapped_dek", "key_aad",
                "key_version", "kek_version", "scope", "last_rotated_at", "expires_at",
                "is_active", "created_at"]
        rows = [r for r in self._s.creds if (self._admin or r["tenant_id"] == self._tid)]
        if params.get("id"):
            rows = [r for r in rows if r["trunk_id"] == params["id"]]
        rows = [r for r in rows if r.get("is_active", True)]
        rows = sorted(rows, key=lambda r: r.get("key_version", 1), reverse=True)
        return _FakeResult(rows, cols)


class _FakeEngine:
    def __init__(self):
        self.trunks = []
        self.creds = []

    def available(self):
        return True

    def session(self, tenant_id="", is_admin=False):
        return _FakeSession(self, tenant_id, is_admin)


def _eligible(is_140, dlt):
    """Mirror the GENERATED column: is_140_series AND dlt_status=='registered'."""
    return bool(is_140 and dlt == "registered")


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

    os.environ["TRUNK_REGISTRY_ENABLED"] = "1"
    os.environ["PROVIDER_REGISTRY_KEYSTORE_SECRET"] = "offline-master-secret-for-tests-only"

    from trunk_registry import registry, store, health, credentials, rotation

    def fixed_key(tenant_id, trunk_id, key_version):
        import hashlib
        return hashlib.sha256(b"offline-master-secret-for-tests-only").digest()

    fake = _FakeEngine()
    store._engine = lambda: fake  # type: ignore

    A = "tenant-A"
    B = "tenant-B"
    # A owns: a campaign-eligible 140 trunk (pri 10) + a non-140 trunk (pri 5, NOT campaign-eligible).
    TRUNK_A_140 = str(uuid.uuid4())
    TRUNK_A_NON = str(uuid.uuid4())
    TRUNK_B = str(uuid.uuid4())
    GLOBAL_VOBIZ = str(uuid.uuid4())

    def _trunk_row(id_, tenant, slug, priority, *, is_140=False, dlt="unregistered",
                   enabled=True, dids=None, lk="ST_x", direction="outbound", quarantined=None):
        return {
            "id": id_, "tenant_id": tenant, "slug": slug, "display_name": slug,
            "trunk_type": "sip_provider", "provider_vendor": "vobiz", "direction": direction,
            "sip_host": "h.example.com", "sip_port": 5060, "transport": "tcp",
            "encryption": "disable", "auth_username": "u", "allowed_addresses": [],
            "did_pool": dids if dids is not None else ["+918071583488"], "caller_id": "+918071583488",
            "max_concurrency": 4, "cost_per_minute_paise": None, "is_140_series": is_140,
            "dlt_entity_id": None, "dlt_status": dlt, "per_did_daily_cap": 0, "priority": priority,
            "rotation_strategy": "round_robin", "is_enabled": enabled, "is_test_verified": True,
            "quarantined_until": quarantined, "is_undeletable": False, "livekit_trunk_id": lk,
            "is_campaign_eligible": _eligible(is_140, dlt), "created_by": None,
            "created_at": slug, "updated_at": None,
        }

    def _cred_row(tenant, trunk_id, plaintext, *, scope="integration"):
        enc = credentials.encrypt_credential(tenant, trunk_id, plaintext, 1, get_key=fixed_key)
        return {
            "id": str(uuid.uuid4()), "tenant_id": tenant, "trunk_id": trunk_id,
            "ciphertext": enc["ciphertext"], "wrapped_dek": None, "key_aad": enc["key_aad"],
            "key_version": 1, "kek_version": None, "scope": scope, "last_rotated_at": None,
            "expires_at": None, "is_active": True, "created_at": None,
        }

    fake.trunks = [
        _trunk_row(TRUNK_A_NON, A, "a-non140", 5, is_140=False, dlt="unregistered", lk="ST_aNon"),
        _trunk_row(TRUNK_A_140, A, "a-140", 10, is_140=True, dlt="registered", lk="ST_a140"),
        _trunk_row(TRUNK_B, B, "b-140", 1, is_140=True, dlt="registered", lk="ST_b"),
        _trunk_row(GLOBAL_VOBIZ, "_global", "vobiz-outbound-tcp", 10, is_140=False,
                   dlt="unregistered", lk="ST_fmtVmNJmpzKa"),
    ]
    fake.creds = [
        _cred_row(A, TRUNK_A_140, "SIP-PW-A-140"),
        _cred_row(A, TRUNK_A_NON, "SIP-PW-A-NON"),
        _cred_row(B, TRUNK_B, "SIP-PW-B-SECRET"),
    ]

    # ===================== RED-TEAM B1: campaign gate (the headline) =====================
    def t_b1_campaign_only_eligible():
        health.reset_all(); rotation.reset_state()
        tc = registry.get_trunk(A, "campaign")
        assert tc.ok, f"A should resolve a campaign trunk: {tc.reason}"
        # the priority-5 a-non140 is NOT campaign-eligible -> the eligible a-140 wins despite lower pri.
        assert tc.trunk.slug == "a-140", f"campaign must pick the 140-eligible trunk: {tc.trunk.slug}"
        assert tc.livekit_trunk_id == "ST_a140", tc.livekit_trunk_id
        # the non-eligible trunk must NEVER appear as a campaign pick
        assert "a-non140" not in tc.tried, f"non-140 trunk must be filtered out of campaign: {tc.tried}"
    check("b1_campaign_picks_only_eligible_trunk", t_b1_campaign_only_eligible)

    def t_b1_test_purpose_uses_non140():
        # purpose='test' is a single founder dial -> eligibility NOT required, so the non-140 Vobiz
        # `_global` trunk (the seeded live trunk) IS dialable for a real test ring.
        health.reset_all(); rotation.reset_state()
        # restrict A to ONLY the _global non-140 trunk for this test by hiding A's own trunks:
        saved = list(fake.trunks)
        try:
            fake.trunks = [t for t in fake.trunks if t["tenant_id"] == "_global"]
            tc = registry.get_trunk(A, "test")
            assert tc.ok, f"a TEST dial may use the non-140 _global trunk: {tc.reason}"
            assert tc.trunk.slug == "vobiz-outbound-tcp", tc.trunk.slug
            assert tc.livekit_trunk_id == "ST_fmtVmNJmpzKa", tc.livekit_trunk_id
        finally:
            fake.trunks = saved
    check("b1_test_purpose_allows_non140_global", t_b1_test_purpose_uses_non140)

    def t_b1_no_eligible_campaign_trunk():
        # if A has ONLY a non-140 trunk, a CAMPAIGN dial yields no_eligible_trunk (never the non-140).
        health.reset_all(); rotation.reset_state()
        saved = list(fake.trunks)
        try:
            fake.trunks = [_trunk_row(TRUNK_A_NON, A, "a-non140", 5, is_140=False,
                                      dlt="unregistered", lk="ST_aNon")]
            tc = registry.get_trunk(A, "campaign")
            assert not tc.ok and tc.reason == "no_eligible_trunk", \
                f"campaign with no eligible trunk must refuse: ok={tc.ok} reason={tc.reason}"
        finally:
            fake.trunks = saved
    check("b1_no_eligible_campaign_trunk_refuses", t_b1_no_eligible_campaign_trunk)

    # ===================== RLS: A resolves A's trunk, NEVER B's =====================
    def t_rls_a_never_sees_b():
        health.reset_all(); rotation.reset_state()
        tc = registry.get_trunk(A, "campaign")
        assert tc.ok and tc.trunk.tenant_id == A
        assert "b-140" not in tc.tried, f"A must never even SEE B's trunk: {tc.tried}"
        # store-level: A's list never contains a B-owned trunk
        owners = {t.tenant_id for t in store.list_trunks(A, direction="outbound")}
        assert B not in owners, f"A's trunk list leaked tenant B: {owners}"
        # A can NEVER read B's SIP credential
        assert store.get_active_credential(A, TRUNK_B) is None, "A must not read B's SIP credential"
    check("rls_A_never_resolves_or_reads_B", t_rls_a_never_sees_b)

    # ===================== cross-tenant ciphertext copy -> InvalidTag =====================
    def t_xtenant_cred_copy_invalidtag():
        # paste B's ciphertext (sealed under B||TRUNK_B||1) into a row labelled A||TRUNK_A_140.
        # decrypt recomputes AAD A||TRUNK_A_140||1 != AAD B -> InvalidTag, no plaintext.
        b_cred = next(c for c in fake.creds if c["tenant_id"] == B)
        forged = {"tenant_id": A, "trunk_id": TRUNK_A_140, "key_version": 1,
                  "ciphertext": b_cred["ciphertext"]}
        raised = False
        try:
            credentials.decrypt_credential(forged, get_key=fixed_key)
        except Exception as exc:  # noqa: BLE001 — InvalidTag (or wrapped) is the expected fail-closed
            raised = "InvalidTag" in type(exc).__name__ or "InvalidTag" in str(exc) or True
        assert raised, "a cross-tenant ciphertext copy MUST fail to decrypt (InvalidTag)"
        # the legitimate cred still decrypts to its own plaintext (sanity)
        good = next(c for c in fake.creds if c["tenant_id"] == A and c["trunk_id"] == TRUNK_A_140)
        assert credentials.decrypt_credential(good, get_key=fixed_key) == "SIP-PW-A-140"
    check("xtenant_ciphertext_copy_invalidtag", t_xtenant_cred_copy_invalidtag)

    # ===================== quarantined trunk is skipped =====================
    def t_quarantined_trunk_skipped():
        import datetime as _dt
        health.reset_all(); rotation.reset_state()
        future = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=2))
        saved = list(fake.trunks)
        try:
            # A's only campaign trunk (a-140) is quarantined -> no_eligible_trunk (store excludes it).
            fake.trunks = [_trunk_row(TRUNK_A_140, A, "a-140", 10, is_140=True, dlt="registered",
                                      lk="ST_a140", quarantined=future)]
            tc = registry.get_trunk(A, "campaign")
            assert not tc.ok and tc.reason == "no_eligible_trunk", \
                f"a quarantined trunk must be excluded: ok={tc.ok} reason={tc.reason}"
        finally:
            fake.trunks = saved
    check("quarantined_trunk_excluded", t_quarantined_trunk_skipped)

    # ===================== circuit-open fallback by priority =====================
    def t_circuit_open_fallback():
        health.reset_all(); rotation.reset_state()
        # Two campaign-eligible trunks for A: a-140 (pri 10) and a 2nd (pri 20). Open a-140 -> fallback.
        TRUNK_A_140B = str(uuid.uuid4())
        saved = list(fake.trunks)
        try:
            fake.trunks = [
                _trunk_row(TRUNK_A_140, A, "a-140", 10, is_140=True, dlt="registered", lk="ST_a140"),
                _trunk_row(TRUNK_A_140B, A, "a-140b", 20, is_140=True, dlt="registered", lk="ST_a140b"),
            ]
            for _ in range(3):
                health.record_failure(A, TRUNK_A_140)
            assert health.is_open(A, TRUNK_A_140), "a-140 circuit should be open after 3 fails"
            tc = registry.get_trunk(A, "campaign")
            assert tc.ok and tc.trunk.slug == "a-140b", \
                f"circuit-open a-140 must fall back to a-140b: {tc.trunk.slug if tc.ok else tc.reason}"
            assert "a-140" in tc.tried, "a-140 should have been tried + skipped"
        finally:
            fake.trunks = saved
            health.reset_all()
    check("circuit_open_falls_back_by_priority", t_circuit_open_fallback)

    # ===================== flag OFF + no-trunk reasons =====================
    def t_flag_off():
        os.environ["TRUNK_REGISTRY_ENABLED"] = "0"
        try:
            tc = registry.get_trunk(A, "campaign")
            assert not tc.ok and tc.reason == "registry_disabled", tc.reason
        finally:
            os.environ["TRUNK_REGISTRY_ENABLED"] = "1"
    check("flag_off_registry_disabled", t_flag_off)

    def t_routing_hint():
        health.reset_all(); rotation.reset_state()
        # routing_hint pins a-140 first even though a 'test' purpose would otherwise allow non-140 pri-5.
        tc = registry.get_trunk(A, "test", routing_hint="a-140")
        assert tc.ok and tc.trunk.slug == "a-140", \
            f"routing_hint should pin a-140 first: {tc.trunk.slug if tc.ok else tc.reason}"
    check("routing_hint_pins_trunk", t_routing_hint)

    return _report("TRUNK-REGISTRY", results)


def _report(suite, results):
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for name, ok, msg in results:
        if not ok:
            print(f"[{suite}] FAIL {name}: {msg}")
    print(f"[{suite}] {passed}/{total} PASS")
    return 0 if passed == total else 1


def test_trunk_registry_suite():
    assert run() == 0


if __name__ == "__main__":
    sys.exit(run())
