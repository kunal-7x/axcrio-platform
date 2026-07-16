"""
crm — the self-contained Customer 360 profile spine.

WHY THIS FILE EXISTS
--------------------
``caller.py`` has always done ``import crm as _crm_mod`` (and every ``/contacts*``
route delegates to it), but the module was never present in the repo / image, so
``_crm_mod`` resolved to ``None`` and the ENTIRE native profile + CRM workspace
rendered the dormant "Customer 360 coming soon" state. That is exactly the "we
lost the complete profile analysis" the founder reported.

This module restores it WITHOUT any new infrastructure: it assembles a person's
full A-Z profile (identity · lead truth · temperature · lead score · conversion
chance · interests · behaviour · call timeline · recordings · next-best-action)
PURELY from the data sources that already work today —

  * the leads JSON store        (``caller.LEADS_FILE`` — score / last_outcome /
                                  hot / W7 lifecycle·ai_summary·next_action·
                                  conversion_prob)
  * the calls JSON store        (``caller.CALLS`` — per-call interest / outcome /
                                  duration / room)
  * the per-call transcripts    (``caller.TRANSCRIPT_DIR/{room}.json`` — summary /
                                  objections / sentiment / next_action)
  * a tiny manual-override store (``crm_contacts.json`` — name/email/tags/stage
                                  edits made in the UI; NEVER touches leads)

CIRCULAR-IMPORT NOTE
--------------------
``caller`` imports THIS module during its own import, so we must NOT
``import caller`` at module top level (caller is only half-initialised then).
Every function reaches ``caller`` LAZILY via ``_c()`` — by the time any HTTP
request calls in, ``caller`` is fully loaded and its in-RAM stores are warm.

SAFETY
------
These functions run inside ``asyncio.to_thread`` from the routes; a raised
exception would surface as a 500. So every public entrypoint is wrapped to
degrade to a calm empty/None shape — never raise into a request.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path
from typing import Any, Iterable

# ── lazy bridge to caller.py (its stores + helpers are the source of truth) ──────


def _c():
    """Return the fully-initialised ``caller`` module (lazy — avoids the circular
    import at module load). Returns None only in the pathological case where caller
    failed to import, in which case callers degrade to empty."""
    try:
        import caller  # noqa: PLC0415
        return caller
    except Exception:  # noqa: BLE001
        return None


def _hard_isolation() -> bool:
    """Read TENANT_HARD_ISOLATION off the lazily-loaded caller module (never import
    caller/config at module top — circular-import rule). Fails CLOSED (isolate) if
    caller is unavailable, so the CRM can never widen scope by accident."""
    c = _c()
    if c is None:
        return True
    return bool(getattr(c, "TENANT_HARD_ISOLATION", True))


def _norm(phone: str) -> str:
    s = phone or ""
    # Defensive: the panel URL-encodes a leading "+" as %2B, and a Next.js rewrite can
    # RE-encode it, so a contact id can reach the backend still-escaped ("%2B91..." or
    # even "%252B91..."). Without this, re.sub(r"\D",...) keeps the stray "2" of "%2B"
    # and the lookup misses -> a real lead shows "Contact not found". Decode until stable
    # (a clean stored phone has no "%", so this is a no-op for stored values).
    if "%" in s:
        try:
            from urllib.parse import unquote  # noqa: PLC0415
            for _ in range(3):
                nxt = unquote(s)
                if nxt == s:
                    break
                s = nxt
        except Exception:  # noqa: BLE001
            pass
    c = _c()
    if c is not None:
        try:
            return c.norm(s)
        except Exception:  # noqa: BLE001
            pass
    d = re.sub(r"\D", "", s)
    if d.startswith("0"):
        d = d[1:]
    if len(d) == 10:
        d = "91" + d
    return "+" + d if len(d) >= 11 else ""


def _read(path: Path, default):
    c = _c()
    if c is not None:
        try:
            return c._read(path, default)
        except Exception:  # noqa: BLE001
            pass
    try:
        return json.loads(Path(path).read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _admin_id() -> str:
    c = _c()
    return getattr(c, "ADMIN_ID", "admin") if c is not None else "admin"


def _var() -> Path:
    c = _c()
    if c is not None and getattr(c, "VAR", None) is not None:
        return c.VAR
    return Path("/opt/famit-agent/var")


def _leads_all() -> list[dict]:
    c = _c()
    if c is None:
        return []
    return _read(c.LEADS_FILE, []) or []


def _calls_all() -> list[dict]:
    c = _c()
    if c is None:
        return []
    return list(getattr(c, "CALLS", []) or [])


def _leads_for_org(org: str, is_admin: bool) -> list[dict]:
    adm = _admin_id()
    rows = _leads_all()
    if is_admin and not _hard_isolation():
        return rows
    return [x for x in rows if x.get("tenant_id", adm) == org]


def _calls_for_org(org: str, is_admin: bool) -> list[dict]:
    rows = _calls_all()
    if is_admin and not _hard_isolation():
        return rows
    return [x for x in rows if x.get("tenant_id") == org]


def _transcript_for(rec: dict) -> dict:
    """The transcripts/{room}.json blob for one outbound call (summary/objections/…)."""
    c = _c()
    room = (rec.get("room", "") or "")
    if c is None or not room:
        return {}
    try:
        return _read(c.TRANSCRIPT_DIR / f"{room}.json", {}) or {}
    except Exception:  # noqa: BLE001
        return {}


# ── manual-override store (UI edits; NEVER writes leads) ─────────────────────────
# crm_contacts.json: {"<org>|<phone>": {name?, email?, tags?[], stage?, data?{}}}
_OVERLAY_LOCK = threading.Lock()


def _overlay_path() -> Path:
    return _var() / "crm_contacts.json"


def _overlay_all() -> dict:
    data = _read(_overlay_path(), {})
    return data if isinstance(data, dict) else {}


def _overlay_key(org: str, phone: str) -> str:
    return f"{org}|{_norm(phone) or phone}"


def _overlay_get(org: str, phone: str) -> dict:
    return _overlay_all().get(_overlay_key(org, phone), {}) or {}


def _overlay_put(org: str, phone: str, patch: dict) -> dict:
    c = _c()
    with _OVERLAY_LOCK:
        allo = _overlay_all()
        key = _overlay_key(org, phone)
        cur = dict(allo.get(key, {}) or {})
        for k, v in (patch or {}).items():
            if v is None:
                continue
            cur[k] = v
        allo[key] = cur
        try:
            if c is not None:
                c._write(_overlay_path(), allo)
            else:
                _overlay_path().write_text(json.dumps(allo), "utf-8")
        except Exception:  # noqa: BLE001
            pass
        return cur


# ── small text helpers ───────────────────────────────────────────────────────────


def _lower(s: Any) -> str:
    return str(s or "").lower().strip()


def _num(v: Any) -> int:
    try:
        return int(float(v))
    except Exception:  # noqa: BLE001
        return 0


def _bag(*vals: Any) -> list[str]:
    return [_lower(v) for v in vals if v not in (None, "")]


def _has(bag: list[str], *keys: str) -> bool:
    return any(any(k == v or k in v for k in keys) for v in bag)


# Outcome / lifecycle vocab the agent + W7 FSM emit.
_DEAD = ("opt_out", "opted_out", "not_interested", "dead", "lost", "do_not_call", "dnd")
_WON = ("booked", "won", "converted", "site_visit", "site visit", "purchase", "sale")
_QUAL = ("interested", "qualified")
_ENGAGED = ("engaged", "contacted", "callback", "answered", "call_back")


# ══════════════════════════════════════════════════════════════════════════════════
# TEMPERATURE — the ONE classifier shared with the panel (app/crm/_ui.tsx `tempOf`).
# Hot/Warm/Cold/Dead. `dead` is reserved for an EXPLICIT opt-out / not-interested —
# an unscored brand-new lead is COLD, never dead. Used by the profile analysis AND
# (via temperature_of) by caller.py's GET /leads ?status= filter, so the two never
# drift again.
# ══════════════════════════════════════════════════════════════════════════════════


def temperature_of(lead: dict, calls: list[dict] | None = None) -> str:
    """Pure signals -> "hot" | "warm" | "cold" | "dead". Mirrors the panel's tempOf
    precedence: explicit lifecycle > hard outcomes > score bands > engagement."""
    lead = lead or {}
    lifecycle = _lower(lead.get("lifecycle")) or _lower(lead.get("lifecycle_state"))
    if lifecycle in ("hot", "warm", "cold", "dead"):
        # an explicit terminal `dead` only wins if it is a real terminal — else fall through
        if lifecycle != "dead" or _has(_bag(lead.get("last_outcome"), lead.get("status")), *_DEAD):
            return lifecycle
    if lifecycle in ("booked", "won", "converted"):
        return "hot"

    bag = _bag(lead.get("status"), lead.get("last_outcome"), lead.get("outcome"), lead.get("stage"))
    # latest call outcome reinforces the bag
    if calls:
        bag += _bag(calls[0].get("outcome"))

    if _has(bag, *_DEAD):
        return "dead"
    if lead.get("booked") is True or _has(bag, *_WON) or _has(bag, *_QUAL):
        return "hot"

    score = _num(lead.get("score"))
    if score <= 0 and lead.get("conversion_prob") is not None:
        try:
            score = round(float(lead["conversion_prob"]) * 100)
        except Exception:  # noqa: BLE001
            score = 0
    if lead.get("hot") is True or score >= 70:
        return "hot"
    if score >= 40:
        return "warm"
    if score > 0:
        return "cold"
    if _has(bag, *_ENGAGED):
        return "warm"
    return "cold"


_STAGE_RANK = {
    "new": 0, "contacted": 1, "engaged": 2, "qualified": 3,
    "booked": 4, "won": 5, "lost": 1, "opted_out": 0,
}


def _stage_of(lead: dict, calls: list[dict]) -> str:
    """Lifecycle stage (the §4.1 funnel vocabulary the panel StageBadge renders)."""
    bag = _bag(lead.get("status"), lead.get("last_outcome"), lead.get("stage"))
    if calls:
        bag += _bag(calls[0].get("outcome"))
    if _has(bag, "opt_out", "opted_out", "do_not_call", "dnd"):
        return "opted_out"
    if _has(bag, "not_interested", "dead", "lost"):
        return "lost"
    if _has(bag, "booked", "site_visit", "site visit"):
        return "booked"
    if _has(bag, "won", "converted", "purchase", "sale"):
        return "won"
    if _has(bag, "interested", "qualified"):
        return "qualified"
    answered = sum(1 for c in calls if c.get("answered") or _lower(c.get("outcome")) in _ENGAGED)
    if answered:
        return "engaged"
    if calls:
        return "contacted"
    return "new"


def _interest_level(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    if score > 0:
        return "low"
    return "none"


def _sentiment_of(outcome: str, score: int, tr: dict) -> str:
    s = _lower(tr.get("sentiment"))
    if s in ("positive", "negative", "neutral", "mixed"):
        return s
    o = _lower(outcome)
    if o in ("interested", "booked", "qualified", "converted", "won"):
        return "positive"
    if o in _DEAD:
        return "negative"
    if score >= 70:
        return "positive"
    if 0 < score < 40:
        return "mixed"
    return "neutral"


def _objections_from(tr: dict) -> list[str]:
    raw = tr.get("objections") or tr.get("objection")
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()][:6]
    return []


def _interests_from(lead: dict, calls: list[dict]) -> list[str]:
    """Best-effort topics this person cares about — NEVER fabricated. Pulls from the
    lead's tags + campaign + any structured interest/topic/requirement fields the
    transcript writer left behind. Empty when we genuinely know nothing."""
    out: list[str] = []

    def _add(v: Any):
        if isinstance(v, (list, tuple)):
            for x in v:
                _add(x)
        elif isinstance(v, str) and v.strip():
            t = v.strip()
            if t.lower() not in (x.lower() for x in out):
                out.append(t)

    _add(lead.get("tags"))
    for c in calls[:6]:
        tr = _transcript_for(c)
        for key in ("interests", "topics", "requirements", "product", "needs"):
            _add(tr.get(key))
    return out[:8]


def _journey_of(lead: dict, calls: list[dict], stage: str) -> list[dict]:
    """The funnel path this person has walked, in order, with done/at where known."""
    order = ["new", "contacted", "engaged", "qualified", "booked"]
    cur_rank = _STAGE_RANK.get(stage, 0)
    # map a couple of terminal stages onto the linear funnel for display
    if stage in ("won",):
        cur_rank = _STAGE_RANK["booked"]
    first_call = calls[-1] if calls else None
    out: list[dict] = []
    for i, st in enumerate(order):
        at = ""
        if st == "new":
            at = lead.get("added_at", "") or ""
        elif st == "contacted" and first_call:
            at = first_call.get("started_at", "") or ""
        out.append({"stage": st, "done": i <= cur_rank, "at": at})
    return out


def _analysis(lead: dict, calls: list[dict]) -> dict:
    """The A-Z assessment object the profile renders: temperature, score, conversion
    chance, interest, behaviour signals, call stats, journey. Real signals only."""
    score = _num(lead.get("score"))
    cp = lead.get("conversion_prob")
    try:
        conv = float(cp) if cp is not None else (score / 100.0)
    except Exception:  # noqa: BLE001
        conv = score / 100.0
    conv = max(0.0, min(1.0, conv))

    temp = temperature_of(lead, calls)
    last_outcome = lead.get("last_outcome", "") or (calls[0].get("outcome", "") if calls else "")
    latest_tr = _transcript_for(calls[0]) if calls else {}

    total = len(calls)
    answered = sum(1 for c in calls if c.get("answered") or _lower(c.get("outcome")) in _ENGAGED)
    talk = sum(_num(c.get("duration_s")) for c in calls)
    no_answer = sum(1 for c in calls if _lower(c.get("outcome")) in ("no_answer", "voicemail", "no_human"))

    # engagement: did they actually talk, and for how long
    if answered and talk >= 60:
        engagement = "high"
    elif answered:
        engagement = "medium"
    else:
        engagement = "low" if total else "none"

    # responsiveness: do they pick up
    if answered:
        responsiveness = "responsive"
    elif no_answer and total:
        responsiveness = "unreachable"
    elif total:
        responsiveness = "slow"
    else:
        responsiveness = "unknown"

    sentiment = _sentiment_of(last_outcome, score, latest_tr)
    objections = _objections_from(latest_tr)

    # momentum: only when >=2 SCORED calls — never fabricate a trend
    scored = [_num(c.get("interest")) for c in calls if _num(c.get("interest")) > 0]
    momentum = ""
    if len(scored) >= 2:
        # calls are newest-first -> scored[0] is latest
        if scored[0] > scored[-1] + 5:
            momentum = "rising"
        elif scored[0] < scored[-1] - 5:
            momentum = "cooling"
        else:
            momentum = "steady"

    stage = _stage_of(lead, calls)
    interests = _interests_from(lead, calls)
    summary = (lead.get("ai_summary") or latest_tr.get("summary") or "").strip()
    next_action = (lead.get("next_action") or latest_tr.get("next_action") or "").strip()

    # a human-readable reason for the temperature, so the badge isn't a black box
    reason = _temp_reason(temp, score, last_outcome, answered, total)

    signals: list[dict] = []
    if total:
        signals.append({"label": "Calls", "value": str(total), "tone": "neutral"})
        signals.append({"label": "Answered", "value": f"{answered}/{total}",
                        "tone": "success" if answered else "neutral"})
    if talk:
        signals.append({"label": "Talk time", "value": _fmt_clock(talk), "tone": "neutral"})
    if objections:
        signals.append({"label": "Objections", "value": str(len(objections)), "tone": "warning"})
    if momentum:
        signals.append({"label": "Momentum", "value": momentum.title(),
                        "tone": "success" if momentum == "rising" else
                        "danger" if momentum == "cooling" else "neutral"})

    return {
        "temperature": temp,
        "temperature_reason": reason,
        "stage": stage,
        "score": score,
        "conversion_prob": round(conv, 3),
        "conversion_pct": int(round(conv * 100)),
        "interest_level": _interest_level(score),
        "interests": interests,
        "behaviour": {
            "engagement": engagement,
            "responsiveness": responsiveness,
            "sentiment": sentiment,
            "objections": objections,
            "momentum": momentum,
        },
        "signals": signals,
        "stats": {
            "total_calls": total,
            "answered_calls": answered,
            "missed_calls": no_answer,
            "talk_time_s": talk,
            "first_contact_at": (calls[-1].get("started_at", "") if calls else ""),
            "last_contact_at": (calls[0].get("started_at", "") if calls else
                                lead.get("last_call_at", "") or ""),
        },
        "journey": _journey_of(lead, calls, stage),
        "summary": summary,
        "next_action": next_action,
    }


def _temp_reason(temp: str, score: int, outcome: str, answered: int, total: int) -> str:
    o = (outcome or "").replace("_", " ").strip()
    if temp == "dead":
        return f"Marked {o or 'not interested'} — outreach is paused."
    if temp == "hot":
        if score >= 70:
            return f"Scored {score}/100 on a call — high buying intent."
        return "Booked or qualified — strong intent to convert."
    if temp == "warm":
        if score >= 40:
            return f"Scored {score}/100 — engaged but not yet committed."
        return "Engaged on a call — worth nurturing."
    if total and not answered:
        return "Not reached yet — keep trying to make first contact."
    if not total:
        return "New lead — no calls placed yet."
    return "Low intent so far — needs a stronger pitch."


def _fmt_clock(sec: int) -> str:
    sec = max(0, int(sec or 0))
    if sec >= 3600:
        return f"{sec // 3600}h {sec % 3600 // 60}m"
    if sec >= 60:
        return f"{sec // 60}m {sec % 60}s"
    return f"{sec}s"


# ── build a full contact from a lead (+ its calls + manual overlay) ──────────────


def _calls_for_phone(org_calls: list[dict], phone_n: str) -> list[dict]:
    rows = [c for c in org_calls
            if _norm(c.get("phone", "")) == phone_n or (c.get("phone", "") or "") == phone_n]
    rows.sort(key=lambda c: (c.get("started_at", "") or ""), reverse=True)
    return rows


def _build_contact(org: str, lead: dict, calls: list[dict], *, with_analysis: bool = True) -> dict:
    lead = lead or {}
    phone_raw = lead.get("phone", "") or (calls[0].get("phone", "") if calls else "")
    phone_n = _norm(phone_raw) or phone_raw
    ov = _overlay_get(org, phone_n)

    score = _num(lead.get("score"))
    temp = temperature_of(lead, calls)
    stage = ov.get("stage") or _stage_of(lead, calls)

    last_call_at = lead.get("last_call_at", "") or (calls[0].get("started_at", "") if calls else "")
    last_activity = (last_call_at or lead.get("lifecycle_at", "")
                     or lead.get("added_at", "") or "")

    name = ov.get("name") or lead.get("name") or (calls[0].get("name", "") if calls else "") or ""
    campaign_id = lead.get("campaign_id", "") or (calls[0].get("campaign_id", "") if calls else "")
    campaign_name = lead.get("campaign_name", "") or (calls[0].get("campaign_name", "") if calls else "")

    tags = ov.get("tags")
    if tags is None:
        tags = lead.get("tags") if isinstance(lead.get("tags"), list) else []

    data = {
        "tags": tags,
        "batch_id": lead.get("batch_id", ""),
        "source_file": lead.get("source_file", ""),
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
    }
    if isinstance(ov.get("data"), dict):
        data.update(ov["data"])

    contact = {
        "id": phone_n,
        "org_id": org,
        "phone_key": phone_n,
        "phone_display": phone_raw or phone_n,
        "name": name,
        "email": ov.get("email", "") or lead.get("email", "") or "",
        "stage": stage,
        "score": score,
        "hot": bool(lead.get("hot") or score >= 70 or temp == "hot"),
        "last_outcome": lead.get("last_outcome", "") or (calls[0].get("outcome", "") if calls else ""),
        "last_activity_at": last_activity or None,
        "lifecycle_state": lead.get("lifecycle", "") or temp,
        # `temp` is transcript-free (temperature_of), so it's always cheap to expose —
        # this lets list rows show the right Hot/Warm/Cold/Dead band WITHOUT building the
        # full (transcript-reading) analysis on the list path.
        "temperature": temp,
        "consent_call": ov.get("consent_call", True) is not False,
        "consent_wa": ov.get("consent_wa", True) is not False,
        "created_at": lead.get("added_at", "") or "",
        "updated_at": lead.get("lifecycle_at", "") or lead.get("added_at", "") or "",
        "campaign": campaign_name or campaign_id,
        "campaign_name": campaign_name,
        "data": data,
    }
    if with_analysis:
        an = _analysis(lead, calls)
        contact["analysis"] = an
        data["analysis"] = an
    return contact


def _list_item(contact: dict) -> dict:
    """Trim a full contact to the GET /contacts list-row shape."""
    return {
        "id": contact["id"],
        "phone_display": contact["phone_display"],
        "name": contact["name"],
        "stage": contact["stage"],
        "score": contact["score"],
        "hot": contact["hot"],
        "last_outcome": contact["last_outcome"],
        "last_activity_at": contact["last_activity_at"],
        "lifecycle": contact["lifecycle_state"],
        "lifecycle_state": contact["lifecycle_state"],
        "campaign": contact.get("campaign", ""),
        "campaign_name": contact.get("campaign_name", ""),
        # cheap temperature (no transcript read): analysis when present, else the
        # transcript-free `temperature` we always stamp, else the lifecycle fallback.
        "temperature": (contact.get("analysis") or {}).get("temperature")
        or contact.get("temperature")
        or contact["lifecycle_state"],
    }


def _index_contacts(org: str, is_admin: bool, *, with_analysis: bool) -> list[dict]:
    """Union of every lead + every called number into full contact objects (one per
    canonical phone). Leads win the identity; call-only numbers still get a row."""
    leads = _leads_for_org(org, is_admin)
    calls = _calls_for_org(org, is_admin)

    calls_by_phone: dict[str, list[dict]] = {}
    for c in calls:
        p = _norm(c.get("phone", "")) or (c.get("phone", "") or "")
        if not p:
            continue
        calls_by_phone.setdefault(p, []).append(c)
    for rows in calls_by_phone.values():
        rows.sort(key=lambda c: (c.get("started_at", "") or ""), reverse=True)

    seen: set[str] = set()
    out: list[dict] = []
    for lead in leads:
        p = _norm(lead.get("phone", "")) or (lead.get("phone", "") or "")
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(_build_contact(org, lead, calls_by_phone.get(p, []), with_analysis=with_analysis))
    # call-only numbers (e.g. inbound) that never became a lead
    for p, rows in calls_by_phone.items():
        if p in seen:
            continue
        seen.add(p)
        # synthesize a minimal lead view from the most-recent call
        top = rows[0]
        synth = {"phone": top.get("phone", "") or p, "name": top.get("name", ""),
                 "score": _num(top.get("interest")), "last_outcome": top.get("outcome", ""),
                 "last_call_at": top.get("started_at", ""), "tenant_id": top.get("tenant_id", org)}
        out.append(_build_contact(org, synth, rows, with_analysis=with_analysis))
    return out


# ══════════════════════════════════════════════════════════════════════════════════
# PUBLIC CONTRACT — the exact functions caller.py's /contacts* routes already call.
# Every one is defensive: any failure degrades to a calm empty/None shape.
# ══════════════════════════════════════════════════════════════════════════════════


def contact_id(org: str, phone: str) -> str:
    """Stable id for a phone. We use the canonical phone itself as the id (the routes
    accept either a phone OR a ct_ id), so the timeline/recordings/memory all key by
    the same value with zero indirection."""
    try:
        return _norm(phone) or (phone or "")
    except Exception:  # noqa: BLE001
        return phone or ""


def _resolve_phone(org: str, phone_or_id: str, is_admin: bool) -> str:
    """Map a path param (canonical phone, raw phone, or ct_<hash> id) to the canonical
    phone we key everything on."""
    s = str(phone_or_id or "")
    if s.startswith("ct_"):
        # legacy ct_ id = sha1(org|phone)[:12]; reverse-scan the org's leads/calls.
        for lead in _leads_for_org(org, is_admin):
            p = _norm(lead.get("phone", ""))
            if p and _ct_hash(org, p) == s:
                return p
        for c in _calls_for_org(org, is_admin):
            p = _norm(c.get("phone", ""))
            if p and _ct_hash(org, p) == s:
                return p
        return ""
    return _norm(s) or s


def _ct_hash(org: str, phone_n: str) -> str:
    return "ct_" + hashlib.sha1(f"{org}|{phone_n}".encode()).hexdigest()[:12]


def get_contact(org: str, phone: str, *, is_admin: bool = False) -> dict | None:
    """One full contact (identity + lead truth + analysis), no timeline attached."""
    try:
        phone_n = _resolve_phone(org, phone, is_admin)
        if not phone_n:
            return None
        lead = next((x for x in _leads_for_org(org, is_admin)
                     if _norm(x.get("phone", "")) == phone_n), None)
        calls = _calls_for_phone(_calls_for_org(org, is_admin), phone_n)
        if lead is None and not calls:
            return None
        if lead is None:
            top = calls[0]
            lead = {"phone": top.get("phone", "") or phone_n, "name": top.get("name", ""),
                    "score": _num(top.get("interest")), "last_outcome": top.get("outcome", ""),
                    "last_call_at": top.get("started_at", "")}
        return _build_contact(org, lead, calls, with_analysis=True)
    except Exception:  # noqa: BLE001
        return None


def project_contact(org: str, phone: str, *, is_admin: bool = False) -> dict | None:
    """Same as get_contact but ALSO attaches `_timeline` (newest-first, up to 500) so
    the route doesn't issue a second timeline read. PERF: one assembly pass."""
    try:
        c = get_contact(org, phone, is_admin=is_admin)
        if c is None:
            return None
        c["_timeline"] = _timeline_for_phone(org, c["phone_key"], is_admin, limit=500, kinds=None)
        return c
    except Exception:  # noqa: BLE001
        return None


