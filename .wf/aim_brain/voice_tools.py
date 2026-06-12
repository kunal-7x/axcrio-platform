"""ai_manager/voice_tools.py — loopback command bridge for the INBOUND manager voice agent.

The inbound `manager` voice agent (aim_voice_agent.py) exposes @function_tools the LLM calls AFTER the
caller has PIN-verified. Those tools delegate here. This module is a THIN, READ-ONLY-over-HTTP client of
the SAME backend the panel + chat Test Console use — caller.py on loopback :8209 — authenticated as the
admin tenant with the box's legacy admin credential (X-Auth). It NEVER imports/edits caller.py, agent.py,
trunks, firewall or SIP; it only makes HTTP calls to already-live routes.

WHY HTTP-to-/run (not the chat `leads.enqueue_calls` workforce tool): the chat path's enqueue tool tries
to reach an HTTP target that 404s in the box-local test path, so it parks (noop) and never actually dials.
`POST /run` is the PROVEN dial path — the EXACT route the panel "Run Campaign" button hits, the same one
that rings outbound. So run_campaign here resolves the audience client-side (read /leads, filter by
segment, take the first N), then posts explicit `lead_ids` to /run (preview==dials, count honored) so a
spoken "run Codename Joy, hot leads, 5" actually rings 5 phones.

SAFETY: every function NEVER raises — on any error it returns a short spoken-friendly string the agent
reads out. The risk gate (PIN-verified + spoken read-back confirm) lives in the agent's function-tool, not
here; this module is the executor once the gate has passed. Reads (lead counts / calls / analytics /
wallet) carry no extra PIN by design.
"""
from __future__ import annotations

import os
import re
from typing import Any

try:
    import httpx  # type: ignore
except Exception:  # noqa: BLE001
    httpx = None  # type: ignore

# Loopback base URL + admin credential. Both overridable via env; defaults match the live box.
_BASE = (os.getenv("AIM_CALLER_BASE_URL", "http://127.0.0.1:8209") or "http://127.0.0.1:8209").rstrip("/")
_ADMIN_CRED = (os.getenv("AIM_CALLER_ADMIN_CRED")
               or os.getenv("CALLER_PASS")
               or "FamitCall2026").strip()
_TIMEOUT = float(os.getenv("AIM_CALLER_TIMEOUT", "12"))
_HEADERS = {"X-Auth": _ADMIN_CRED}


# ── FIX (E): ONE keep-alive POOLED httpx client (not a fresh client per call) ──────────────────────
# The old _client() built a brand-new httpx.Client (new TCP + connection setup) on EVERY read/dial.
# On loopback that's small but non-zero and it adds up across a chatty voice turn. A single module-
# level client with a keep-alive connection pool reuses the warm connection, shaving per-call setup.
# Lazily built + thread-safe (tools run via asyncio.to_thread). Auto-heals if it gets closed.
import threading as _threading  # noqa: E402

_POOL_LOCK = _threading.Lock()
_POOL: "httpx.Client | None" = None


def _client() -> "httpx.Client":
    """Return the shared, keep-alive pooled client (built once). Falls back to a fresh client only if
    httpx is missing the Limits API (older versions). NEVER returns a closed client."""
    global _POOL
    if httpx is None:  # pragma: no cover — httpx is present on the box
        raise RuntimeError("httpx unavailable")
    c = _POOL
    if c is not None and not getattr(c, "is_closed", False):
        return c
    with _POOL_LOCK:
        if _POOL is not None and not getattr(_POOL, "is_closed", False):
            return _POOL
        try:
            limits = httpx.Limits(max_keepalive_connections=8, max_connections=16,
                                  keepalive_expiry=30.0)
            _POOL = httpx.Client(base_url=_BASE, headers=_HEADERS, timeout=_TIMEOUT, limits=limits)
        except Exception:  # noqa: BLE001 — very old httpx without Limits; still pooled per-process
            _POOL = httpx.Client(base_url=_BASE, headers=_HEADERS, timeout=_TIMEOUT)
        return _POOL


def _get(path: str, params: dict | None = None) -> Any:
    c = _client()
    r = c.get(path, params=params or {})
    r.raise_for_status()
    return r.json()


