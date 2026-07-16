"""Offline smoke for the vault key->connector chain (BLINDSPOTS B1+B2+B15) — NO app boot, NO .env,
NO network, NO caller, NO Postgres.

Wires a FAKE provider_registry seam (store + credentials) onto ads_engine via pkg.wire(registry=...),
then proves the paste-key -> connected chain end to end with mock saved creds:

  * NOT configured before any key is saved (no def / no cred row).
  * named_provider resolution is CHANNEL-ACCURATE: meta and google both carry capability ad_platform,
    yet is_configured("meta") and is_configured("google") resolve DISTINCT defs (the B2 bug fix).
  * after a Meta key blob is "saved": is_configured(t,"meta") -> True; list_status -> meta configured;
    test_connection -> ok with the required fields present.
  * a def WITHOUT a credential row -> is_configured False (a key must actually be saved).
  * test_connection reports the SPECIFIC missing fields (secret-free: names only, never values).
  * WhatsApp messaging channel resolves + tests via its own named_provider.

Run:
  python -c "import sys; sys.path.insert(0,'droplet_work'); import ads_engine._smoke_vault as s; s.main()"
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace


# --------------------------------------------------------------------------- #
# A fake provider_registry seam: an in-memory store + credentials module. Mirrors the real
# interface vault_adapter reaches (store.available / list_definitions / get_definition_by_slug /
# get_active_credential ; credentials.decrypt_credential). Tenant-scoped by construction.
# --------------------------------------------------------------------------- #
class _FakeDef:
    def __init__(self, id, named_provider, slug, caps):
        self.id = id
        self.named_provider = named_provider
        self.slug = slug
        self.capabilities = caps


class _FakeStore:
    def __init__(self):
        # (tenant, def_id) -> def ; (tenant, def_id) -> ciphertext-row (here: the plaintext blob str)
        self._defs: dict = {}
        self._creds: dict = {}

    def available(self) -> bool:
        return True

    def add_definition(self, tenant, d: _FakeDef):
        self._defs[(tenant, d.id)] = d

    def save_credential(self, tenant, def_id, blob_str):
        self._creds[(tenant, def_id)] = {"def_id": def_id, "ciphertext": blob_str}

    # --- the read interface vault_adapter calls ---
    def list_definitions(self, tenant_id, *, capability="", enabled_only=False):
        return [d for (t, _id), d in self._defs.items() if t == tenant_id]

    def get_definition_by_slug(self, tenant_id, slug):
        for (t, _id), d in self._defs.items():
            if t == tenant_id and d.slug == slug:
                return d
        return None

    def get_active_credential(self, tenant_id, provider_def_id):
        return self._creds.get((tenant_id, provider_def_id))


class _FakeCreds:
    @staticmethod
    def decrypt_credential(row):
        # The real seam returns the decrypted plaintext blob (a JSON string for ad connectors).
        return row.get("ciphertext") if isinstance(row, dict) else None


def _wire(store: _FakeStore):
    import ads_engine as pkg
    registry = SimpleNamespace(store=store, credentials=_FakeCreds())
    pkg.wire(registry=registry)


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ok: {msg}")


def main() -> None:
    if "droplet_work" not in ",".join(sys.path):
        sys.path.insert(0, "droplet_work")

    from ads_engine import vault_adapter

    T = "tenant_vault_smoke"
    store = _FakeStore()
    _wire(store)

    # 0) registry reachable.
    _assert(vault_adapter.available() is True, "available: fake registry store is reachable")

    # 1) NOTHING configured before any def/cred exists.
    s0 = vault_adapter.list_status(T)
    _assert(s0 == {"meta": "not_configured", "google": "not_configured",
                   "whatsapp": "not_configured"},
            "dormant: all channels not_configured before any key is saved")
    _assert(vault_adapter.is_configured(T, "meta") is False, "dormant: is_configured(meta) False")
    tc0 = vault_adapter.test_connection(T, "meta")
    _assert(tc0["ok"] is False and tc0["reason"] == "not_configured",
            "dormant: test_connection(meta) -> not_configured")

    # 2) Create DISTINCT defs for meta + google (both capability ad_platform) by named_provider.
    store.add_definition(T, _FakeDef("def_meta", "meta", "my-meta", ["ad_platform"]))
    store.add_definition(T, _FakeDef("def_google", "google", "my-google", ["ad_platform"]))
    store.add_definition(T, _FakeDef("def_wa", "whatsapp", "my-wa", ["messaging"]))

    # def exists but NO credential row yet -> still not configured (a key must actually be saved).
    _assert(vault_adapter.is_configured(T, "meta") is False,
            "no-cred: def exists but no key saved -> is_configured(meta) False")
    tc_nocred = vault_adapter.test_connection(T, "meta")
    _assert(tc_nocred["reason"] == "no_credential",
            "no-cred: test_connection -> no_credential when def has no key row")

    # CHANNEL-ACCURACY (B2): meta and google resolve to DIFFERENT def ids despite same capability.
    pid_meta = vault_adapter._def_id_for(T, "meta")
    pid_google = vault_adapter._def_id_for(T, "google")
    _assert(pid_meta == "def_meta" and pid_google == "def_google",
            "B2: named_provider resolves meta/google to DISTINCT defs (not conflated by capability)")

    # 3) Save a Meta key blob (the exact fields connectors/meta.py reads).
    meta_blob = json.dumps({
        "system_user_token": "EAAG_sys_user_token_xxx",
        "app_secret": "app_secret_xxx",
        "ad_account_id": "act_1234567890",
        "page_id": "111222333",
        "dataset_id": "999888777",
        "webhook_verify_token": "verify_abc",
    })
    store.save_credential(T, "def_meta", meta_blob)

    _assert(vault_adapter.is_configured(T, "meta") is True,
            "connected: is_configured(meta) True the instant the key blob is saved")
    _assert(vault_adapter.is_configured(T, "google") is False,
            "isolation: google still not configured (its own def has no key)")

    s1 = vault_adapter.list_status(T)
    _assert(s1["meta"] == "configured" and s1["google"] == "not_configured",
            "connected: list_status reflects meta=configured, google=not_configured")

    ph = vault_adapter.provider_status_for_health(T)
    _assert(ph == {"meta": "configured", "google": "not_configured",
                   "whatsapp": "not_configured"},
            "health: provider_status_for_health carries meta/google/whatsapp")

    tc_meta = vault_adapter.test_connection(T, "meta")
    _assert(tc_meta["ok"] is True and tc_meta["reason"] == "ok",
            "test: test_connection(meta) ok with required fields present")
    _assert("system_user_token" in tc_meta["present"] and "ad_account_id" in tc_meta["present"],
            "test: required Meta fields reported present (names only)")
    # secret-free: no VALUE leaks into the result.
    _assert("EAAG_sys_user_token_xxx" not in json.dumps(tc_meta),
            "secret-free: test_connection result carries field NAMES only, never values")

    # 4) Save an INCOMPLETE Google blob -> test_connection names the missing fields.
    store.save_credential(T, "def_google", json.dumps({
        "refresh_token": "rt_xxx", "client_id": "cid_xxx"}))  # missing developer_token + client_secret
    tc_g = vault_adapter.test_connection(T, "google")
    _assert(tc_g["ok"] is False and tc_g["reason"] == "missing_fields",
            "test: incomplete Google blob -> missing_fields")
    _assert("developer_token" in tc_g["missing"] and "client_secret" in tc_g["missing"],
            "test: the specific missing Google fields are reported")
    # is_configured is still True (a cred row exists) — test_connection is the deeper readiness check.
    _assert(vault_adapter.is_configured(T, "google") is True,
            "note: is_configured True once a key row exists; test_connection gates field-completeness")

    # 5) WhatsApp (messaging) — 360dialog blob with phone_number_id + api_key.
    store.save_credential(T, "def_wa", json.dumps({
        "channel": "360dialog", "phone_number_id": "5551112222", "api_key": "d360_key_xxx",
        "waba_id": "waba_123", "app_secret": "wa_secret"}))
    _assert(vault_adapter.is_configured(T, "whatsapp") is True, "wa: is_configured(whatsapp) True")
    tc_wa = vault_adapter.test_connection(T, "whatsapp")
    _assert(tc_wa["ok"] is True, "wa: test_connection(whatsapp) ok (phone_number_id + api_key)")

    # 6) Tenant isolation — a second tenant sees nothing of tenant1's keys.
    T2 = "tenant_other"
    _assert(vault_adapter.is_configured(T2, "meta") is False,
            "isolation: a different tenant is not configured for tenant1's Meta key")

    print("\nALL ads_engine vault key->connector chain smoke assertions passed.")


if __name__ == "__main__":
    main()
