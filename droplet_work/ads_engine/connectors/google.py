"""ads_engine.connectors.google — Google Ads API v24 client over connectors/base.py.

Builds ON the shared async HTTP substrate (base.py) and the get_secret seam (vault_adapter):
design = vault-connectors.md §4; research = google-ads-api.md (2026-06-25 refresh).

WHAT THIS OWNS (the *how* of talking to Google; the *what* lives in campaign/leads/feedback):
  * OAuth2 refresh-token flow -> a short-lived access token, cached in-process (TTL from
    expires_in, 60s safety margin). Creds come ONLY from get_secret_json (client_id /
    client_secret / refresh_token / developer_token / login_customer_id / customer_id).
  * create_campaign(plan): a SINGLE atomic GoogleAdsService.Mutate (v24) building
    CampaignBudget -> Campaign -> AdGroup/AssetGroup using TEMP negative resource ids so the
    request is orphan-free. Supports SEARCH and PERFORMANCE_MAX channel types.
  * add_lead_form_asset(plan): AssetService LeadFormAsset + CampaignAsset(field_type=LEAD_FORM)
    in one mutate (structure). Retrieval is via the lead_form_submission_data report — and is
    gated behind Explorer-access read constraints (see _EXPLORER_LEAD_READ_NOTE).
  * upload_conversions(events): conversion feedback via the **Data Manager API**
    (datamanager.googleapis.com :ingestEvents) — NOT the Ads-API offline path, which is BLOCKED
    for new integrations from 2026-06-15 (we are NOT allowlisted). A call to the legacy
    UploadClickConversions surface is a HARD NO -> ConnectorError.BLOCKED_GOOGLE_LEGACY. The
    ingestEvents call is left STRUCTURED for W6 (DATA_MANAGER_API_REVISION pinned in config).

HARD invariants honored (binding, inherited from base + design §9):
  * Every method RETURNS a ConnectorResult — never raises into the tick / live spine.
  * Secrets ONLY via vault_adapter (creds.secret_json); never os.environ / .env; never logged.
  * SSRF-safe: each upstream host (googleads / oauth2 / datamanager) is reached through a
    base-pinned, host-allowlisted request — a path that escapes the pinned host is blocked.
  * OFFLINE: all calls go through the injected httpx client (a MockTransport in tests). httpx is
    imported lazily by the base; an httpx-less build still constructs the connector.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .base import BaseConnector, ConnectorError, ConnectorResult

_log = logging.getLogger("ads_engine.connectors.google")

# ---------------------------------------------------------------------------
# Pinned hosts. Single-sourced here (the API *version* is config.GOOGLE_ADS_VERSION).
# Each host is reached via its OWN base-pinned request context so the SSRF host allowlist
# stays exactly one host per request — we never widen base's allowlist.
# ---------------------------------------------------------------------------
_ADS_BASE = "https://googleads.googleapis.com"
_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"  # refresh-token -> access token
_OAUTH_HOST_BASE = "https://oauth2.googleapis.com"
_DATA_MANAGER_BASE = "https://datamanager.googleapis.com"

# OAuth scope (single scope for full Ads read/write) — research §2.
_ADWORDS_SCOPE = "https://www.googleapis.com/auth/adwords"

# Access-token cache safety margin: refresh this many seconds BEFORE the real expiry.
_TOKEN_SAFETY_MARGIN_S = 60.0

# Explorer-access lead-read constraint (research §2 access tiers): Explorer can hit production
# but is capped (2,880 ops/day) and BLOCKS planning/account-mgmt. lead_form_submission_data
# *reads* work on owned/managed accounts but the realistic launch tier is Explorer — so the
# daily-op guard (base/ads_jobs counter, design §2.1) applies and high-volume lead pulls must
# assume Basic/Standard. Surfaced, not enforced here (leads.py owns the cadence).
_EXPLORER_LEAD_READ_NOTE = (
    "lead_form_submission_data read assumes Explorer-tier op budget (2,880/day); "
    "apply for Basic/Standard for production lead volume (HUMAN_TASKS.md)."
)


class GoogleConnector(BaseConnector):
    """Google Ads API v24 client (+ Data Manager scaffold) over BaseConnector.

    The connector is pinned to the Ads host; OAuth-token and Data-Manager calls are made through
    sibling base contexts pinned to their own hosts (so each request keeps a single-host allowlist).
    """

    channel = "google"
    base_url = _ADS_BASE

    def __init__(self, creds: Any = None, *, version: str = "", http: Any = None, **kw: Any) -> None:
        # Default the version pin from config when the registry did not pass one (defensive).
        if not version:
            try:
                from .. import config
                version = getattr(config, "GOOGLE_ADS_VERSION", "v24")
            except Exception:  # noqa: BLE001
                version = "v24"
        super().__init__(creds, version=version, base_url=_ADS_BASE, http=http, **kw)
        # In-process access-token cache (NEVER persisted, repr-suppressed-by-omission).
        self._access_token: Optional[str] = None
        self._access_token_exp: float = 0.0
        # Sibling contexts for the other two hosts, sharing the SAME injected http client so a
        # mock transport in tests serves all three. Each keeps its own single-host allowlist.
        self._oauth = _SiblingContext(_OAUTH_HOST_BASE, http=self._http,
                                      sleep_fn=self._sleep, now_fn=self._now)
        self._dm = _SiblingContext(_DATA_MANAGER_BASE, http=self._http,
                                   sleep_fn=self._sleep, now_fn=self._now)

    # -- creds accessors (canonical names via vault_adapter field helpers) -----------------------
    def _blob(self) -> dict:
        sj = getattr(self.creds, "secret_json", None)
        return sj if isinstance(sj, dict) else {}

    def _cred(self, key: str) -> Optional[str]:
        """Read a canonical cred field, tolerating known aliases (e.g. oauth_refresh_token)."""
        try:
            from .. import vault_adapter
            return vault_adapter.field_aliased(self._blob(), key)
        except Exception:  # noqa: BLE001
            b = self._blob()
            v = b.get(key)
            return str(v) if v else None

    def _customer_id(self) -> Optional[str]:
        cid = self._cred("customer_id")
        return cid.replace("-", "") if cid else None

    def _login_customer_id(self) -> Optional[str]:
        lid = self._cred("login_customer_id")
        return lid.replace("-", "") if lid else None

    def _developer_token(self) -> Optional[str]:
        return self._cred("developer_token")

    # -- per-request auth headers for the ADS host (Bearer + developer-token + login-customer-id) -
    def _auth_headers(self) -> dict:
        h: dict = {}
        if self._access_token:
            h["Authorization"] = f"Bearer {self._access_token}"
        dev = self._developer_token()
        if dev:
            h["developer-token"] = dev
        login = self._login_customer_id()
        if login:
            h["login-customer-id"] = login
        return h

    # =====================================================================================
    # OAuth2 refresh-token flow — refresh_token -> access token (cached). research §2.
    # =====================================================================================
    async def refresh_token_if_needed(self) -> ConnectorResult:
        """Ensure a fresh access token is cached. Returns ok=True if a usable token is present.

        Posts client_id/client_secret/refresh_token to oauth2.googleapis.com/token (form-encoded).
        On failure returns a structured CRED_EXPIRED/PERMISSION result — NEVER raises. The token
        is cached in-process keyed to this connector instance; never logged, never persisted.
        """
        now = self._now()
        if self._access_token and now < self._access_token_exp:
            return ConnectorResult(ok=True, status=200, data={"cached": True})

        client_id = self._cred("client_id")
        client_secret = self._cred("client_secret")
        refresh_token = self._cred("refresh_token")
        if not (client_id and client_secret and refresh_token):
            return ConnectorResult.fail(
                ConnectorError.NOT_CONFIGURED,
                detail="google: missing oauth client_id/client_secret/refresh_token")

        form = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        # Form-encoded token request to the OAUTH host (its own single-host allowlist).
        res = await self._oauth._request(
            "POST", "/token", data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        if not res.ok:
            # 400/401 from the token endpoint == bad/expired refresh token -> tell vendor to re-auth.
            err = ConnectorError.CRED_EXPIRED if res.error in (
                ConnectorError.INVALID_REQUEST, ConnectorError.PERMISSION) else res.error
            return ConnectorResult.fail(err or ConnectorError.UPSTREAM, status=res.status,
                                        detail="google: token refresh failed", attempts=res.attempts)

        body = res.data if isinstance(res.data, dict) else {}
        token = body.get("access_token")
        if not token:
            return ConnectorResult.fail(ConnectorError.CRED_EXPIRED,
                                        detail="google: token response missing access_token")
        try:
            expires_in = float(body.get("expires_in", 3600))
        except Exception:  # noqa: BLE001
            expires_in = 3600.0
        self._access_token = str(token)
        self._access_token_exp = now + max(0.0, expires_in - _TOKEN_SAFETY_MARGIN_S)
        return ConnectorResult(ok=True, status=200, data={"refreshed": True})

    async def _ensure_token(self) -> Optional[ConnectorResult]:
        """Refresh if needed; return the FAILED result to short-circuit, or None on success."""
        r = await self.refresh_token_if_needed()
        return None if r.ok else r

    # =====================================================================================
    # Campaign creation — single atomic GoogleAdsService.Mutate (research §3).
    # =====================================================================================
    async def create_campaign(self, plan: dict) -> ConnectorResult:
        """Create a Search OR Performance Max campaign via ONE atomic googleAds:mutate.

        Builds CampaignBudget -> Campaign (-> AssetGroup for PMax) with TEMP negative resource ids
        so the bulk request is orphan-free. status defaults to PAUSED (never auto-spend). The
        channel type is plan["channel_type"] in {SEARCH, PERFORMANCE_MAX}. DRY-RUN/offline: the
        request body is shaped exactly as v24 expects and POSTed via the mocked transport.
        """
        tok = await self._ensure_token()
        if tok is not None:
            return tok
        cid = self._customer_id()
        if not cid:
            return ConnectorResult.fail(ConnectorError.NOT_CONFIGURED,
                                        detail="google: missing customer_id")

        channel_type = str(plan.get("channel_type", "SEARCH")).upper()
        try:
            if channel_type == "PERFORMANCE_MAX":
                operations = self._build_pmax_operations(plan)
            elif channel_type == "SEARCH":
                operations = self._build_search_operations(plan)
            else:
                return ConnectorResult.fail(
                    ConnectorError.INVALID_REQUEST,
                    detail=f"google: unsupported channel_type {channel_type!r}")
        except Exception as exc:  # noqa: BLE001 — a malformed plan must not raise into the spine
            _log.warning("google.create_campaign build failed: %r", type(exc).__name__)
            return ConnectorResult.fail(ConnectorError.INVALID_REQUEST,
                                        detail="google: campaign plan malformed")

        path = f"/{self.version}/customers/{cid}/googleAds:mutate"
        payload = {"mutateOperations": operations, "partialFailure": False}
        return await self._request("POST", path, json=payload,
                                   headers={"Content-Type": "application/json"})

    def _budget_micros(self, plan: dict) -> int:
        """Daily budget in MICROS (Google uses micros = paise*10000... we take paise/minor and x1e4
        on the rupee). plan carries daily_cap_minor (paise); micros = paise * 10_000 (1 unit=1e6
        micros, 1 rupee = 100 paise => 1 paise = 10_000 micros)."""
        try:
            minor = int(plan.get("daily_budget_minor", plan.get("daily_cap_minor", 0)))
        except Exception:  # noqa: BLE001
            minor = 0
        return max(0, minor) * 10_000

    def _bidding(self, plan: dict) -> dict:
        """Standard bidding strategy union set DIRECTLY on the campaign (research §3 Search step 3).
        Defaults to maximizeConversions; supports target_cpa / target_spend via plan['bidding']."""
        b = plan.get("bidding") or {}
        kind = str(b.get("type", "maximize_conversions")).lower()
        if kind == "target_cpa":
            tcpa = int(b.get("target_cpa_micros", 0))
            return {"targetCpa": {"targetCpaMicros": tcpa}} if tcpa else {"maximizeConversions": {}}
        if kind == "target_spend":
            return {"targetSpend": {}}
        if kind == "maximize_conversion_value":
            return {"maximizeConversionValue": {}}
        return {"maximizeConversions": {}}

    def _build_campaign_core(self, plan: dict, channel_type: str) -> list:
        """The shared budget+campaign operations (temp resource ids -1 budget, -2 campaign)."""
        budget_res = "customers/0/campaignBudgets/-1"
        campaign_res = "customers/0/campaigns/-2"
        name = str(plan.get("name", "ElevateX Campaign"))
        ops = [
            {"campaignBudgetOperation": {"create": {
                "resourceName": budget_res,
                "name": f"{name} — budget",
                "deliveryMethod": "STANDARD",
                "amountMicros": self._budget_micros(plan),
                "explicitlyShared": False,
            }}},
            {"campaignOperation": {"create": dict({
                "resourceName": campaign_res,
                "name": name,
                "status": "PAUSED",            # never auto-spend (design §9)
                "advertisingChannelType": channel_type,
                "campaignBudget": budget_res,
            }, **self._bidding(plan))}},
        ]
        return ops, campaign_res

    def _build_search_operations(self, plan: dict) -> list:
        """Search: budget -> campaign -> ad group (temp ids). research §3 Search."""
        ops, campaign_res = self._build_campaign_core(plan, "SEARCH")
        adgroup_res = "customers/0/adGroups/-3"
        ops.append({"adGroupOperation": {"create": {
            "resourceName": adgroup_res,
            "name": f"{plan.get('name', 'ElevateX')} — ad group",
            "campaign": campaign_res,
            "status": "ENABLED",
            "type": "SEARCH_STANDARD",
            "cpcBidMicros": int((plan.get("ad_group") or {}).get("cpc_bid_micros", 0)) or None,
        }}})
        return ops

    def _build_pmax_operations(self, plan: dict) -> list:
        """Performance Max: budget -> campaign(PERFORMANCE_MAX) -> AssetGroup (+signal) in ONE
        mutate (non-retail PMax requires the asset group created together). research §3 PMax."""
        ops, campaign_res = self._build_campaign_core(plan, "PERFORMANCE_MAX")
        asset_group_res = "customers/0/assetGroups/-3"
        ag = plan.get("asset_group") or {}
        final_urls = ag.get("final_urls") or plan.get("final_urls") or []
        ops.append({"assetGroupOperation": {"create": {
            "resourceName": asset_group_res,
            "name": f"{plan.get('name', 'ElevateX')} — asset group",
            "campaign": campaign_res,
            "finalUrls": list(final_urls),
            "status": "PAUSED",
        }}})
        # Optional audience/search-theme signal to steer the model (research §3 PMax).
        signal = ag.get("audience_signal") or plan.get("audience_signal")
        if signal:
            ops.append({"assetGroupSignalOperation": {"create": {
                "assetGroup": asset_group_res,
                "audience": {"audience": signal},
            }}})
        return ops

    # =====================================================================================
    # Lead Form asset — LeadFormAsset + CampaignAsset(field_type=LEAD_FORM). research §4.
    # =====================================================================================
    async def add_lead_form_asset(self, plan: dict) -> ConnectorResult:
        """Create a LeadFormAsset and link it to a campaign via CampaignAsset (field_type LEAD_FORM)
        in one atomic mutate (structure). Retrieval is via lead_form_submission_data — see
        _EXPLORER_LEAD_READ_NOTE for the Explorer-tier read constraint.
        """
        tok = await self._ensure_token()
        if tok is not None:
            return tok
        cid = self._customer_id()
        if not cid:
            return ConnectorResult.fail(ConnectorError.NOT_CONFIGURED,
                                        detail="google: missing customer_id")
        campaign_resource = plan.get("campaign_resource")
        if not campaign_resource:
            return ConnectorResult.fail(ConnectorError.INVALID_REQUEST,
                                        detail="google: add_lead_form_asset needs campaign_resource")

        try:
            asset_res = "customers/0/assets/-1"
            lead_form = {
                "businessName": str(plan.get("business_name", "ElevateX")),
                "callToActionType": str(plan.get("cta", "GET_QUOTE")),
                "callToActionDescription": str(plan.get("cta_description", "Apply now")),
                "headline": str(plan.get("headline", "Get a callback")),
                "description": str(plan.get("description", "We'll reach out shortly.")),
                "privacyPolicyUrl": str(plan.get("privacy_policy_url", "")),
                "fields": [{"inputType": f} for f in
                           (plan.get("fields") or ["FULL_NAME", "EMAIL", "PHONE_NUMBER"])],
            }
            delivery = plan.get("webhook_url")
            if delivery:
                lead_form["deliveryMethods"] = [{
                    "webhook": {
                        "advertiserWebhookUrl": str(delivery),
                        "googleKey": str(plan.get("webhook_key", "")),
                    }}]
            operations = [
                {"assetOperation": {"create": {
                    "resourceName": asset_res,
                    "name": f"{plan.get('name', 'ElevateX')} — lead form",
                    "leadFormAsset": lead_form,
                }}},
                {"campaignAssetOperation": {"create": {
                    "campaign": str(campaign_resource),
                    "asset": asset_res,
                    "fieldType": "LEAD_FORM",
                }}},
            ]
        except Exception as exc:  # noqa: BLE001
            _log.warning("google.add_lead_form_asset build failed: %r", type(exc).__name__)
            return ConnectorResult.fail(ConnectorError.INVALID_REQUEST,
                                        detail="google: lead form plan malformed")

        path = f"/{self.version}/customers/{cid}/googleAds:mutate"
        payload = {"mutateOperations": operations, "partialFailure": False}
        return await self._request("POST", path, json=payload,
                                   headers={"Content-Type": "application/json"})

    async def pull_lead_submissions(self, since_iso: str = "") -> ConnectorResult:
        """Read lead_form_submission_data via googleAds:searchStream (structure for W-leads).

        NOTE (Explorer-access read constraint): see _EXPLORER_LEAD_READ_NOTE — the realistic launch
        tier (Explorer, 2,880 ops/day) caps read volume; high-volume lead pulls assume Basic/Standard.
        """
        tok = await self._ensure_token()
        if tok is not None:
            return tok
        cid = self._customer_id()
        if not cid:
            return ConnectorResult.fail(ConnectorError.NOT_CONFIGURED,
                                        detail="google: missing customer_id")
        gaql = (
            "SELECT lead_form_submission_data.resource_name, "
            "lead_form_submission_data.lead_form_submission_fields, "
            "lead_form_submission_data.campaign, lead_form_submission_data.submission_date_time "
            "FROM lead_form_submission_data"
        )
        if since_iso:
            gaql += f" WHERE lead_form_submission_data.submission_date_time >= '{since_iso}'"
        path = f"/{self.version}/customers/{cid}/googleAds:searchStream"
        return await self._request("POST", path, json={"query": gaql},
                                   headers={"Content-Type": "application/json"})

    # =====================================================================================
    # Conversion feedback — Data Manager API (NOT the Ads-API offline path). research §5.
    # =====================================================================================
    async def upload_conversions(self, events: list, *, _legacy: bool = False) -> ConnectorResult:
        """Conversion feedback via the **Data Manager API** :ingestEvents (structured for W6).

        The Ads-API offline-conversion + EC-for-leads path is BLOCKED for new integrations from
        2026-06-15 (we are NOT allowlisted). So feedback MUST go via Data Manager. Any attempt to
        route through the legacy Ads-API UploadClickConversions surface (_legacy=True) is a HARD NO
        -> ConnectorError.BLOCKED_GOOGLE_LEGACY (surfaced, never crashed).

        The ingestEvents request body is shaped + POSTed (offline/mocked); the full destination +
        hashed-PII consent mapping is finalized in W6. DATA_MANAGER_API_REVISION is pinned in config.
        """
        if _legacy:
            return ConnectorResult.fail(
                ConnectorError.BLOCKED_GOOGLE_LEGACY,
                detail="google: Ads-API offline conversions blocked 2026-06-15; use Data Manager")

        tok = await self._ensure_token()
        if tok is not None:
            return tok

        revision = "v1"
        try:
            from .. import config
            revision = getattr(config, "DATA_MANAGER_API_REVISION", "v1")
        except Exception:  # noqa: BLE001
            revision = "v1"

        # product_account_id is the Data Manager destination (google-datamanager blob, design §1.3).
        product_account_id = self._cred("product_account_id") or self._customer_id()

        # ingestEvents body (structured for W6 — events carry SHA-256 hashed first-party data
        # within 24h of the conversion; the connector does NOT hash here, feedback.py does).
        body = {
            "destinations": [{
                "productDestinationId": product_account_id,
                "product": "GOOGLE_ADS",
            }],
            "events": list(events or []),
            "validateOnly": True,   # W6: structured/validate-only until the destination is wired
        }
        # Pinned to the Data Manager host (its own single-host allowlist).
        path = f"/{revision}:ingestEvents"
        return await self._dm._request(
            "POST", path, json=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self._access_token}"})

    # =====================================================================================
    # GAQL reporting (spend/metrics) — searchStream. research §3 / design §4.1.
    # =====================================================================================
    async def report(self, query: str) -> ConnectorResult:
        """Run a GAQL query via googleAds:searchStream (spend/metrics for analytics)."""
        tok = await self._ensure_token()
        if tok is not None:
            return tok
        cid = self._customer_id()
        if not cid:
            return ConnectorResult.fail(ConnectorError.NOT_CONFIGURED,
                                        detail="google: missing customer_id")
        path = f"/{self.version}/customers/{cid}/googleAds:searchStream"
        return await self._request("POST", path, json={"query": query},
                                   headers={"Content-Type": "application/json"})

    # =====================================================================================
    # PUBLISH + PLATFORM CAP (REDTEAM C1) — Google CampaignBudget ceiling at publish time.
    # =====================================================================================
    async def publish(self, plan: dict) -> ConnectorResult:
        """Publish a Search/PMax campaign (alias of create_campaign — campaign.py-facing name).

        The single atomic mutate creates the CampaignBudget with `amountMicros` already set from
        the plan's daily cap (see _budget_micros), so the platform-enforced spend ceiling is
        established AT PUBLISH (REDTEAM C1) in the same request — no separate poll/pause needed."""
        return await self.create_campaign(plan)

    async def set_campaign_budget_cap(self, *, budget_resource: str,
                                      daily_budget_minor: int = 0) -> ConnectorResult:
        """REDTEAM C1 — set/raise the CampaignBudget ceiling (amountMicros) so Google itself caps
        delivery. POST googleAds:mutate with a campaignBudget UPDATE (update_mask amount_micros).
        `budget_resource` is the resourceName returned at publish; daily_budget_minor is paise.
        """
        tok = await self._ensure_token()
        if tok is not None:
            return tok
        cid = self._customer_id()
        if not cid:
            return ConnectorResult.fail(ConnectorError.NOT_CONFIGURED,
                                        detail="google: missing customer_id")
        if not budget_resource:
            return ConnectorResult.fail(ConnectorError.INVALID_REQUEST,
                                        detail="google: budget_resource required to set cap")
        micros = max(0, int(daily_budget_minor or 0)) * 10_000
        if micros <= 0:
            return ConnectorResult.fail(ConnectorError.INVALID_REQUEST,
                                        detail="google: set_campaign_budget_cap needs a budget")
        operations = [{"campaignBudgetOperation": {
            "update": {"resourceName": str(budget_resource), "amountMicros": micros},
            "updateMask": "amount_micros",
        }}]
        path = f"/{self.version}/customers/{cid}/googleAds:mutate"
        payload = {"mutateOperations": operations, "partialFailure": False}
        return await self._request("POST", path, json=payload,
                                   headers={"Content-Type": "application/json"})

    # -- platform error mapping (Google REST error envelope) -------------------------------------
    def _surface(self, raw: Any) -> Optional[ConnectorError]:
        """Map a Google REST error body -> ConnectorError. Google wraps errors as
        {error:{code,status,details:[{...googleAdsFailure...}]}}. Best-effort, never raises."""
        try:
            err = (raw or {}).get("error") if isinstance(raw, dict) else None
            if not isinstance(err, dict):
                return None
            status = str(err.get("status", "")).upper()
            if status in ("RESOURCE_EXHAUSTED", "QUOTA_EXCEEDED"):
                return ConnectorError.QUOTA_EXCEEDED
            if status in ("PERMISSION_DENIED", "UNAUTHENTICATED"):
                return ConnectorError.PERMISSION
            if status in ("INVALID_ARGUMENT", "FAILED_PRECONDITION"):
                return ConnectorError.INVALID_REQUEST
        except Exception:  # noqa: BLE001
            return None
        return None


class _SiblingContext(BaseConnector):
    """A minimal BaseConnector pinned to ONE host (oauth2 / datamanager), sharing the parent's
    injected http client so a mock transport serves all hosts. Keeps each request's SSRF allowlist
    to exactly that host. Auth headers are passed per-call by the parent (not stored here)."""

    channel = "google-aux"

    def __init__(self, base_url: str, *, http: Any = None, sleep_fn: Any = None,
                 now_fn: Any = None) -> None:
        super().__init__(None, base_url=base_url, http=http, sleep_fn=sleep_fn, now_fn=now_fn)