def _post_form(path: str, data: dict) -> Any:
    c = _client()
    r = c.post(path, data=data)
    # /run can legitimately return 202 (queued out of window) or 402 (no balance); surface, don't raise.
    if r.status_code >= 500:
        r.raise_for_status()
    try:
        return {"_status": r.status_code, **(r.json() if r.content else {})}
    except Exception:  # noqa: BLE001
        return {"_status": r.status_code, "_text": (r.text or "")[:200]}


# ───────────────────────── campaign resolution ─────────────────────────────────
def list_campaigns() -> list[dict]:
    try:
        d = _get("/campaigns")
        return list(d.get("campaigns", []) or [])
    except Exception:  # noqa: BLE001
        return []


def _camp_name(c: dict) -> str:
    f = c.get("fields", {}) or {}
    return str(c.get("name") or f.get("company_name") or f.get("product_name") or "").strip()


def campaigns_summary() -> dict:
    """Spoken-friendly enumeration of ALL campaigns (real data, never invented). Returns the count and
    a readable list of "name (status)" so the agent can answer "how many campaigns / list my campaigns"
    truthfully. The agent MUST call this — it must never guess a campaign name or count."""
    camps = list_campaigns()
    if not camps:
        return {"ok": True, "count": 0, "campaigns": [],
                "summary": "I don't see any campaigns on your account yet."}
    items = []
    for c in camps:
        nm = _camp_name(c) or "(unnamed)"
        st = str(c.get("status") or "").strip() or "ready"
        items.append({"id": str(c.get("id", "")), "name": nm, "status": st})
    names = "; ".join(f"{i['name']} ({i['status']})" for i in items)
    n = len(items)
    return {"ok": True, "count": n, "campaigns": items,
            "summary": (f"You have {n} campaign{'s' if n != 1 else ''}: {names}.")}


def campaign_details(spoken: str) -> dict:
    """Full detail for ONE campaign, resolved from a spoken name/id (forgiving match), read from GET
    /campaigns/{id} and unwrapped from the {"campaign":{...}} envelope. Real data only — if no match,
    say so. Speaks status + goal + language + calling window so the manager hears the real config."""
    camp = resolve_campaign(spoken)
    if camp is None:
        avail = ", ".join(_camp_name(c) for c in list_campaigns()[:8] if _camp_name(c))
        return {"ok": False, "summary": (f"I couldn't find a campaign called {spoken}." +
                (f" The ones you have are: {avail}." if avail else ""))}
    cid = str(camp.get("id", ""))
    try:
        d = _get(f"/campaigns/{cid}")
        full = (d.get("campaign") or d) if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        full = camp  # fall back to the list-view fields we already have
    f = full.get("fields", {}) or {}
    name = _camp_name(full) or _camp_name(camp) or spoken
    status = str(full.get("status") or camp.get("status") or "ready").strip()
    goal = str(f.get("goal") or "").strip()
    lang = str(f.get("language") or f.get("primary_language") or "").strip()
    ws = str(f.get("call_window_start") or "").strip()
    we = str(f.get("call_window_end") or "").strip()
    product = str(full.get("product") or f.get("product_name") or "").strip()
    parts = [f"{name} is {status}"]
    if product:
        parts.append(f"for {product}")
    if goal:
        parts.append(f"the goal is {goal}")
    if lang:
        parts.append(f"language {lang}")
    if ws and we:
        parts.append(f"calling window {ws} to {we}")
    summary = ". ".join(parts) + "."
    return {"ok": True, "id": cid, "name": name, "status": status,
            "campaign": full, "summary": summary}


def campaign_analytics(spoken: str) -> dict:
    """Per-campaign analytics (dialed/connected/answered/interested/qualified/voicemail) from
    GET /analytics?campaign_id=<resolved>. Real numbers only; resolves the spoken name first."""
    camp = resolve_campaign(spoken)
    if camp is None:
        avail = ", ".join(_camp_name(c) for c in list_campaigns()[:8] if _camp_name(c))
        return {"ok": False, "summary": (f"I couldn't find a campaign called {spoken}." +
                (f" You have: {avail}." if avail else ""))}
    cid = str(camp.get("id", ""))
    cname = _camp_name(camp) or spoken
    try:
        d = _get("/analytics", {"campaign_id": cid})
    except Exception:  # noqa: BLE001
        return {"ok": False, "summary": f"I couldn't pull the analytics for {cname} right now."}
    dialed = int(d.get("dialed", 0) or 0)
    connected = int(d.get("connected", 0) or 0)
    answered = int(d.get("answered", 0) or 0)
    interested = int(d.get("interested", 0) or 0)
    qualified = int(d.get("qualified", 0) or 0)
    vm = int(d.get("voicemail", 0) or 0)
    return {"ok": True, "stats": d,
            "summary": (f"For {cname}: {dialed} dialed, {connected} connected, {answered} answered, "
                        f"{interested} interested, {qualified} qualified, and {vm} went to voicemail.")}


