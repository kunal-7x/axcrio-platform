"""Tests for voice_ops.gcal — AAD vault round-trip + cross-tenant non-portability, the OAuth
server-side flow (mock token endpoint), and async event sync (mock HTTP). No network, no Google
SDK, no Postgres (a dict-backed vault store is injected).
"""
from __future__ import annotations

import asyncio

import pytest

from voice_ops.gcal import GCalConfig, CalendarSync, GoogleOAuth, vault
from voice_ops.gcal.vault import VaultError


# --------------------------------------------------------------------------- #
# a dict-backed fake vault store (no Postgres in CI).
# --------------------------------------------------------------------------- #
class FakeVaultStore:
    def __init__(self):
        self.rows: dict = {}

    def upsert_blob(self, org_id, blob, *, calendar_id="primary", account_email=""):
        self.rows[org_id] = {"ciphertext": blob["ciphertext"], "key_version": blob["key_version"],
                             "calendar_id": calendar_id, "account_email": account_email,
                             "status": "connected"}
        return {"status": "ok"}

    def read_blob(self, org_id):
        return dict(self.rows[org_id]) if org_id in self.rows else None

    def set_status(self, org_id, status):
        if org_id in self.rows:
            self.rows[org_id]["status"] = status
        return {"status": "ok"}


@pytest.fixture(autouse=True)
def master_secret(monkeypatch):
    monkeypatch.setenv("FAMIT_KEYSTORE_SECRET", "test-master-secret-32bytes-derive-key")
    yield


@pytest.fixture
def fake_store():
    s = FakeVaultStore()
    vault.set_store_for_tests(s)
    yield s
    vault.set_store_for_tests(None)


def _cfg(**kw):
    base = dict(enabled=True, client_id="cid.apps.googleusercontent.com", client_secret="csecret",
                redirect_uri="https://panel.famit.in/api/gcal/callback")
    base.update(kw)
    return GCalConfig(**base)


# =========================================================================== #
# vault: AES-256-GCM round trip + cross-tenant non-portability
# =========================================================================== #
def test_vault_round_trip():
    blob = vault.encrypt_token("orgA", "1//refresh-token-abc")
    pt = vault.decrypt_token("orgA", blob["ciphertext"], blob["key_version"])
    assert pt == "1//refresh-token-abc"
    assert blob["key_aad"] == "orgA|google_calendar|1"


def test_vault_cross_tenant_ciphertext_fails():
    blob = vault.encrypt_token("orgA", "1//secret-for-A")
    # paste orgA's ciphertext under orgB -> AAD mismatch -> InvalidTag (never leaks plaintext)
    with pytest.raises(Exception):
        vault.decrypt_token("orgB", blob["ciphertext"], blob["key_version"])


def test_vault_refuses_empty_and_no_tenant():
    with pytest.raises(VaultError):
        vault.encrypt_token("orgA", "")
    with pytest.raises(VaultError):
        vault.encrypt_token("", "tok")


def test_vault_no_master_secret_raises(monkeypatch):
    for env in ("FAMIT_KEYSTORE_SECRET", "PROVIDER_KEYSTORE_SECRET",
                "PROVIDER_REGISTRY_KEYSTORE_SECRET", "GCAL_VAULT_SECRET"):
        monkeypatch.delenv(env, raising=False)
    with pytest.raises(VaultError):
        vault.encrypt_token("orgA", "tok")


def test_vault_mask_never_full():
    assert vault.mask("1//0gsupersecrettoken1234") == "1//0…1234"
    assert "supersecret" not in vault.mask("1//0gsupersecrettoken1234")


def test_vault_store_persists_and_reads(fake_store):
    blob = vault.encrypt_token("orgA", "1//tok-A")
    assert vault.upsert_blob("orgA", blob, account_email="a@x.com")["status"] == "ok"
    row = vault.read_blob("orgA")
    assert row is not None and row["account_email"] == "a@x.com"
    # tenant isolation at the store layer: orgB has no row
    assert vault.read_blob("orgB") is None


