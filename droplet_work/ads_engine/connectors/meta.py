"""ads_engine.connectors.meta — the Meta Marketing/Graph **v25.0** client.

Builds ON `connectors/base.py` (the shared async HTTP substrate) — it does NOT re-implement
retry/backoff/SSRF/timeout/structured-error; every call goes through `BaseConnector._request`,
so an error is RETURNED as a `ConnectorResult(ok=False, ...)`, never raised into the tick / the
live spine. This module is PURE platform-shape: payload builders + the v25 endpoint paths.

Design sources (binding):
  * research/meta-ads-api.md — v25.0 (released 2026-02-18); OUTCOME_LEADS for messaging-conversion
    leads; `special_ad_categories: ["HOUSING"]` + `special_ad_category_country`; 50-per-batch;
    CAPI on the unified Dataset (`/{dataset_id}/events`); leadgen webhook on Page/leadgen.
  * design/campaign.md — HOUSING is structurally enforced (age 18/65, all genders, no ZIP,
    radius >= floor, no interests/exclusions/lookalike). The targeting BUILDER lives here as a
    SAFE-WHITELIST constructor (no demographic narrowing path exists), so an illegal targeting
    object cannot be produced even from a hostile brief.
  * design/vault-connectors.md §3 — the method surface + the v25 paths + the cred blob shape.

HARD invariants honored here:
  * Auth is the System-User token, read ONLY via `vault_adapter.get_secret_json` (the cred blob is
    handed in on `creds.secret_json`; NEVER os.environ / .env). Applied per-request as a Bearer
    header by `_auth_headers()` — never stored on the instance, never logged.
  * Version is the single-sourced `config.META_API_VERSION` ("v25.0"), passed in as `version`.
    Every path is `/{version}/...`; the version is NOT hardcoded in the path strings.
  * NO ASC/AAC (Advantage+) create path — only standard ODAX outcome objectives exist here.
  * Webhook HMAC verify is FAIL-CLOSED (constant-time compare, missing-secret => False).
  * OFFLINE / DRY-RUN: all of this runs against a MOCKED httpx (the base accepts an injected
    client). With no `http` injected on an httpx-less build, `_request` returns a structured
    TRANSPORT error — it never crashes. No real keys exist yet; the offline test asserts payload
    SHAPE (incl. the HOUSING fields), not live behavior.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any, Optional

from .base import BaseConnector, ConnectorError, ConnectorResult

_log = logging.getLogger("ads_engine.connectors.meta")

# ---------------------------------------------------------------------------
# v25 ENUM CONSTANTS (single-sourced; confirmed against research/meta-ads-api.md).
# ---------------------------------------------------------------------------
META_BASE_URL = "https://graph.facebook.com"

# ODAX outcome objectives (v25). NO ASC/AAC — Advantage+ create is disabled via API on v25.
OBJECTIVE_LEADS = "OUTCOME_LEADS"
OBJECTIVE_ENGAGEMENT = "OUTCOME_ENGAGEMENT"
OBJECTIVE_SALES = "OUTCOME_SALES"
OBJECTIVE_TRAFFIC = "OUTCOME_TRAFFIC"
OBJECTIVE_AWARENESS = "OUTCOME_AWARENESS"
_VALID_OBJECTIVES = frozenset({
    OBJECTIVE_LEADS, OBJECTIVE_ENGAGEMENT, OBJECTIVE_SALES,
    OBJECTIVE_TRAFFIC, OBJECTIVE_AWARENESS,
})
# CTWA (Click-to-WhatsApp) default objective for *lead-quality* optimization. research §3:
# OUTCOME_LEADS with a Messaging conversion location is valid (downstream lead quality).
CTWA_DEFAULT_OBJECTIVE = OBJECTIVE_LEADS

# Special Ad Category enum (v25). Exact spelling confirmed: research/meta-ads-api.md:92.
SPECIAL_AD_HOUSING = "HOUSING"
SPECIAL_AD_NONE = "NONE"
_VALID_SPECIAL_AD = frozenset({
    SPECIAL_AD_HOUSING, "EMPLOYMENT", "CREDIT", "ISSUES_ELECTIONS_POLITICS",
    "FINANCIAL_PRODUCTS_SERVICES", SPECIAL_AD_NONE,
})

# HOUSING anti-discrimination locks (research §6 / design/campaign.md §4). LOCKED, not tunable here.
HOUSING_AGE_MIN = 18
HOUSING_AGE_MAX = 65          # 65 == "65+" (cannot narrow)
HOUSING_GENDERS = [1, 2]      # all genders (1=male, 2=female) — no narrowing
HOUSING_MIN_RADIUS_KM = 25    # ~15.5 mi, safely above the US 15-mi floor (config.min_radius_km mirror)
_HOUSING_DISTANCE_UNIT = "kilometer"

# CAPI user_data keys that MUST be SHA-256 hashed (research §5). fbp/fbc are sent PLAINTEXT.
_CAPI_HASH_KEYS = frozenset({
    "em", "ph", "fn", "ln", "ct", "st", "zp", "country", "external_id",
})
_CAPI_PLAINTEXT_KEYS = frozenset({"fbp", "fbc", "ctwa_clid"})


class MetaConnector(BaseConnector):
    """Meta Marketing/Graph v25.0. Constructed by `connectors.get_connector` with the resolved
    `ConnectorCreds` (secret blob on `.secret_json`) + the pinned version. NEVER reads .env.

    The cred blob shape (vault-connectors.md §1.2):
        { "system_user_token", "ad_account_id": "act_123", "page_id", "dataset_id",
          "app_secret", "business_id", ... }
    """

    channel = "meta"
    base_url = META_BASE_URL

    def __init__(self, creds: Any = None, *, version: str = "", **kw: Any) -> None:
        super().__init__(creds, version=version or "v25.0", base_url=META_BASE_URL, **kw)

    # -- cred-blob accessors (None-safe; blob lives on creds.secret_json, never .env) -----------
    def _blob(self) -> dict:
        b = getattr(self.creds, "secret_json", None)
        return b if isinstance(b, dict) else {}

    def _token(self) -> str:
        # canonical: system_user_token; tolerate access_token alias (vault_adapter._FIELD_ALIASES).
        b = self._blob()
        return str(b.get("system_user_token") or b.get("access_token") or "")

    def _ad_account(self) -> str:
        """The act_<id> ad-account id, normalized to always carry the `act_` prefix."""
        raw = str(self._blob().get("ad_account_id") or "")
        if not raw:
            return ""
        return raw if raw.startswith("act_") else f"act_{raw}"

    def _page_id(self) -> str:
        return str(self._blob().get("page_id") or "")

    def _dataset_id(self) -> str:
        return str(self._blob().get("dataset_id") or "")

    def _app_secret(self) -> str:
        return str(self._blob().get("app_secret") or "")

    # -- auth: per-request Bearer (token NEVER stored on the instance / NEVER logged) -----------
    def _auth_headers(self) -> dict:
        tok = self._token()
        return {"Authorization": f"Bearer {tok}"} if tok else {}

    def _v(self) -> str:
        """The pinned version segment for paths (config.META_API_VERSION via __init__)."""
        return self.version or "v25.0"

    # ======================================================================================
    # 1. STANDARD CAMPAIGN -> ADSET -> AD CREATE (no ASC/AAC).
    # ======================================================================================
    def build_campaign_payload(
        self,
        *,
        name: str,
        objective: str = CTWA_DEFAULT_OBJECTIVE,
        special_ad_categories: Optional[list] = None,
        special_ad_category_country: Optional[list] = None,
        status: str = "PAUSED",
        housing: bool = True,
    ) -> dict:
        """Build the Campaign create body. `special_ad_categories` is a REQUIRED v25 array.

        For property/housing (the default), force `["HOUSING"]` + `["IN"]` proactively (Meta's
        multimodal HEC auto-flagging means a real-estate creative can be flagged even without
        trigger words — research §6). `objective` is validated against the ODAX outcome set; an
        unknown/ASC value is coerced to the safe default (never emit a legacy/Advantage+ objective).
        """
        obj = objective if objective in _VALID_OBJECTIVES else CTWA_DEFAULT_OBJECTIVE
        if housing:
            cats = [SPECIAL_AD_HOUSING]
            country = list(special_ad_category_country or ["IN"])
        else:
            cats = list(special_ad_categories or [])  # REQUIRED array; [] when none (research:34)
            cats = [c for c in cats if c in _VALID_SPECIAL_AD]
            country = list(special_ad_category_country or [])
        body: dict = {
            "name": name,
            "objective": obj,
            "status": status,                       # PAUSED on create; flipped ACTIVE post-publish
            "special_ad_categories": cats,          # REQUIRED — never omit
        }
        if cats and cats != [SPECIAL_AD_NONE]:
            body["special_ad_category_country"] = country
        return body

    async def create_campaign(self, plan: dict, *, housing: bool = True) -> ConnectorResult:
        """POST /{v}/act_{ad_account_id}/campaigns. Standard campaign only (no ASC/AAC)."""
        acct = self._ad_account()
        if not acct:
            return ConnectorResult.fail(ConnectorError.NOT_CONFIGURED,
                                        detail="meta: no ad_account_id in cred blob")
        body = self.build_campaign_payload(
            name=str(plan.get("name") or "Campaign"),
            objective=str(plan.get("objective") or CTWA_DEFAULT_OBJECTIVE),
            special_ad_categories=plan.get("special_ad_categories"),
            special_ad_category_country=plan.get("special_ad_category_country"),
            status=str(plan.get("status") or "PAUSED"),
            housing=housing,
        )
        return await self._request("POST", f"/{self._v()}/{acct}/campaigns", json=body)

    def build_geo_radius_targeting(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_km: float = HOUSING_MIN_RADIUS_KM,
        country: str = "IN",
        housing: bool = True,
    ) -> dict:
        """SAFE-WHITELIST targeting builder — a geo-RADIUS around a project pin ONLY.

        For HOUSING this is the ONLY constructor: it emits a `custom_locations` radius (bumped UP
        to the legal floor, never below), forces age 18-65+ + all genders, and has NO code path
        for ZIP/postal, interests, behaviors, exclusions, or lookalikes. There is literally no
        parameter to narrow a protected class — illegal targeting is structurally impossible.
        """
        # radius floor: never below the legal minimum (research §6: >=15 mi US; 25km safe-above).
        floor = HOUSING_MIN_RADIUS_KM if housing else 1
        radius = max(float(radius_km or 0), float(floor))
        targeting: dict = {
            "geo_locations": {
                "custom_locations": [{
                    "latitude": round(float(latitude), 6),
                    "longitude": round(float(longitude), 6),
                    "radius": radius,
                    "distance_unit": _HOUSING_DISTANCE_UNIT,
                }],
                "location_types": ["home", "recent"],
            },
        }
        if housing:
            # LOCKED demographics — cannot be widened or narrowed.
            targeting["age_min"] = HOUSING_AGE_MIN
            targeting["age_max"] = HOUSING_AGE_MAX
            targeting["genders"] = list(HOUSING_GENDERS)
        # Note: NO flexible_spec / interests / behaviors / exclusions / zips / lookalike keys —
        # they are intentionally absent (the whitelist), not stripped after the fact.
        return targeting

    def build_adset_payload(
        self,
        *,
        campaign_id: str,
        targeting: dict,
        daily_budget_minor: int = 0,
        lifetime_budget_minor: int = 0,
        optimization_goal: str = "LEAD_GENERATION",
        billing_event: str = "IMPRESSIONS",
        bid_strategy: str = "LOWEST_COST_WITHOUT_CAP",
        destination_type: str = "ON_AD",
        promoted_object: Optional[dict] = None,
        status: str = "PAUSED",
        ctwa: bool = False,
    ) -> dict:
        """Build the ONE consolidated AdSet body (budget consolidation: one ad set per campaign).

        `targeting` MUST come from `build_geo_radius_targeting` (campaign.py guarantees this) — this
        method posts it verbatim; it does NOT re-derive or relax it. CTWA path sets
        destination_type=WHATSAPP (research §3).
        """
        body: dict = {
            "campaign_id": str(campaign_id),
            "optimization_goal": optimization_goal,
            "billing_event": billing_event,
            "bid_strategy": bid_strategy,
            "targeting": targeting,
            "status": status,
        }
        if ctwa:
            body["destination_type"] = "WHATSAPP"
        else:
            body["destination_type"] = destination_type
        # Meta budgets are MINOR units of the account currency (paise) — pass straight through.
        if daily_budget_minor:
            body["daily_budget"] = int(daily_budget_minor)
        if lifetime_budget_minor:
            body["lifetime_budget"] = int(lifetime_budget_minor)
        if promoted_object:
            body["promoted_object"] = promoted_object
        return body

    async def create_adset(self, plan: dict, campaign_id: str) -> ConnectorResult:
        """POST /{v}/act_{id}/adsets. Targeting taken from the plan (built by campaign.py)."""
        acct = self._ad_account()
        if not acct:
            return ConnectorResult.fail(ConnectorError.NOT_CONFIGURED,
                                        detail="meta: no ad_account_id in cred blob")
        targeting = plan.get("targeting")
        if not isinstance(targeting, dict):
            # safety: if the plan didn't carry targeting, refuse rather than post an open audience.
            return ConnectorResult.fail(ConnectorError.INVALID_REQUEST,
                                        detail="meta: adset requires targeting block")
        ctwa = str(plan.get("destination_type") or "").upper() == "WHATSAPP"
        body = self.build_adset_payload(
            campaign_id=campaign_id,
            targeting=targeting,
            daily_budget_minor=int(plan.get("budget_daily_minor") or 0),
            lifetime_budget_minor=int(plan.get("lifetime_budget_minor") or 0),
            optimization_goal=str(plan.get("optimization_goal") or "LEAD_GENERATION"),
            billing_event=str(plan.get("billing_event") or "IMPRESSIONS"),
            bid_strategy=str(plan.get("bid_strategy") or "LOWEST_COST_WITHOUT_CAP"),
            destination_type=str(plan.get("destination_type") or "ON_AD"),
            promoted_object=plan.get("promoted_object"),
            status=str(plan.get("status") or "PAUSED"),
            ctwa=ctwa,
        )
        return await self._request("POST", f"/{self._v()}/{acct}/adsets", json=body)

    def build_adcreative_payload(self, variant: dict, *, ctwa: bool = False,
                                 page_id: str = "") -> dict:
        """Build an AdCreative body from a creative variant. CTWA sets the WHATSAPP_MESSAGE CTA."""
        pid = page_id or self._page_id()
        link_data: dict = {
            "message": str(variant.get("primary_text") or ""),
            "name": str(variant.get("headline") or ""),
            "description": str(variant.get("description") or ""),
        }
        if ctwa:
            link_data["call_to_action"] = {
                "type": "WHATSAPP_MESSAGE",
                "value": {"app_destination": "WHATSAPP"},
            }
            wm = variant.get("page_welcome_message")
            if wm:
                link_data["page_welcome_message"] = wm
        body: dict = {
            "name": str(variant.get("headline") or "Creative"),
            "object_story_spec": {
                "page_id": pid,
                "link_data": link_data,
            },
        }
        return body

    async def create_adcreative(self, variant: dict, *, ctwa: bool = False) -> ConnectorResult:
        """POST /{v}/act_{id}/adcreatives."""
        acct = self._ad_account()
        if not acct:
            return ConnectorResult.fail(ConnectorError.NOT_CONFIGURED,
                                        detail="meta: no ad_account_id in cred blob")
        body = self.build_adcreative_payload(variant, ctwa=ctwa)
        return await self._request("POST", f"/{self._v()}/{acct}/adcreatives", json=body)

    async def create_ad(self, *, adset_id: str, creative_id: str, name: str,
                        status: str = "PAUSED") -> ConnectorResult:
        """POST /{v}/act_{id}/ads — bind a creative to the ad set as an Ad."""
        acct = self._ad_account()
        if not acct:
            return ConnectorResult.fail(ConnectorError.NOT_CONFIGURED,
                                        detail="meta: no ad_account_id in cred blob")
        body = {
            "name": name,
            "adset_id": str(adset_id),
            "creative": {"creative_id": str(creative_id)},
            "status": status,
        }
        return await self._request("POST", f"/{self._v()}/{acct}/ads", json=body)

    # ======================================================================================
    # 2. BATCH ENDPOINT (<=50 sub-requests) — campaign+adset+adcreative+ad atomically-ish.
    # ======================================================================================
    def build_batch_op(self, method: str, relative_url: str, *, body: Optional[dict] = None,
                       name: str = "", depends_on: str = "") -> dict:
        """Build ONE Graph batch sub-request. `body` is form-encoded (Graph batch convention).

        `name` lets a later op reference this op's response via JSONPath
        (e.g. relative_url="act_X/adsets" with body referencing "{result=create_campaign:$.id}").
        """
        op: dict = {"method": method.upper(), "relative_url": relative_url}
        if body is not None:
            # Graph batch sub-request bodies are URL-encoded key=value& strings.
            parts = []
            for k, v in body.items():
                val = v if isinstance(v, str) else json.dumps(v, separators=(",", ":"))
                parts.append(f"{k}={val}")
            op["body"] = "&".join(parts)
        if name:
            op["name"] = name
        if depends_on:
            op["depends_on"] = depends_on
        return op

    async def batch(self, ops: list) -> ConnectorResult:
        """POST https://graph.facebook.com with batch=[...]. <=50 sub-requests (research §8)."""
        if not isinstance(ops, list) or not ops:
            return ConnectorResult.fail(ConnectorError.INVALID_REQUEST,
                                        detail="meta: empty batch")
        if len(ops) > 50:
            return ConnectorResult.fail(ConnectorError.INVALID_REQUEST,
                                        detail="meta: batch exceeds 50 sub-requests")
        tok = self._token()
        # batch goes to the version-less root; access_token + batch are form fields.
        data = {"access_token": tok, "batch": json.dumps(ops, separators=(",", ":"))}
        return await self._request("POST", "/", data=data)

    def build_publish_batch(self, plan: dict, creatives: list, *,
                            housing: bool = True) -> list:
        """Assemble the campaign->adset->adcreative->ad publish as ONE dependency-chained batch.

        Campaign (PAUSED) -> the ONE ad set -> N adcreatives -> N ads, each later op referencing the
        prior response id via JSONPath. campaign.py calls this; meta.py posts it verbatim.
        """
        acct = self._ad_account()
        camp_body = self.build_campaign_payload(
            name=str(plan.get("name") or "Campaign"),
            objective=str(plan.get("objective") or CTWA_DEFAULT_OBJECTIVE),
            special_ad_category_country=plan.get("special_ad_category_country"),
            status="PAUSED",
            housing=housing,
        )
        ctwa = str(plan.get("destination_type") or "").upper() == "WHATSAPP"
        adset_body = self.build_adset_payload(
            campaign_id="{result=create_campaign:$.id}",
            targeting=plan.get("targeting") or {},
            daily_budget_minor=int(plan.get("budget_daily_minor") or 0),
            lifetime_budget_minor=int(plan.get("lifetime_budget_minor") or 0),
            optimization_goal=str(plan.get("optimization_goal") or "LEAD_GENERATION"),
            billing_event=str(plan.get("billing_event") or "IMPRESSIONS"),
            bid_strategy=str(plan.get("bid_strategy") or "LOWEST_COST_WITHOUT_CAP"),
            destination_type=str(plan.get("destination_type") or "ON_AD"),
            promoted_object=plan.get("promoted_object"),
            status="PAUSED",
            ctwa=ctwa,
        )
        ops = [
            self.build_batch_op("POST", f"{acct}/campaigns", body=camp_body,
                                name="create_campaign"),
            self.build_batch_op("POST", f"{acct}/adsets", body=adset_body,
                                name="create_adset", depends_on="create_campaign"),
        ]
        for i, variant in enumerate(creatives or []):
            cr_name = f"create_creative_{i}"
            cr_body = self.build_adcreative_payload(variant, ctwa=ctwa)
            ops.append(self.build_batch_op("POST", f"{acct}/adcreatives", body=cr_body,
                                           name=cr_name))
            ad_body = {
                "name": str(variant.get("headline") or f"Ad {i}"),
                "adset_id": "{result=create_adset:$.id}",
                "creative": {"creative_id": "{result=" + cr_name + ":$.id}"},
                "status": "PAUSED",
            }
            ops.append(self.build_batch_op("POST", f"{acct}/ads", body=ad_body,
                                           name=f"create_ad_{i}",
                                           depends_on=f"{cr_name},create_adset"))
        return ops

    async def publish(self, plan: dict, creatives: list, *,
                      housing: bool = True) -> ConnectorResult:
        """PUBLISH the full campaign->adset->adcreative->ad chain as ONE Graph batch.

        campaign.py builds the HOUSING-safe `plan` (targeting + special_ad_categories already set)
        and the consolidated single-ad-set budget; this method assembles the dependency-chained
        batch and POSTs it. Returns the raw batch result; campaign.py parses the per-op ids.
        Every object is created PAUSED — campaign.py flips ACTIVE only after all ops succeed.
        """
        ops = self.build_publish_batch(plan, creatives or [], housing=housing)
        return await self.batch(ops)

    async def set_status(self, *, object_id: str, status: str) -> ConnectorResult:
        """POST /{v}/{object_id} status=ACTIVE|PAUSED — flip a campaign/adset/ad node.

        Used to flip the campaign ACTIVE after a clean publish, and to PAUSE on partial failure /
        on a guardrails breaker trip. `object_id` is a Meta node id (campaign/adset/ad)."""
        if not object_id:
            return ConnectorResult.fail(ConnectorError.INVALID_REQUEST,
                                        detail="meta: object_id required for status flip")
        st = str(status or "").upper()
        if st not in ("ACTIVE", "PAUSED"):
            return ConnectorResult.fail(ConnectorError.INVALID_REQUEST,
                                        detail=f"meta: invalid status {status!r}")
        return await self._request("POST", f"/{self._v()}/{object_id}",
                                   data={"status": st})

    async def set_caps(self, *, adset_id: str, daily_budget_minor: int = 0,
                       lifetime_budget_minor: int = 0) -> ConnectorResult:
        """REDTEAM C1 — PLATFORM-ENFORCED CAP AT PUBLISH. POST /{v}/{adset_id} with
        daily_budget + lifetime_budget (paise) so Meta itself stops delivery at the cap,
        independent of our poll-and-pause sweep. campaign.py calls this at publish time with
        the plan's daily/lifetime caps. At least one of the two budgets must be > 0.
        """
        if not adset_id:
            return ConnectorResult.fail(ConnectorError.INVALID_REQUEST,
                                        detail="meta: adset_id required to set caps")
        body: dict = {}
        if daily_budget_minor and int(daily_budget_minor) > 0:
            body["daily_budget"] = int(daily_budget_minor)
        if lifetime_budget_minor and int(lifetime_budget_minor) > 0:
            body["lifetime_budget"] = int(lifetime_budget_minor)
        if not body:
            return ConnectorResult.fail(ConnectorError.INVALID_REQUEST,
                                        detail="meta: set_caps needs a daily or lifetime budget")
        return await self._request("POST", f"/{self._v()}/{adset_id}", data=body)

    # ======================================================================================
    # 3. LEADGEN WEBHOOK — subscribe + HMAC verify (fail-closed) + parse + retrieve.
    # ======================================================================================
    async def subscribe_leadgen(self, page_id: str = "") -> ConnectorResult:
        """POST /{v}/{page_id}/subscribed_apps?subscribed_fields=leadgen (one-time per Page)."""
        pid = page_id or self._page_id()
        if not pid:
            return ConnectorResult.fail(ConnectorError.NOT_CONFIGURED,
                                        detail="meta: no page_id for leadgen subscribe")
        return await self._request(
            "POST", f"/{self._v()}/{pid}/subscribed_apps",
            params={"subscribed_fields": "leadgen"})

    async def list_owned_pages(self) -> ConnectorResult:
        """GET /{v}/me/accounts — the Pages this System-User/token can manage (ownership proof for
        the page-claim flow, B16). Returns data.data = [{id,name,...}]. NEVER raises."""
        return await self._request(
            "GET", f"/{self._v()}/me/accounts",
            params={"fields": "id,name", "limit": "200"})

    async def get_account_funding(self) -> ConnectorResult:
        """GET /{v}/{act_id}?fields=account_status,funding_source,disable_reason,balance,currency,
        amount_spent — the vendor-own-card funding read (B13/B14/B15). `account_status==1` == ACTIVE;
        a non-empty `funding_source` == a payment method is attached. NEVER raises (structured fail).
        """
        act = self._ad_account()
        if not act:
            return ConnectorResult.fail(ConnectorError.NOT_CONFIGURED,
                                        detail="meta: no ad_account_id for funding read")
        return await self._request(
            "GET", f"/{self._v()}/{act}",
            params={"fields": "account_status,funding_source,disable_reason,balance,currency,amount_spent"})

    def verify_webhook_signature(self, app_secret: str, raw_body: bytes,
                                 signature_header: str) -> bool:
        """HMAC-SHA256 verify of the `X-Hub-Signature-256` header — FAIL-CLOSED.

        Meta signs the raw request body with the app secret as `sha256=<hexdigest>`. Any missing
        piece (no secret, no header, malformed) returns False — we never default-accept. Uses a
        constant-time compare to avoid a timing oracle. The caller MUST resolve the tenant's
        app_secret from the page_id->tenant map BEFORE calling (the tenant is not trusted from the
        body) — this function only does the cryptographic check.
        """
        if not app_secret or not signature_header or raw_body is None:
            return False
        sig = signature_header.strip()
        if not sig.startswith("sha256="):
            return False
        provided = sig[len("sha256="):]
        try:
            mac = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256)
            expected = mac.hexdigest()
        except Exception:  # noqa: BLE001 — any crypto error => fail closed
            return False
        try:
            return hmac.compare_digest(expected, provided)
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def parse_leadgen(payload: dict) -> list:
        """Parse a Page/leadgen webhook payload -> [{leadgen_id, page_id, form_id, ad_id, ...}].

        We get IDs, NOT the lead data — `get_lead(leadgen_id)` does the retrieval. Tenant is NEVER
        taken from here for trust; the page_id->tenant map (in store) resolves it. Never raises.
        """
        out: list = []
        try:
            for entry in (payload or {}).get("entry", []) or []:
                for change in entry.get("changes", []) or []:
                    if change.get("field") != "leadgen":
                        continue
                    v = change.get("value") or {}
                    out.append({
                        "leadgen_id": v.get("leadgen_id"),
                        "page_id": v.get("page_id") or entry.get("id"),
                        "form_id": v.get("form_id"),
                        "ad_id": v.get("ad_id"),
                        "adgroup_id": v.get("adgroup_id"),
                        "created_time": v.get("created_time"),
                    })
        except Exception as exc:  # noqa: BLE001 — malformed payload => empty, never raise
            _log.warning("meta.parse_leadgen: malformed payload %r", type(exc).__name__)
            return []
        return out

    async def get_lead(self, leadgen_id: str) -> ConnectorResult:
        """GET /{v}/{leadgen_id}?fields=field_data,form_id,ad_id,created_time,campaign_id,platform."""
        if not leadgen_id:
            return ConnectorResult.fail(ConnectorError.INVALID_REQUEST,
                                        detail="meta: leadgen_id required")
        fields = "field_data,form_id,ad_id,created_time,campaign_id,platform"
        return await self._request("GET", f"/{self._v()}/{leadgen_id}",
                                   params={"fields": fields})

    async def reconcile_leads(self, form_id: str, since: Optional[int] = None) -> ConnectorResult:
        """GET /{v}/{form_id}/leads — the backstop poll (webhooks can silently die post-CA migration,
        research §4). tick.py runs this ~5 min. `since` is a unix filter (Graph `filtering`)."""
        if not form_id:
            return ConnectorResult.fail(ConnectorError.INVALID_REQUEST,
                                        detail="meta: form_id required")
        params: dict = {"fields": "id,created_time,field_data,ad_id,campaign_id"}
        if since:
            params["filtering"] = json.dumps(
                [{"field": "time_created", "operator": "GREATER_THAN", "value": int(since)}],
                separators=(",", ":"))
        return await self._request("GET", f"/{self._v()}/{form_id}/leads", params=params)

    # ======================================================================================
    # 4. INSIGHTS PULL (structure — async job base).
    # ======================================================================================
    async def pull_insights(self, *, level: str = "campaign", ids: Optional[list] = None,
                            fields: Optional[list] = None,
                            date_preset: str = "last_7d",
                            object_id: str = "") -> ConnectorResult:
        """GET /{v}/{object}/insights. Object defaults to the ad account; pass `object_id` for a
        campaign/adset/ad node. `level` controls breakdown granularity. Feeds optimization/analytics.
        """
        obj = object_id or self._ad_account()
        if not obj:
            return ConnectorResult.fail(ConnectorError.NOT_CONFIGURED,
                                        detail="meta: no object for insights")
        f = fields or ["spend", "impressions", "clicks", "actions", "cost_per_action_type",
                       "cpc", "ctr"]
        params: dict = {
            "level": level,
            "fields": ",".join(f),
            "date_preset": date_preset,
        }
        if ids:
            params["filtering"] = json.dumps(
                [{"field": f"{level}.id", "operator": "IN", "value": list(ids)}],
                separators=(",", ":"))
        return await self._request("GET", f"/{self._v()}/{obj}/insights", params=params)

    # ======================================================================================
    # 5. CAPI EVENT SEND (structure — for W6; unified Dataset, NOT legacy offline event sets).
    # ======================================================================================
    @staticmethod
    def _sha256(value: str) -> str:
        return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()

    @classmethod
    def hash_user_data(cls, user_data: dict) -> dict:
        """SHA-256 hash the matching keys (em/ph/fn/ln/ct/st/zp/country/external_id); pass fbp/fbc/
        ctwa_clid PLAINTEXT (hashing them breaks matching — research §5). Already-hashed (64-hex)
        values are left as-is. Never raises."""
        out: dict = {}
        for k, v in (user_data or {}).items():
            if v is None:
                continue
            sval = v if isinstance(v, str) else str(v)
            if k in _CAPI_PLAINTEXT_KEYS:
                out[k] = sval
            elif k in _CAPI_HASH_KEYS:
                # don't double-hash an already-SHA256 value.
                if len(sval) == 64 and all(c in "0123456789abcdef" for c in sval.lower()):
                    out[k] = sval.lower()
                else:
                    out[k] = cls._sha256(sval)
            else:
                out[k] = sval  # custom/unknown matching key -> pass through (caller's choice)
        return out

    def build_capi_event(self, *, event_name: str, event_time: Optional[int] = None,
                         action_source: str = "business_messaging",
                         user_data: Optional[dict] = None,
                         custom_data: Optional[dict] = None,
                         event_id: str = "", event_source_url: str = "") -> dict:
        """Build ONE CAPI server event (research §5). `user_data` is hashed via hash_user_data."""
        ev: dict = {
            "event_name": event_name,
            "event_time": int(event_time if event_time is not None else time.time()),
            "action_source": action_source,
            "user_data": self.hash_user_data(user_data or {}),
        }
        if event_id:
            ev["event_id"] = event_id          # dedup key
        if event_source_url:
            ev["event_source_url"] = event_source_url
        if custom_data:
            ev["custom_data"] = custom_data
        return ev

    async def send_capi(self, events: list, *, test_event_code: str = "",
                        dataset_id: str = "") -> ConnectorResult:
        """POST /{v}/{dataset_id}/events — the unified Dataset CAPI endpoint (NOT the legacy
        offline-event-set path, removed 2025-05-14). Body { data: [...], test_event_code? }.
        Called by feedback.py in W6. `events` should already be built via build_capi_event."""
        ds = dataset_id or self._dataset_id()
        if not ds:
            return ConnectorResult.fail(ConnectorError.NOT_CONFIGURED,
                                        detail="meta: no dataset_id for CAPI")
        if not isinstance(events, list) or not events:
            return ConnectorResult.fail(ConnectorError.INVALID_REQUEST,
                                        detail="meta: no CAPI events")
        body: dict = {"data": events}
        if test_event_code:
            body["test_event_code"] = test_event_code
        return await self._request("POST", f"/{self._v()}/{ds}/events", json=body)

    # ======================================================================================
    # Meta-specific error surfacing (Graph error codes layered over the base status map).
    # ======================================================================================
    def _surface(self, raw: Any) -> Optional[ConnectorError]:
        """Map a parsed Graph error body -> ConnectorError. research: 190 cred_expired, 4/17/613
        rate, 10/200/294 permission. Body shape: {"error": {"code", "error_subcode", ...}}."""
        try:
            err = (raw or {}).get("error") if isinstance(raw, dict) else None
            if not isinstance(err, dict):
                return None
            code = int(err.get("code") or 0)
        except Exception:  # noqa: BLE001
            return None
        if code == 190:
            return ConnectorError.CRED_EXPIRED
        if code in (4, 17, 32, 613):
            return ConnectorError.RATE_LIMITED
        if code in (10, 200, 294, 803):
            return ConnectorError.PERMISSION
        if code in (100, 2635):
            return ConnectorError.INVALID_REQUEST
        return None

    def _parse_rate(self, resp: Any) -> dict:
        """Parse Meta's BUC usage headers (research §8) on top of the base Retry-After parse.
        Surfaces the throttle headers for the breaker/analytics — NEVER any secret."""
        out = super()._parse_rate(resp)
        try:
            headers = getattr(resp, "headers", None)
            if headers is not None:
                for h in ("x-business-use-case-usage", "x-ad-account-usage",
                          "x-fb-ads-insights-throttle"):
                    val = headers.get(h)
                    if val:
                        out[h] = val
        except Exception:  # noqa: BLE001
            pass
        return out