def resolve_campaign(spoken: str) -> dict | None:
    """Best-effort match of a spoken campaign name to a stored campaign. Returns the campaign dict or
    None. Matching is forgiving: exact id, exact name (ci), then substring/word-overlap on the name."""
    q = (spoken or "").strip().lower()
    if not q:
        return None
    camps = list_campaigns()
    if not camps:
        return None
    # exact id
    for c in camps:
        if str(c.get("id", "")).lower() == q:
            return c
    # exact name (case-insensitive)
    for c in camps:
        if _camp_name(c).lower() == q:
            return c
    # substring either direction
    for c in camps:
        n = _camp_name(c).lower()
        if n and (q in n or n in q):
            return c
    # word-overlap (drop trivial words/numbers like "the", version digits)
    qwords = {w for w in re.split(r"[^a-z0-9]+", q) if w and w not in ("the", "a", "campaign")}
    best, best_score = None, 0
    for c in camps:
        nwords = {w for w in re.split(r"[^a-z0-9]+", _camp_name(c).lower()) if w}
        score = len(qwords & nwords)
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= 1 else None


# ───────────────────────── safe reads (no extra PIN) ───────────────────────────
def _lead_temp_score(x: dict) -> int:
    try:
        return int(x.get("score", 0) or 0)
    except Exception:  # noqa: BLE001
        return 0


def lead_counts(campaign: str = "") -> dict:
    """Real lead counts (total + hot/warm/cold by score). Stored leads are tenant-wide (not per
    campaign in this data model), so `campaign` is accepted for phrasing but the counts are the
    tenant's lead pool. score>=70 hot, 40-69 warm, <40 cold (mirrors panel temperature)."""
    try:
        d = _get("/leads")
        leads = list(d.get("leads", []) or [])
    except Exception:  # noqa: BLE001
        return {"ok": False, "summary": "I couldn't pull the lead numbers right now."}
    total = len(leads)
    hot = sum(1 for x in leads if _lead_temp_score(x) >= 70)
    warm = sum(1 for x in leads if 40 <= _lead_temp_score(x) < 70)
    cold = sum(1 for x in leads if _lead_temp_score(x) < 40)
    return {"ok": True, "total": total, "hot": hot, "warm": warm, "cold": cold,
            "leads": leads,
            "summary": (f"You have {total} leads total — {hot} hot, {warm} warm, and {cold} cold."
                        if total else "You don't have any leads stored yet.")}


def recent_calls(limit: int = 5) -> dict:
    """A short spoken summary of the most recent calls (name + outcome)."""
    try:
        d = _get("/calls", {"limit": max(1, min(int(limit), 20))})
        calls = list(d.get("calls", []) or [])
    except Exception:  # noqa: BLE001
        return {"ok": False, "summary": "I couldn't pull the recent calls right now."}
    if not calls:
        return {"ok": True, "summary": "There are no recent calls yet."}
    parts = []
    for c in calls[:limit]:
        nm = str(c.get("name") or c.get("num") or "a lead").strip()[:24]
        out = str(c.get("outcome") or c.get("status") or "").replace("_", " ") or "no result"
        parts.append(f"{nm}: {out}")
    return {"ok": True, "summary": "Recent calls — " + "; ".join(parts) + ".", "calls": calls}


