# CONNECT + FUND build state (BLINDSPOTS B4, B16/B17, B13-B15)

EARNER-SAFE: no agent.py/voice. All real-network calls flag-gated (ADS_CONNECT_LIVE / ADS_OAUTH_LIVE),
default DRY-RUN. New routes live in a SEPARATE sub-router `connect_routes.py` (prefix `/ads/connect`)
to avoid conflicts with parallel edits to endpoints.py.

## Units
1. [DONE] vault_adapter.write_channel_blob (merge+encrypt+upsert token into the channel's def blob)
2. [DONE] connectors/meta.get_account_funding (account_status + funding_source read; subscribe_leadgen already exists)
3. [DONE] oauth.py — Meta Login-for-Business + Google OAuth2 (authorize URL, signed state, code->token, land in vault)
4. [DONE] funding.py — vendor-own-card model: funding_status + launch_precheck(blocked_insufficient_funds) + manage deep-link
5. [DONE] connect_routes.py — build_router(/ads/connect): oauth start/callback, claim page/dataset/wa-phone, subscribe leadgen, funding status/precheck/manage
6. [DONE] mount in caller.py (additive block) + offline smoke (_smoke_connect.py)
7. [DONE] frontend _connect-lib.ts + _connect-panel.tsx + ConnectionsTab embed (Connect with Meta/Google buttons)

## Founder-gated (needs real keys/approval) -> see struct.remaining
- Meta App ID/secret + Login-for-Business config + redirect URI allowlist; Google OAuth client id/secret + verified redirect.
- ADS_OAUTH_LIVE / ADS_CONNECT_LIVE flips after a scratch-account smoke.
- ADS_OAUTH_STATE_SECRET env (HMAC state signing).