def list_contacts(org: str, *, stage: str = "", hot: bool | None = None, q: str = "",
                  sort: str = "last_activity_at", limit: int = 100, offset: int = 0,
                  is_admin: bool = False) -> dict:
    """Filtered/sorted/PAGED contact list. Returns {contacts:[list-row], total, offset,
    limit, next}. List rows are built WITHOUT the (transcript-reading) analysis — the row
    only needs the transcript-free temperature/score/stage — so the workspace list stays
    O(leads) with no per-contact disk-read storm. Full analysis is only paid on the
    single-contact reads (get_contact / project_contact)."""
    try:
        items = _index_contacts(org, is_admin, with_analysis=False)
        if stage:
            want = _lower(stage)
            items = [c for c in items
                     if _lower(c["stage"]) == want or c.get("temperature") == want]
        if hot is True:
            items = [c for c in items if c["hot"]]
        elif hot is False:
            items = [c for c in items if not c["hot"]]
        if q:
            ql = q.lower().strip()
            items = [c for c in items
                     if ql in _lower(c["name"]) or ql in _lower(c["phone_display"])]
        s = _lower(sort)
        if s == "score":
            items.sort(key=lambda c: c["score"], reverse=True)
        elif s == "stage":
            items.sort(key=lambda c: _STAGE_RANK.get(c["stage"], 0), reverse=True)
        elif s == "name":
            items.sort(key=lambda c: _lower(c["name"]))
        else:  # last_activity_at (default) — newest first
            items.sort(key=lambda c: (c["last_activity_at"] or ""), reverse=True)
        total = len(items)
        off = max(0, int(offset or 0))
        lim = max(1, min(int(limit or 100), 1000))
        rows = [_list_item(c) for c in items[off:off + lim]]
        nxt = off + lim if (off + lim) < total else None
        return {"contacts": rows, "total": total, "offset": off, "limit": lim, "next": nxt}
    except Exception:  # noqa: BLE001
        return {"contacts": [], "total": 0, "offset": 0, "limit": int(limit or 100), "next": None}