# =========================================================================== #
# oauth: authorization url + state + code exchange + refresh
# =========================================================================== #
def test_authorization_url_has_offline_consent_and_state():
    oa = GoogleOAuth(_cfg())
    res = oa.authorization_url("orgA")
    assert res["status"] == "ok"
    url = res["url"]
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "scope=" in url
    assert "state=" in url


def test_authorization_url_dormant_without_client():
    oa = GoogleOAuth(GCalConfig(enabled=True, client_id="", client_secret=""))
    assert oa.authorization_url("orgA")["status"] == "not_configured"


def test_exchange_code_stores_encrypted_refresh_token(fake_store, monkeypatch):
    oa = GoogleOAuth(_cfg())
    state = oa.authorization_url("orgA")["state"]
    # mock Google's token endpoint
    monkeypatch.setattr(oa, "_post_token", lambda form: {
        "access_token": "ya29.access", "refresh_token": "1//refresh-A", "expires_in": 3600})
    res = oa.exchange_code("auth-code-123", state)
    assert res["status"] == "ok"
    assert res["org_id"] == "orgA"
    # refresh token stored ENCRYPTED (not plaintext) and bound to orgA
    row = fake_store.read_blob("orgA")
    assert row is not None
    assert b"1//refresh-A" not in row["ciphertext"]  # encrypted at rest
    assert vault.decrypt_token("orgA", row["ciphertext"], row["key_version"]) == "1//refresh-A"


def test_exchange_code_rejects_forged_state(fake_store):
    oa = GoogleOAuth(_cfg())
    assert oa.exchange_code("code", "totally-forged-state")["status"] == "error"
    assert oa.exchange_code("code", "totally-forged-state")["reason"] == "bad_state"


def test_refresh_mints_access_token(fake_store, monkeypatch):
    oa = GoogleOAuth(_cfg())
    state = oa.authorization_url("orgA")["state"]
    monkeypatch.setattr(oa, "_post_token", lambda form: {
        "access_token": "ya29.access", "refresh_token": "1//refresh-A", "expires_in": 3600})
    oa.exchange_code("code", state)
    # now refresh
    monkeypatch.setattr(oa, "_post_token", lambda form: {
        "access_token": "ya29.fresh", "expires_in": 3599})
    res = oa.refresh("orgA")
    assert res["status"] == "ok"
    assert res["access_token"] == "ya29.fresh"


def test_refresh_invalid_grant_flips_revoked(fake_store, monkeypatch):
    from voice_ops.gcal.oauth import _TokenError
    oa = GoogleOAuth(_cfg())
    state = oa.authorization_url("orgA")["state"]
    monkeypatch.setattr(oa, "_post_token", lambda form: {
        "access_token": "a", "refresh_token": "1//refresh-A", "expires_in": 3600})
    oa.exchange_code("code", state)

    def _boom(form):
        raise _TokenError("invalid_grant", invalid_grant=True)
    monkeypatch.setattr(oa, "_post_token", _boom)
    res = oa.refresh("orgA")
    assert res["status"] == "revoked"
    assert res["reason"] == "reconnect_required"
    # subsequent refresh sees the revoked row and prompts reconnect without a network call
    assert oa.refresh("orgA")["status"] == "revoked"


def test_refresh_not_connected_when_no_row(fake_store):
    oa = GoogleOAuth(_cfg())
    assert oa.refresh("orgNeverConnected")["status"] == "not_connected"


# =========================================================================== #
# sync: create / reschedule / cancel with a mock HTTP seam
# =========================================================================== #
class MockHTTP:
    def __init__(self):
        self.calls = []
        self._seq = 0

    def __call__(self, method, url, token, body):
        self.calls.append({"method": method, "url": url, "token": token, "body": body})
        if method == "POST":
            self._seq += 1
            return {"id": f"gcal_evt_{self._seq}"}
        if method == "DELETE":
            return {}
        return {"id": "gcal_evt_patched"}