def analytics() -> dict:
    """Spoken analytics summary from /stats (totals, answered, voicemail)."""
    try:
        d = _get("/stats")
    except Exception:  # noqa: BLE001
        return {"ok": False, "summary": "I couldn't pull the analytics right now."}
    total = int(d.get("total", 0) or 0)
    answered = int(d.get("answered", 0) or 0)
    vm = int(d.get("voicemail", 0) or 0)
    camps = int(d.get("campaigns", 0) or 0)
    return {"ok": True, "stats": d,
            "summary": (f"Across {camps} campaigns you've made {total} calls — "
                        f"{answered} answered and {vm} went to voicemail.")}


def wallet_status() -> dict:
    """Spoken wallet/balance summary from /wallet."""
    try:
        d = _get("/wallet")
    except Exception:  # noqa: BLE001
        return {"ok": False, "summary": "I couldn't reach the wallet right now."}
    if not d.get("wallet_available", True) and "available" not in d:
        return {"ok": True, "summary": "The wallet isn't set up yet."}
    avail = d.get("available", d.get("balance", 0))
    cur = d.get("currency", "INR")
    plan = d.get("plan", "")
    sign = "rupees" if cur == "INR" else cur
    plan_txt = f" on your {plan} plan" if plan else ""
    return {"ok": True, "wallet": d,
            "summary": f"Your balance is {avail} {sign}{plan_txt}."}


# ───────────────────────── run_campaign (the PROVEN dial path) ──────────────────
_SEGMENT_TEMP = {"hot": "hot", "warm": "warm", "cold": "cold"}


def resolve_audience(segment: str, count: int) -> list[dict]:
    """Resolve which lead rows to dial: read /leads, filter by segment (hot/warm/cold/all), take the
    first `count` (count<=0 -> all). Returns lead dicts (id/name/phone/score)."""
    try:
        d = _get("/leads")
        leads = list(d.get("leads", []) or [])
    except Exception:  # noqa: BLE001
        return []
    seg = (segment or "all").strip().lower()
    if seg in ("hot",):
        rows = [x for x in leads if _lead_temp_score(x) >= 70]
    elif seg in ("warm",):
        rows = [x for x in leads if 40 <= _lead_temp_score(x) < 70]
    elif seg in ("cold",):
        rows = [x for x in leads if _lead_temp_score(x) < 40]
    else:  # all / everyone / everybody / corporates / free-text / unknown -> the whole pool (NEVER silent 0)
        rows = list(leads)
    # highest score first so a small count dials the best leads
    rows = sorted(rows, key=_lead_temp_score, reverse=True)
    if count and count > 0:
        rows = rows[:count]
    return rows


def run_campaign(campaign: str, segment: str = "all", count: int = 0) -> dict:
    """THE DIAL ACTION. Resolves the campaign + audience, then POSTs to /run (the proven path that
    actually rings phones — the same route the panel Run button uses). The agent MUST have PIN-verified
    and read back a confirmation BEFORE calling this. Returns a spoken-friendly result dict.

    Mapping to /run: campaign_id=<resolved>, lead_ids=<resolved ids> (preview==dials, count honored).
    If the audience can't be resolved to explicit ids (e.g. no scores), falls back to source_mode/temps."""
    camp = resolve_campaign(campaign)
    if camp is None:
        return {"ok": False, "summary": (f"I couldn't find a campaign called {campaign}. "
                                         "Which campaign would you like to run?")}
    cid = str(camp.get("id", ""))
    cname = _camp_name(camp) or campaign
    seg = (segment or "all").strip().lower()
    rows = resolve_audience(seg, count)
    if not rows:
        return {"ok": False, "summary": (f"I didn't find any {seg if seg!='all' else ''} leads to call "
                                         f"for {cname}. Want me to try a different group?")}
    lead_ids = [str(x.get("id")) for x in rows if x.get("id")]
    form: dict = {"campaign_id": cid, "force": "1"}
    if lead_ids:
        form["lead_ids"] = ",".join(lead_ids)
        form["source_mode"] = "manual"
    else:
        # fallback: temperature/all source_mode (no explicit ids)
        if seg in ("hot", "warm", "cold"):
            form["source_mode"] = "temperature"
            form["temps"] = seg
        else:
            form["source_mode"] = "all"
            form["use_stored"] = "1"
    try:
        res = _post_form("/run", form)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "summary": "I couldn't start the campaign — the calling engine didn't respond.",
                "error": type(exc).__name__}
    st = res.get("_status", 0)
    if st == 402:
        return {"ok": False, "summary": "I couldn't start it — the prepaid balance is exhausted. "
                                        "Please top up to run campaigns."}
    n = res.get("count", len(lead_ids))
    job = res.get("job_id", "")
    if res.get("queued_out_of_window"):
        return {"ok": True, "summary": (f"{cname} is queued — it's outside calling hours, so {n} "
                                        "leads will start dialing when the window opens."),
                "job_id": res.get("job_id", ""), "count": n}
    if not job and st not in (200, 202):
        return {"ok": False, "summary": "I couldn't start the campaign just now — please try again."}
    # Honest read-out: speak ONLY after /run returned a job; include the real count.
    seg_txt = "" if seg in ("all", "everyone", "everybody") else f"{seg} "
    is_are = "is" if n == 1 else "are"
    return {"ok": True, "job_id": job, "count": n,
            "phones": [str(x.get("phone") or x.get("num") or "") for x in rows][:n],
            "summary": (f"Done — I've started the run for {cname}. {n} {seg_txt}"
                        f"lead{'s' if n != 1 else ''} {is_are} dialing now; they'll start ringing in a few seconds.")}