# ── timeline ──────────────────────────────────────────────────────────────────────


def _call_timeline_row(c: dict) -> dict:
    tr = _transcript_for(c)
    outcome = c.get("outcome", "") or tr.get("outcome", "")
    summary = (tr.get("summary", "") or "").strip()
    title = "Call"
    o = (outcome or "").replace("_", " ").strip()
    if o:
        title = f"Call · {o}"
    return {
        "kind": "call",
        "direction": "outbound",
        "title": title,
        "body": summary,
        "outcome": outcome,
        "amount": None,
        "currency": "",
        "at": c.get("started_at", "") or "",
        "source": "calls",
        # source_id = call.id || room -> exactly what GET /calls/{id}/transcript accepts
        "source_id": c.get("id", "") or c.get("room", "") or "",
    }


def _wa_timeline_rows(org: str, phone_n: str, is_admin: bool) -> list[dict]:
    c = _c()
    if c is None:
        return []
    try:
        if is_admin and not _hard_isolation() and hasattr(c, "_wa_thread_find_any"):
            th = c._wa_thread_find_any(phone_n)
        elif hasattr(c, "_wa_thread_read"):
            th = c._wa_thread_read(phone_n, org)
        else:
            return []
    except Exception:  # noqa: BLE001
        return []
    turns = (th or {}).get("turns", []) or []
    rows: list[dict] = []
    for t in turns:
        if not isinstance(t, dict):
            continue
        text = (t.get("text") or t.get("content") or "").strip()
        if not text:
            continue
        role = _lower(t.get("role"))
        rows.append({
            "kind": "whatsapp",
            "direction": "inbound" if role in ("user", "customer", "lead") else "outbound",
            "title": "WhatsApp",
            "body": text,
            "outcome": "",
            "amount": None,
            "currency": "",
            "at": str(t.get("ts", "") or t.get("created_at", "") or ""),
            "source": "whatsapp",
            "source_id": "",
        })
    return rows


