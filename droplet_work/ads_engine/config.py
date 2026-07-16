"""ads_engine.config — the SINGLE source of flags, caps, version pins, and the EOL/sunset table.

No `from caller import ...`: flags are read from the environment via a tiny degrade-safe
`cfg_get` (os.getenv fallback). The mount may later inject caller's richer `cfg_get` seam;
until then os.getenv is the byte-identical default (FEATURE_ADS default OFF).

Money is ALWAYS minor units (paise), suffix `*_minor`, matching `_lib.ts` + the paise ledger.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Config seam — degrade-safe getter. Replaceable by caller's cfg_get at wire time,
# but defaults to os.getenv so the package is self-contained and import-cheap.
# ---------------------------------------------------------------------------
_cfg_get = None  # optionally set by caller via set_cfg_get(); else os.getenv


def set_cfg_get(fn) -> None:
    """Optionally inject caller.cfg_get (reads .env+config). Best-effort; never required."""
    global _cfg_get
    _cfg_get = fn


def cfg(key: str, default: str = "") -> str:
    try:
        if _cfg_get is not None:
            return _cfg_get(key, default)
    except Exception:  # noqa: BLE001
        pass
    return os.getenv(key, default)


def _flag(key: str, default: str = "0") -> bool:
    return (cfg(key, default) or default).strip().lower() in ("1", "true", "yes", "on")


def _int(key: str, default: int) -> int:
    try:
        return int(str(cfg(key, str(default))).strip())
    except Exception:  # noqa: BLE001
        return default


# ---------------------------------------------------------------------------
# FEATURE FLAGS (default OFF => resting backend byte-identical)
# ---------------------------------------------------------------------------
def is_enabled() -> bool:
    """The master gate. EVERY route 404s when this is False (defense in depth over
    the caller.py mount guard). Default OFF => the ads engine does not exist at rest."""
    return _flag("FEATURE_ADS", "0")


def dry_run() -> bool:
    """When True, propose/optimize compute but never spend / never call a platform."""
    return _flag("ADS_DRY_RUN", "1")  # default DRY (safe): no real spend until explicitly off


def require_approval() -> bool:
    """When True, a proposed campaign MUST be approved (step-up) before it can launch."""
    return _flag("ADS_REQUIRE_APPROVAL", "1")  # default ON: nothing spends without approval


def require_funded() -> bool:
    """BLINDSPOTS B14: when True, a LIVE launch is BLOCKED unless the tenant's funded ad-budget
    balance covers the campaign's monthly budget. Default ON (fail-closed: never publish into an
    un-funded account). Only enforced on the real-spend path; DRY-RUN approvals skip it."""
    return _flag("ADS_REQUIRE_FUNDED", "1")


def autorun_enabled() -> bool:
    """BLINDSPOTS B9: master gate for the AUTONOMY orchestrator (the self-running pipeline that
    chains propose -> creative -> moderation -> viability -> launch). Default OFF => the tick never
    drives autorun even when FEATURE_ADS is on, so enabling the engine does NOT silently start an
    autonomous loop. A tenant must ALSO opt in per-tenant (autorun_config.enabled)."""
    return _flag("ADS_AUTORUN", "0")


def autorun_autolaunch() -> bool:
    """BLINDSPOTS B9/B11: when True the orchestrator may itself APPROVE (launch) a viable campaign
    without a human X-Step-Up — the explicit 'auto-pilot' the vendor enables. Default OFF => the
    orchestrator drives everything UP TO launch and then parks at `launch_pending`, leaving approve
    as the human step-up checkpoint. In ADS_DRY_RUN this only ever produces a dry-run persist."""
    return _flag("ADS_AUTORUN_AUTOLAUNCH", "0")


def _float(key: str, default: float) -> float:
    try:
        return float(str(cfg(key, str(default))).strip())
    except Exception:  # noqa: BLE001
        return default


# ---------------------------------------------------------------------------
# CAMPAIGN-DOMAIN policy knobs (W5). Each has a HARD CODE FLOOR so a mis-set env
# var can NEVER disable a safety gate (REDTEAM spend-optimization-safety C3).
# ---------------------------------------------------------------------------

# REDTEAM C3: the CPA x50 viability gate. The number of conversions a campaign must
# be able to fund to exit Meta's learning phase. CLAMPED >= 50 IN CODE — env can
# only RAISE it, never lower it below the researched floor.
CPA_MULTIPLIER_FLOOR = 50


def cpa_multiplier() -> int:
    """Conversions/period needed to exit learning. Floored at 50 in code (REDTEAM C3)."""
    return max(CPA_MULTIPLIER_FLOOR, _int("ADS_CPA_MULTIPLIER", CPA_MULTIPLIER_FLOOR))


# REDTEAM C3: a launch funded below `viability_block_ratio * monthly_floor` is a HARD
# BLOCK. CLAMPED >= 0.8 IN CODE — env can only TIGHTEN it (raise toward 1.0), never
# loosen it below 0.8. A config of 0 cannot disable the gate.
VIABILITY_BLOCK_RATIO_FLOOR = 0.8


def viability_block_ratio() -> float:
    """Hard-block threshold as a fraction of the monthly floor. Floored at 0.8 (REDTEAM C3)."""
    v = _float("ADS_VIABILITY_BLOCK_RATIO", VIABILITY_BLOCK_RATIO_FLOOR)
    # clamp into [0.8, 1.0]: env may tighten, never loosen below the code floor.
    return max(VIABILITY_BLOCK_RATIO_FLOOR, min(1.0, v))


def default_cpl_minor() -> int:
    """Fallback target CPL (paise) when a brief omits cpl_max_minor. Conservative default."""
    c = caps().get("cpl_max_minor", 0) or 0
    return int(c) if c > 0 else _int("ADS_DEFAULT_CPL_MINOR", 50000)  # Rs500 default


def learning_lock_days() -> int:
    """Days the learning-phase edit lock holds (~7d Meta learning window)."""
    return max(1, _int("ADS_LEARNING_LOCK_DAYS", 7))


def learning_edit_pct() -> float:
    """Max relative budget/bid/targeting edit during learning before Meta resets (~20%)."""
    v = _float("ADS_LEARNING_EDIT_PCT", 0.20)
    return min(1.0, max(0.0, v))


def min_radius_km() -> float:
    """HOUSING geo-radius floor (km). Floored at 25km (~15.5mi, safely above the US 15mi rule).
    Env may RAISE it, never lower below the legal-safe floor."""
    return max(25.0, _float("ADS_MIN_RADIUS_KM", 25.0))


# ---------------------------------------------------------------------------
# CAPS — spend guardrails (paise). Single source of the AdsHealth `caps` block.
# Conservative defaults so an accidental enable cannot run away with spend.
# ---------------------------------------------------------------------------
def caps() -> dict:
    return {
        "daily_cap_minor": _int("ADS_DAILY_CAP_MINOR", 0),            # 0 = per-plan unset
        "lifetime_cap_minor": _int("ADS_LIFETIME_CAP_MINOR", 0),
        "org_daily_cap_minor": _int("ADS_ORG_DAILY_CAP_MINOR", 0),    # 0 = breaker open until set
        "cpl_max_minor": _int("ADS_CPL_MAX_MINOR", 0),
        "cpl_min_conversions": _int("ADS_CPL_MIN_CONVERSIONS", 50),   # CPA x50 viability gate
        "poll_minutes": _int("ADS_POLL_MINUTES", 5),
        "currency": cfg("ADS_CURRENCY", "INR"),
    }


# ---------------------------------------------------------------------------
# VERSION PINS — single-sourced. Drift is NOT prose-managed: `assert_versions_current()`
# runs at import AND ~daily inside the ads tick (run_tick), logging a loud alarm + a
# Decision-Log row when any pin is EXPIRED or within SUNSET_ALARM_DAYS (30d) of sunset.
# Bump the string here; the machine check (not a human bump task) is what catches drift.
# Recorded INTO rows (version_pin) so drift is auditable, not silent.
# ---------------------------------------------------------------------------
META_API_VERSION = "v25.0"          # Meta Marketing/Graph (no ASC/AAC on v25 — standard only)
GOOGLE_ADS_VERSION = "v24"          # Google Ads (v24/v24.1 atomic Mutate)
# WhatsApp Cloud API shares Graph versioning with the Marketing API. v23.0 hit its
# sunset 2026-06-09 (past EOL); pin WhatsApp to the SAME current Graph version as Meta
# so calls don't hit a sunset endpoint. Single-sourced off META_API_VERSION.
WHATSAPP_GRAPH_VERSION = META_API_VERSION  # = "v25.0" (WhatsApp Cloud API on current Graph)

# Google Data Manager API revision — the conversion-feedback path (datamanager.googleapis.com
# :ingestEvents). The Ads-API offline-conversion path is BLOCKED for new integrations from
# 2026-06-15 (we are NOT allowlisted), so ALL conversion feedback goes via Data Manager. Pinned
# here so a silent upstream revision swap is a visible config change. ingestEvents is structured
# for W6 (google.upload_conversions). See EOL_TABLE['google_ads_offline_conversions'].
DATA_MANAGER_API_REVISION = "v1"


def version_pins() -> dict:
    return {
        "meta": META_API_VERSION,
        "google": GOOGLE_ADS_VERSION,
        "whatsapp": WHATSAPP_GRAPH_VERSION,
    }


# ---------------------------------------------------------------------------
# {version: sunset_date} TABLE — per API, the Marketing/Graph + Google-Ads version
# availability windows (research: meta-ads-api.md §1, google-ads-api.md §1). The pinned
# version above MUST stay above its sunset; `version_health()` flags drift for the Decision
# Log and HUMAN_TASKS bump tasks. Dates are ISO; "graph" covers Graph + Marketing API (same
# version string + window) and WhatsApp Cloud API (a Graph version).
# ---------------------------------------------------------------------------
VERSION_SUNSET = {
    "graph": {
        # Meta Graph + Marketing API (~quarterly; ~1-year availability).
        # META_API_VERSION + WHATSAPP_GRAPH_VERSION both pin here (v25.0).
        "v25.0": "2027-02-17",   # META_API_VERSION + WHATSAPP_GRAPH_VERSION pin lives here
        "v24.0": "2026-10-06",
        "v23.0": "2026-06-09",   # SUNSET (past EOL 2026-06-09) — WhatsApp moved off this to v25.0
        "v22.0": "2026-02-18",
        "v21.0": "2025-10-08",
        "v20.0": "2026-09-24",   # EOL watch
        "v19.0": "2026-05-21",   # EOL watch
    },
    "google_ads": {
        # Google Ads API (monthly cadence since Jan 2026; ~1-year sunset).
        "v24.1": "2027-05-13",
        "v24": "2027-05-13",     # GOOGLE_ADS_VERSION pin lives here
        "v23.2": "2027-02-28",
        "v23.1": "2027-02-28",
        "v23": "2027-02-28",
        "v22": "2026-10-15",
        "v21": "2026-08-06",
        "v20": "2026-06-30",     # EOL now
    },
}


def version_health(today_iso: str = "") -> dict:
    """Non-secret drift check: for each pinned version, its sunset date + days-of-runway.

    `today_iso` injectable (tests pass a fixed date; default = real today). Never raises —
    an unknown version just reports sunset=None. Feeds analytics / the Decision Log so a stale
    pin is VISIBLE, not a silent breakage."""
    import datetime as _dt

    try:
        today = _dt.date.fromisoformat(today_iso) if today_iso else _dt.date.today()
    except Exception:  # noqa: BLE001
        today = _dt.date.today()

    def _entry(api_key: str, version: str) -> dict:
        sunset = VERSION_SUNSET.get(api_key, {}).get(version)
        days = None
        if sunset:
            try:
                days = (_dt.date.fromisoformat(sunset) - today).days
            except Exception:  # noqa: BLE001
                days = None
        return {"version": version, "sunset": sunset, "days_to_sunset": days,
                "expired": (days is not None and days < 0)}

    return {
        "meta": _entry("graph", META_API_VERSION),
        "whatsapp": _entry("graph", WHATSAPP_GRAPH_VERSION),
        "google": _entry("google_ads", GOOGLE_ADS_VERSION),
    }


# Number of days of runway at/under which a pinned version is "alarming". The tick
# (run_tick) and the import-time guard both alarm when days_to_sunset <= this (or already
# expired). 30d gives a non-technical operator a month of warning before a SILENT 4xx.
# (redteam api-version-google-block-mtls.md M1/M4: replace prose-only bump notes with a
# real machine check + loud alarm.)
SUNSET_ALARM_DAYS = 30


def version_sunset_alarms(within_days: int = SUNSET_ALARM_DAYS, today_iso: str = "") -> list:
    """The pinned API versions that are EXPIRED or within `within_days` of their sunset.

    Returns a list of {api, version, sunset, days_to_sunset, expired} — EMPTY when every
    pin has healthy runway. Built on `version_health` so it shares the single sunset table.
    Never raises (a bad date / unknown version simply does not alarm). This is the machine
    check the version-sunset guard (import-time + the daily tick pass) consumes."""
    alarms = []
    try:
        health = version_health(today_iso)
    except Exception:  # noqa: BLE001
        return alarms
    for api, h in (health or {}).items():
        days = h.get("days_to_sunset")
        if days is None:
            continue  # unknown version => no sunset known => cannot alarm (reported elsewhere)
        if h.get("expired") or days <= within_days:
            alarms.append({"api": api, "version": h.get("version"), "sunset": h.get("sunset"),
                           "days_to_sunset": days, "expired": bool(h.get("expired"))})
    return alarms


# ---------------------------------------------------------------------------
# IMPORT-TIME SUNSET GUARD (the "startup assertion", crash-proof). On import, if any pinned
# API version is EXPIRED or within SUNSET_ALARM_DAYS of sunset, log a LOUD alarm. Per the
# package HARD RULES (a broken/late ads import must NEVER crash the live caller spine) this
# NEVER raises — it only logs. The tick re-runs the same check ~daily into the Decision Log
# so the alarm is visible to the operator, not just in process logs. Replaces the prose-only
# "quarterly/monthly bump task" note (redteam M1).
# ---------------------------------------------------------------------------
def assert_versions_current() -> list:
    """Log a loud alarm for every pinned version at/under its sunset runway. Returns the
    alarm list (also used by tests). NEVER raises — import/startup must stay crash-proof."""
    try:
        alarms = version_sunset_alarms()
        if alarms:
            import logging as _lg
            log = _lg.getLogger("ads_engine.config")
            for a in alarms:
                state = "EXPIRED" if a.get("expired") else f"sunsets in {a.get('days_to_sunset')}d"
                log.error(
                    "ADS VERSION-SUNSET ALARM: %s pin %s %s (sunset=%s) — BUMP THE PIN in "
                    "ads_engine.config before this breaks as a silent 4xx",
                    a.get("api"), a.get("version"), state, a.get("sunset"))
        return alarms
    except Exception:  # noqa: BLE001 — the guard must never crash the import / live spine
        return []


# Run the guard at import (best-effort, swallowed). Cheap: a few date comparisons.
try:
    assert_versions_current()
except Exception:  # noqa: BLE001
    pass


# ---------------------------------------------------------------------------
# MODEL PINS — creative generation stack (Nano Banana / Ideogram / FLUX.2 / Creatify).
# Pinned so a silent upstream model swap is a visible config change, not a surprise.
# ---------------------------------------------------------------------------
MODEL_PINS = {
    "image_primary": "gemini-2.5-flash-image",   # "Nano Banana"
    "image_text_in_image": "ideogram-v3",        # text-in-image legibility
    "image_alt": "flux.2",                       # FLUX.2 alternate
    "video_avatar": "creatify-v2",               # UGC/avatar video
    "copy": "gemini-2.5-flash",                  # headline/body copy
    # Per-kind creative-batch pins consumed by creative_models (design/creative.md §4).
    "headline_image": "ideogram-v3", "headline_image_fallback": "gemini-3-pro-image-preview",
    "bulk_image": "gemini-2.5-flash-image", "bulk_image_fallback": "gpt-image-1-mini",
    "vector_badge": "recraft-v3", "property_shot": "flux-2-max",
    "multi_size": "bannerbear", "multi_size_fallback": "placid",
    "ugc_video": "creatify-aurora", "raw_video": "luma-dream-machine",
    # HARD EOL BLOCKLIST — these model ids MUST NEVER be used (research/creative-gen-apis.md
    # "Hard constraints"): gpt-image-1 dies 2026-10-23; Veo 3.0 GA dies 2026-06-30.
    "_eol_blocklist": ["gpt-image-1", "veo-3.0", "veo-3.0-fast", "veo-3.0-generate-001"],
}


# ---------------------------------------------------------------------------
# EOL / SUNSET TABLE — known upstream deprecations the engine must NOT silently
# trip over. `feedback`/`connectors` consult this; analytics records pins so a drift
# shows in the Decision Log. Each entry: what, when, the safe path, hard/soft.
# ---------------------------------------------------------------------------
EOL_TABLE = [
    {
        "key": "google_ads_offline_conversions",
        "what": "Google Ads API offline-conversion + EC-for-leads for NEW integrations",
        "sunset": "2026-06-15",
        "hard": True,
        "safe_path": "Google Data Manager API (datamanager.googleapis.com :ingestEvents)",
        "note": "Legacy UploadClickConversions is a HARD NO -> BLOCKED_GOOGLE_LEGACY.",
    },
    {
        "key": "meta_offline_event_sets",
        "what": "Meta Offline Event Sets (legacy offline conversions)",
        "sunset": "2025-05-14",
        "hard": True,
        "safe_path": "Unified Dataset CAPI: POST /{dataset_id}/events",
        "note": "Send all conversions to the unified Dataset, not offline event sets.",
    },
    {
        "key": "meta_asc_aac",
        "what": "Meta Advantage+ Shopping (ASC) / App (AAC) campaign objectives",
        "sunset": "2025-Q4",
        "hard": True,
        "safe_path": "Standard campaign objectives only (OUTCOME_LEADS/SALES/...)",
        "note": "Build standard campaigns; ASC/AAC creation disabled on v25.",
    },
    {
        "key": "meta_webhook_ca",
        "what": "Meta webhook delivery moved to a new internal CA",
        "sunset": "2026-03-31",
        "hard": False,
        "safe_path": "Trust Meta's new CA; mandatory reconcile_leads() backstop poll (~5 min)",
        "note": "Webhooks can silently die post-migration; poll is the backstop.",
    },
    {
        "key": "whatsapp_per_message_pricing",
        "what": "WhatsApp conversation-based -> per-message pricing",
        "sunset": "2025-07-01",
        "hard": False,
        "safe_path": "Meter per message into the paise ledger; route bulk via Marketing Messages API",
        "note": "India Marketing ~Rs0.86, Utility/Auth ~Rs0.12 per message.",
    },
]


def health_block(provider_status: dict | None = None) -> dict:
    """Shape the AdsHealth payload (`_lib.ts` AdsHealth). provider_status = {meta,google}
    derived from 'does a vault row exist?' (NEVER a decrypt). Default-safe."""
    ps = provider_status or {}
    meta_s = ps.get("meta", "not_configured")
    google_s = ps.get("google", "not_configured")
    whatsapp_s = ps.get("whatsapp", "not_configured")
    active = "meta" if meta_s == "configured" else ("google" if google_s == "configured" else "not_configured")
    return {
        "module": "ads_engine",
        "dry_run": dry_run(),
        "require_approval": require_approval(),
        "providers": {"meta": meta_s, "google": google_s, "whatsapp": whatsapp_s},
        "active_provider": active,
        "caps": caps(),
    }