# ═══════════════════════════════════════════════════════════════════════════════
# CUSTOMER (sales) MODE additions (BUILD #5). All read-only-over-HTTP against the
# SAME live caller.py the panel uses; never import/edit caller.py/agent.py. Every
# function NEVER raises — returns a safe value/spoken-friendly dict on any error.
# ═══════════════════════════════════════════════════════════════════════════════
def _norm_phone(phone: str) -> str:
    """Match caller.py norm(): digits-only -> +91XXXXXXXXXX (drop leading 0, add 91 for
    a bare 10-digit). Used to reconcile the SIP caller-id against stored call/lead phones."""
    import re as _re
    d = _re.sub(r"\D", "", phone or "")
    if d.startswith("0"):
        d = d[1:]
    if len(d) == 10:
        d = "91" + d
    return ("+" + d) if len(d) >= 11 else ""


def _digits(phone: str) -> str:
    import re as _re
    return _re.sub(r"\D", "", phone or "")


def resolve_contact_by_phone(phone: str) -> dict:
    """Returning-caller link over HTTP (mirrors caller._resolve_contact_by_phone, but read-only
    against /calls + /leads). Returns {name, campaign_id, campaign_name, tenant_id, is_known}.
    Most-recent CALL to this number wins (it carries campaign_id); falls back to a stored lead.
    NEVER raises."""
    out = {"name": "", "campaign_id": "", "campaign_name": "", "tenant_id": "", "is_known": False}
    key = _norm_phone(phone)
    if not key:
        return out
    # 1) most-recent call to this number (carries campaign_id + name)
    try:
        d = _get("/calls", {"limit": 1000})
        for c in (d.get("calls", []) or []):
            if _norm_phone(c.get("phone", "") or c.get("num", "")) == key:
                out["name"] = c.get("name", "") or out["name"]
                out["campaign_id"] = c.get("campaign_id", "") or out["campaign_id"]
                out["campaign_name"] = c.get("campaign_name", "") or out["campaign_name"]
                out["tenant_id"] = c.get("tenant_id", "") or out["tenant_id"]
                out["is_known"] = True
                break
    except Exception:  # noqa: BLE001
        pass
    # 2) fall back to a stored lead (name only; leads have no campaign in this data model)
    if not out["name"]:
        try:
            d = _get("/leads")
            for x in (d.get("leads", []) or []):
                if _norm_phone(x.get("phone", "")) == key:
                    out["name"] = x.get("name", "") or out["name"]
                    out["tenant_id"] = out["tenant_id"] or x.get("tenant_id", "")
                    out["is_known"] = True
                    break
        except Exception:  # noqa: BLE001
            pass
    return out


def campaign_fields(spoken_or_id: str) -> dict:
    """Resolve a spoken name / id to its FULL campaign `fields` dict (the same shape
    prompt.build_system_prompt expects) by reading GET /campaigns/{id}. Returns {} if it
    can't resolve. NEVER raises."""
    try:
        camp = resolve_campaign(spoken_or_id)
        if camp is None:
            return {}
        cid = str(camp.get("id", ""))
        if not cid:
            return {}
        d = _get(f"/campaigns/{cid}")
        full = (d.get("campaign") or d) if isinstance(d, dict) else {}
        f = dict(full.get("fields", {}) or {})
        # stamp id/name so the caller (customer agent) can attach the lead later
        f.setdefault("_campaign_id", cid)
        f.setdefault("_campaign_name", _camp_name(full) or _camp_name(camp))
        return f
    except Exception:  # noqa: BLE001
        return {}