def _timeline_for_phone(org: str, phone_or_id: str, is_admin: bool,
                        limit: int = 100, kinds: list[str] | None = None) -> list[dict]:
    phone_n = _resolve_phone(org, phone_or_id, is_admin)
    if not phone_n:
        return []
    calls = _calls_for_phone(_calls_for_org(org, is_admin), phone_n)
    rows: list[dict] = [_call_timeline_row(c) for c in calls]
    try:
        rows += _wa_timeline_rows(org, phone_n, is_admin)
    except Exception:  # noqa: BLE001
        pass
    # a calm "Lead added" anchor at the bottom of the journey
    lead = next((x for x in _leads_for_org(org, is_admin)
                 if _norm(x.get("phone", "")) == phone_n), None)
    if lead and lead.get("added_at"):
        rows.append({
            "kind": "system", "direction": "", "title": "Lead added",
            "body": (f"Imported from {lead.get('source_file')}" if lead.get("source_file") else ""),
            "outcome": "", "amount": None, "currency": "",
            "at": lead.get("added_at", "") or "", "source": "leads", "source_id": "",
        })
    rows = [r for r in rows if r.get("at")]
    rows.sort(key=lambda r: r["at"], reverse=True)
    if kinds:
        kset = {_lower(k) for k in kinds}
        rows = [r for r in rows if r["kind"] in kset]
    return rows[: max(1, int(limit or 100))]