def _sync_with_token(fake_store, monkeypatch, http):
    cfg = _cfg()
    oa = GoogleOAuth(cfg)
    # seed a connected token via the fake store + a stubbed refresh
    blob = vault.encrypt_token("orgA", "1//refresh-A")
    fake_store.upsert_blob("orgA", blob, calendar_id="primary")
    monkeypatch.setattr(oa, "_post_token", lambda form: {"access_token": "ya29.x", "expires_in": 3600})
    persisted = {}

    def persist(org, bk, ev_id):
        persisted[bk] = ev_id
    cal = CalendarSync(cfg, oauth=oa, persist_event_id=persist, http=http)
    return cal, persisted


def test_sync_on_booked_creates_event(fake_store, monkeypatch):
    http = MockHTTP()
    cal, persisted = _sync_with_token(fake_store, monkeypatch, http)
    booking = {"id": "bk_1", "name": "Ramesh", "phone_display": "+919876543210",
               "campaign_id": "camp7", "notes": "3BHK", "status": "booked",
               "slot_start": "2026-06-20T10:00:00+00:00", "slot_end": "2026-06-20T10:30:00+00:00"}
    res = asyncio.run(cal.on_booked("orgA", booking))
    assert res["status"] == "ok"
    assert res["event_id"] == "gcal_evt_1"
    # event body carried the founder's fields
    body = http.calls[0]["body"]
    assert "Ramesh" in body["description"]
    assert "+919876543210" in body["description"]
    assert "camp7" in body["description"]
    assert body["summary"] == "Site Visit"
    # event id persisted back onto the booking
    assert persisted["bk_1"] == "gcal_evt_1"


def test_sync_on_rescheduled_patches(fake_store, monkeypatch):
    http = MockHTTP()
    cal, _ = _sync_with_token(fake_store, monkeypatch, http)
    booking = {"id": "bk_1", "calendar_event_id": "gcal_evt_existing", "name": "Ramesh",
               "slot_start": "2026-06-21T11:00:00+00:00", "slot_end": "2026-06-21T11:30:00+00:00"}
    res = asyncio.run(cal.on_rescheduled("orgA", booking))
    assert res["status"] == "ok"
    assert http.calls[-1]["method"] == "PATCH"
    assert "gcal_evt_existing" in http.calls[-1]["url"]


def test_sync_on_cancelled_deletes(fake_store, monkeypatch):
    http = MockHTTP()
    cal, _ = _sync_with_token(fake_store, monkeypatch, http)
    booking = {"id": "bk_1", "calendar_event_id": "gcal_evt_existing"}
    res = asyncio.run(cal.on_cancelled("orgA", booking))
    assert res["status"] == "ok"
    assert http.calls[-1]["method"] == "DELETE"


def test_sync_dormant_is_noop():
    cal = CalendarSync(GCalConfig(enabled=False))  # not configured
    res = asyncio.run(cal.on_booked("orgA", {"id": "bk_1", "slot_start": "x"}))
    assert res["status"] == "not_configured"


def test_sync_revoked_token_skips_gracefully(fake_store, monkeypatch):
    from voice_ops.gcal.oauth import _TokenError
    cfg = _cfg()
    oa = GoogleOAuth(cfg)
    blob = vault.encrypt_token("orgA", "1//refresh-A")
    fake_store.upsert_blob("orgA", blob)

    def _boom(form):
        raise _TokenError("invalid_grant", invalid_grant=True)
    monkeypatch.setattr(oa, "_post_token", _boom)
    http = MockHTTP()
    cal = CalendarSync(cfg, oauth=oa, http=http)
    res = asyncio.run(cal.on_booked("orgA", {"id": "bk_1", "slot_start": "x",
                                             "slot_end": "y", "status": "booked"}))
    # no access token (revoked) -> skipped, NO calendar call, never raises
    assert res["status"] == "skipped"
    assert http.calls == []