def active_campaigns() -> list[dict]:
    """The campaigns a NEW inbound caller could be calling about — those that are 'active' OR
    'ready' (i.e. live enough to take inbound interest). Returns [{id, name, status}]. Falls back
    to ALL campaigns if none are flagged active/ready (never leave a caller with zero options).
    NEVER raises."""
    camps = list_campaigns()
    if not camps:
        return []
    act = []
    for c in camps:
        st = str(c.get("status") or "").strip().lower()
        if st in ("active", "running", "ready", "live", "on"):
            act.append({"id": str(c.get("id", "")), "name": _camp_name(c) or "(unnamed)", "status": st})
    if not act:  # nothing flagged -> offer the whole set so a new caller is never stranded
        act = [{"id": str(c.get("id", "")), "name": _camp_name(c) or "(unnamed)",
                "status": str(c.get("status") or "")} for c in camps]
    return act


def create_lead(name: str, phone: str, campaign_id: str = "") -> dict:
    """Create/refresh a lead for an inbound CUSTOMER caller so the sale is visible in the panel.
    POSTs to /leads (the same route the panel 'Add leads' uses) with a 'name,phone' line. Idempotent
    server-side (de-dups on phone within the tenant). Returns {ok, added}. NEVER raises.

    NOTE: caller.py's /leads stores tenant-wide leads (no campaign column), so campaign_id is recorded
    only for the spoken/audit context here; the lead row links to the tenant. The CALL record (written
    by the inbound run) is what carries campaign_id for the next returning-caller resolution."""
    ph = _norm_phone(phone)
    if not ph:
        return {"ok": False, "added": 0, "summary": "no_phone"}
    nm = (name or "").strip() or "Inbound caller"
    line = f"{nm},{ph}"
    try:
        res = _post_form("/leads", {"leads": line})
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "added": 0, "error": type(exc).__name__}
    added = int(res.get("added", 0) or 0)
    return {"ok": True, "added": added, "phone": ph, "name": nm,
            "summary": ("saved as a new lead" if added else "already on file")}


def test_call(name: str, phone: str, campaign_id: str = "") -> dict:
    """Place ONE real outbound call to an explicit phone via the PROVEN /run dial path — used by the
    manager's `test_call_me` tool so the founder's own verified number RINGS. POSTs the phone as an
    ad-hoc lead line ('name,phone') + a campaign + force=1 (so it dials immediately, outside-window
    safe). Returns a spoken-friendly result. NEVER raises. SAFETY: this is the SAME /run route the
    panel Run button uses — no new dial code; it just dispatches one lead."""
    ph = _norm_phone(phone)
    if not ph:
        return {"ok": False, "summary": "I don't have a verified number on file to ring you back on."}
    cid = (campaign_id or "").strip()
    if not cid:
        # pick the first active/ready campaign so the test call has a brain
        acts = active_campaigns()
        cid = acts[0]["id"] if acts else ""
    if not cid:
        return {"ok": False, "summary": "I couldn't find a campaign to place the test call with."}
    nm = (name or "").strip() or "Manager"
    form = {"campaign_id": cid, "leads": f"{nm},{ph}", "force": "1"}
    try:
        res = _post_form("/run", form)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "summary": "I couldn't place the test call — the calling engine didn't respond.",
                "error": type(exc).__name__}
    st = res.get("_status", 0)
    if st == 402:
        return {"ok": False, "summary": "I couldn't place the test call — the prepaid balance is exhausted."}
    job = res.get("job_id", "")
    n = res.get("count", 0)
    if not job and st not in (200, 202):
        return {"ok": False, "summary": "I couldn't place the test call just now — please try again."}
    return {"ok": True, "job_id": job, "count": n, "phone": ph,
            "summary": "Done — I'm ringing your phone now. It should start ringing in a few seconds."}