def get_timeline(org: str, contact_id_: str, *, limit: int = 100,
                 kinds: list[str] | None = None, is_admin: bool = False) -> list[dict]:
    try:
        return _timeline_for_phone(org, contact_id_, is_admin, limit=limit, kinds=kinds)
    except Exception:  # noqa: BLE001
        return []


# ── next best action (deterministic rules; no metered call) ──────────────────────


def next_best_action(org: str, contact: dict, *, timeline: list[dict] | None = None,
                     is_admin: bool = False) -> dict:
    try:
        an = (contact or {}).get("analysis") or {}
        temp = an.get("temperature") or temperature_of(contact or {})
        stage = (contact or {}).get("stage", "")
        score = _num((contact or {}).get("score"))
        last_outcome = _lower((contact or {}).get("last_outcome"))
        stats = an.get("stats") or {}
        total = _num(stats.get("total_calls"))
        answered = _num(stats.get("answered_calls"))

        def nba(action, reason, conf, pin):
            return {"action": action, "reason": reason, "confidence": round(conf, 2),
                    "params": {}, "requires_pin": bool(pin)}

        if temp == "dead" or stage in ("opted_out", "lost"):
            return nba("none", "This person opted out / isn't interested — outreach is paused.", 0.0, False)
        if stage in ("booked", "won"):
            return nba("nurture", "Already booked — keep them warm and confirm the next step.", 0.6, False)
        if "callback" in last_outcome:
            return nba("retry_call", "They asked for a callback — ring them back at the agreed time.", 0.85, True)
        if temp == "hot":
            if total and answered:
                return nba("send_whatsapp", "Hot and engaged — send a tailored follow-up to close.", 0.8, True)
            return nba("place_call", "Hot lead — call now while intent is high.", 0.85, True)
        if temp == "warm":
            return nba("send_whatsapp", "Warm lead — a personal WhatsApp nudge keeps momentum.", 0.7, True)
        if total and not answered:
            return nba("retry_call", "Not reached yet — try a different time of day.", 0.65, True)
        if not total:
            return nba("place_call", "New lead — place the first call to qualify them.", 0.7, True)
        return nba("reengage", "Low intent so far — re-engage with a fresh angle.", 0.5, False)
    except Exception:  # noqa: BLE001
        return {"action": "none", "reason": "", "confidence": 0.0, "params": {}, "requires_pin": False}


# ── upsert / update (manual overlay only — NEVER writes leads) ───────────────────


def upsert_contact(org: str, phone: str, *, name: str = "", is_admin: bool = False) -> dict | None:
    """Ensure a contact resolves for a freshly-called number. Identity is DERIVED from
    leads/calls, so the only durable thing to record is an optional name override.
    Deliberately LIGHTWEIGHT — this runs in the per-call finalize path, so it must NOT
    build the full (transcript-reading) analysis. Only writes the overlay name when the
    person has no name anywhere yet; returns a minimal contact stub (caller discards it)."""
    try:
        phone_n = _norm(phone) or phone
        if not phone_n:
            return None
        ov = _overlay_get(org, phone_n)
        lead_name = next((x.get("name", "") for x in _leads_for_org(org, is_admin)
                          if _norm(x.get("phone", "")) == phone_n and (x.get("name") or "")), "")
        if name and not ov.get("name") and not lead_name:
            # only persist when the person has NO name anywhere — never clobber a real one
            _overlay_put(org, phone_n, {"name": name})
            ov = {**ov, "name": name}
        return {
            "id": phone_n, "phone_key": phone_n, "phone_display": phone or phone_n,
            "name": ov.get("name", "") or lead_name or name,
        }
    except Exception:  # noqa: BLE001
        return None


def update_contact(org: str, phone: str, *, name: str | None = None, email: str | None = None,
                   tags: Iterable | None = None, stage: str | None = None,
                   data: dict | None = None, is_admin: bool = False) -> dict | None:
    """Persist a MANUAL contact override (name/email/tags/stage/data). Never touches
    the lead row — the override is merged on read in _build_contact."""
    try:
        phone_n = _norm(phone) or phone
        if not phone_n:
            return None
        patch: dict = {}
        if name is not None:
            patch["name"] = name
        if email is not None:
            patch["email"] = email
        if tags is not None:
            patch["tags"] = [str(t) for t in tags] if not isinstance(tags, str) else \
                [s.strip() for s in tags.split(",") if s.strip()]
        if stage is not None:
            patch["stage"] = stage
        if isinstance(data, dict):
            patch["data"] = data
        _overlay_put(org, phone_n, patch)
        return get_contact(org, phone_n, is_admin=is_admin)
    except Exception:  # noqa: BLE001
        return None


# ── relationship memory + episodes (for the profile Memory tab) ──────────────────
# The panel's GET /leads/{phone}/memory + /episodes call these via caller.py. Built
# from the lead's durable fields + one episode per call (summary/sentiment/outcome).


def lead_memory(org: str, phone: str, *, is_admin: bool = False) -> dict | None:
    try:
        c = get_contact(org, phone, is_admin=is_admin)
        if c is None:
            return None
        an = c.get("analysis") or {}
        beh = an.get("behaviour") or {}
        stats = an.get("stats") or {}
        durable = {k: v for k, v in {
            "name": c.get("name"),
            "phone": c.get("phone_display"),
            "stage": c.get("stage"),
            "temperature": an.get("temperature"),
            "interest level": an.get("interest_level"),
        }.items() if v}
        prefs = {}
        for i, topic in enumerate((an.get("interests") or [])[:6]):
            prefs[f"interest {i + 1}"] = topic
        last_outcome = {}
        if c.get("last_outcome"):
            last_outcome["outcome"] = c["last_outcome"]
        if beh.get("sentiment"):
            last_outcome["sentiment"] = beh["sentiment"]
        if an.get("summary"):
            last_outcome["summary"] = an["summary"]
        nba = next_best_action(org, c, is_admin=is_admin)
        memory = {
            "profile": durable,
            "durable_facts": durable,
            "preferences": prefs,
            "last_outcome": last_outcome,
            "next_best_action": {"action": nba.get("action", ""), "reason": nba.get("reason", "")},
            "episode_count": stats.get("total_calls", 0),
            "version": 1,
            "last_channel": "call" if stats.get("total_calls") else "",
            "last_seen_at": stats.get("last_contact_at", "") or "",
            "updated_at": c.get("updated_at", "") or "",
        }
        return memory
    except Exception:  # noqa: BLE001
        return None


def lead_episodes(org: str, phone: str, *, limit: int = 50, offset: int = 0,
                  is_admin: bool = False) -> dict:
    try:
        phone_n = _resolve_phone(org, phone, is_admin)
        if not phone_n:
            return {"episodes": [], "total": 0, "offset": offset, "limit": limit, "next": None}
        calls = _calls_for_phone(_calls_for_org(org, is_admin), phone_n)
        eps: list[dict] = []
        for i, c in enumerate(calls):
            tr = _transcript_for(c)
            outcome = c.get("outcome", "") or tr.get("outcome", "")
            score = _num(c.get("interest"))
            eps.append({
                "id": i + 1,
                "channel": "call",
                "summary": (tr.get("summary", "") or "").strip(),
                "objections": _objections_from(tr),
                "sentiment": _sentiment_of(outcome, score, tr),
                "outcome": outcome,
                "transcript_ref": c.get("id", "") or c.get("room", "") or "",
                "meta": {"duration_s": _num(c.get("duration_s")), "interest": score},
                "created_at": c.get("started_at", "") or "",
            })
        total = len(eps)
        off = max(0, int(offset or 0))
        lim = max(1, min(int(limit or 50), 200))
        page = eps[off:off + lim]
        nxt = off + lim if (off + lim) < total else None
        return {"episodes": page, "total": total, "offset": off, "limit": lim, "next": nxt}
    except Exception:  # noqa: BLE001
        return {"episodes": [], "total": 0, "offset": offset, "limit": limit, "next": None}
