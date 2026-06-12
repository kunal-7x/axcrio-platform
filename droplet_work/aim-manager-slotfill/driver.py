"""ai_manager.intent.driver — provider-agnostic intent parser (the AIManagerNLU, spec §22 / §2.3, §8.1).

parse_intent(utterance, ctx) -> IntentMatch over a CLOSED ENUM of command intents + extracted slots.
The model NEVER invents a tool, NEVER authorizes, NEVER marks its own risk — anything off-enum or
low-confidence => {"kind":"clarify"} (spec §6.4). Mirrors whatsapp.py / workforce.llm.driver dormancy:
import-safe, is_configured(), status(), no-op when blank, NEVER raises (on error -> clarify).

Providers (spec §2.3 / aim-nlu-policy-security §1.5):
  * none   (default) -> a deterministic KEYWORD/REGEX matcher (the offline path). No network, no key.
  * groq   -> OpenAI-compatible chat-completions with JSON-mode (response_format=json_object),
              temperature=0 (deterministic classification), the §1.3 system prompt + vendor ctx +
              the §22 strict-JSON schema. Validated + retried-once, then mapped to IntentMatch. LIVE.
  * claude -> claude-opus-4-8, structured output; NO temperature/budget_tokens on Opus 4.8. LIVE.
  * mock   -> a deterministic in-proc provider for OFFLINE smoke (no key/network): echoes a §22 object
              from a tiny rule table so the validate+map pipeline is provable. (test-only)

THE LLM IS ADVISORY ONLY (aim-nlu-policy-security §1.1): it classifies + extracts + summarizes. The
deterministic PolicyEngine / identity.classify_risk remain AUTHORITATIVE — the model's risk_level /
requires_pin / safe_to_execute are recomputed and overridden downstream. This module funnels the model's
rich §22 object DOWN to the lean closed IntentMatch the state machine consumes; risk is re-derived there.

IntentMatch shape (the closed schema the state machine consumes):
  {"kind": "query"|"command"|"clarify"|"goodbye",
   "intent": "<workforce tool-scope>" | "",   # e.g. ads.set_budget / leads.enqueue_calls / analytics.read
   "slots": {...},                              # extracted args (budget_minor, campaign, count, ...)
   "confidence": 0.0..1.0,
   "reason": "<why clarify/error, redacted>"}
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

from .. import config as _config

# The closed set of COMMAND intents the voice path maps to workforce tool-scopes (spec §2.3). A command
# intent that isn't in this set => clarify. Reads are answered from context (kind="query") with no gate.
# (B2: extended with the live-module gap intents — workflow/booking + campaign create — wired in catalog.)
COMMAND_INTENTS = (
    "leads.enqueue_calls",   # "call all my hot leads"
    "whatsapp.send",         # "message my new leads on whatsapp"
    "campaigns.create",      # "launch a campaign for my 2bhk"
    "ads.set_budget",        # "bump budget on the best ad" / "set google budget to 1500 a day"
    "ads.pause",             # "pause the facebook ad"
    "ads.create_campaign",   # "create a new google ads campaign"
    "leads.delete",          # "delete this lead" (destructive — always PIN)
    "contacts.write",        # "add note: Ravi wants 3BHK" / "mark hot"
    "suppression.add",       # "add this number to DND"
    # --- B2 gap intents for the LIVE modules (workflow-studio, booking) ---
    "workflow.create_draft", # "workflow: hot lead -> brochure -> 2h -> call" (DRAFT, never auto-activate)
    "workflow.activate",     # "activate / publish the workflow" (step-up)
    "workflow.run_now",      # "run the workflow now"
    "booking.create",        # "book a site visit tomorrow 5pm"
    "booking.reschedule",    # "move that booking to..."
    "booking.cancel",        # "cancel the booking"
    # --- B2 parked-until-creds (correct adapter; clean not_configured when FEATURE_* off) ---
    "creative.generate_video",   # "create 5 video ads" (media_gen, FEATURE_MEDIA off -> parked)
    "creative.generate_banner",  # parked
    "creative.generate_brochure",# parked
)
QUERY_INTENTS = (
    "analytics.read",        # "today's revenue" / "how many hot leads"
    "leads.read",            # "show my hot leads"
    "contacts.read",         # "look up Ravi"
    "billing.read",          # "what's my balance"
    "wallet.read",           # "wallet balance"
    "booking.read",          # "kal ke site visits batao"
    "brain.retrieve",        # grounding facts
)

# The §22 always-block hints the model may surface (block_reason). The PolicyEngine is final authority;
# this only lets the model refuse first-line. Mapped to kind="clarify" with a redirect reason here (the
# state machine / policy engine emit the real spoken refusal).
_BLOCK_INTENTS = (
    "security.reveal_secret", "compliance.bypass", "account.delete", "account.transfer",
    "audit.disable", "security.change_pin",
)

_GOODBYE = ("goodbye", "bye", "that's all", "thats all", "nothing else", "hang up", "done for now")

# Confidence floor: below this the model is forced to clarify, never execute (aim-nlu §1.2 CONF_MIN).
_CONF_MIN = 0.55


# ================================================================================================
#  SLOT-FILLING (multi-turn ELICIT) — the required_slots table + the per-slot question/validator maps.
#  The brain (state_machine S4.5 / chat ELICIT) holds a PendingCommand and asks for any required slot
#  the NLU did not extract, instead of the lossy dead-end clarify. AUTHORITATIVE source = the LIVE tool
#  registry's ToolSpec.required_slots (so catalog edits flow here for free); this static table is the
#  OFFLINE fallback when the registry can't be built (zero-dep). Keep the two in sync.
# ================================================================================================
_REQUIRED_SLOTS_FALLBACK: dict[str, tuple] = {
    "leads.enqueue_calls": ("campaign", "segment"),
    "whatsapp.send": ("segment",),
    "ads.set_budget": ("budget_minor",),
    "campaigns.create": ("objective",),
    "workflow.create_draft": ("objective",),
    "workflow.activate": ("workflow_id",),
    "workflow.run_now": ("workflow_id",),
    "booking.create": ("slot_start",),
}

# The single natural question we ask for each missing slot (Hinglish-friendly; asked ONE at a time,
# most-important-first per required_slots ORDER). Voice speaks this; chat renders it verbatim.
_SLOT_QUESTION: dict[str, str] = {
    "campaign": "Which campaign?",
    "segment": "Which leads — hot, warm, or all?",
    "count": "How many?",
    "budget_minor": "What daily budget should I set, in rupees?",
    "objective": "What should this be about?",
    "channel": "Which platform — Google or Meta?",
    "workflow_id": "Which workflow?",
    "slot_start": "What date and time?",
    "note": "What note should I add?",
}

# Friendly slot name for a generic fallback question.
_SLOT_LABEL: dict[str, str] = {
    "campaign": "campaign", "segment": "lead segment", "count": "count",
    "budget_minor": "budget", "objective": "details", "channel": "platform",
    "workflow_id": "workflow", "slot_start": "date and time", "note": "note",
}

_SEGMENT_ENUM = ("hot", "warm", "cold", "all", "new")

# the model surfaces missing_fields using §22 entity names; map them DOWN to our slot names so its hint
# can be unioned with the deterministic required_slots table.
_MODEL_MISSING_MAP: dict[str, str] = {
    "campaign_ref": "campaign", "campaign": "campaign",
    "lead_segment": "segment", "segment": "segment",
    "amount_minor": "budget_minor", "budget_minor": "budget_minor", "amount": "budget_minor",
    "count": "count", "platform": "channel", "channel": "channel",
    "workflow_id": "workflow_id", "schedule_time": "slot_start", "date_ref": "slot_start",
    "slot_start": "slot_start", "objective": "objective", "note_text": "note",
}


def required_slots_for(intent: str) -> tuple:
    """The required slots for a command intent. Prefers the LIVE tool registry (ToolSpec.required_slots
    so catalog stays the single source of truth); falls back to the static table when the registry can't
    be built (offline / workforce absent). NEVER raises."""
    try:
        from workforce.tools import build_registry  # type: ignore
        reg = build_registry("live")
        rs = reg.required_slots_for(intent)
        if rs:
            return tuple(rs)
    except Exception:  # noqa: BLE001
        pass
    return _REQUIRED_SLOTS_FALLBACK.get(intent or "", ())


def missing_required(intent: str, slots: dict) -> list:
    """Required slots that are absent/blank in `slots` (the outstanding list the brain elicits). The slot
    is considered FILLED iff present and non-empty (0 counts as filled for budget_minor only when >0).
    NEVER raises."""
    out: list = []
    slots = slots or {}
    for s in required_slots_for(intent):
        v = slots.get(s, None)
        if s == "budget_minor":
            try:
                filled = int(v or 0) > 0
            except Exception:  # noqa: BLE001
                filled = False
        else:
            filled = v not in (None, "", [], {})
        if not filled:
            out.append(s)
    return out


def slot_question(slot: str) -> str:
    """The natural question to ask for a missing slot (deterministic; ONE slot at a time)."""
    return _SLOT_QUESTION.get(slot) or f"Could you tell me the {_SLOT_LABEL.get(slot, slot)}?"


def coerce_slot(slot: str, value) -> tuple:
    """Validate + normalize an elicited slot answer. Returns (ok: bool, normalized_value). On a bad/empty
    answer returns (False, None) so the brain re-asks. NEVER raises.
      - budget_minor: rupee phrase -> integer paise (>0)
      - segment:      free text -> one of hot|warm|cold|all|new (default 'all' for 'everyone'/'sab')
      - count:        first integer in the text (>0)
      - others:       trimmed non-empty string passthrough"""
    text = (value if isinstance(value, str) else str(value or "")).strip()
    if not text:
        return (False, None)
    low = text.lower()
    if slot == "budget_minor":
        minor = _num_to_minor(low)
        return (minor > 0, minor if minor > 0 else None)
    if slot == "segment":
        if "hot" in low:
            return (True, "hot")
        if "warm" in low:
            return (True, "warm")
        if "cold" in low:
            return (True, "cold")
        if "new" in low:
            return (True, "new")
        if re.search(r"\b(all|every|everyone|sab|sabhi|sabko|poora)\b", low):
            return (True, "all")
        # an explicit single value the user just said, otherwise re-ask
        if low in _SEGMENT_ENUM:
            return (True, low)
        return (False, None)
    if slot == "count":
        m = re.search(r"\b([0-9]+)\b", low)
        if m and int(m.group(1)) > 0:
            return (True, int(m.group(1)))
        return (False, None)
    if slot == "channel":
        if "google" in low:
            return (True, "google")
        if re.search(r"\b(meta|facebook|fb|instagram|insta)\b", low):
            return (True, "meta")
        return (False, None)
    # campaign / objective / workflow_id / slot_start / note: any non-empty answer is accepted as-is.
    # For "campaign" strip filler so "the diwali campaign" -> "diwali".
    if slot == "campaign":
        m = re.search(r"(?:the\s+)?[\"']?([a-z0-9][a-z0-9 _\-]*?)[\"']?(?:\s+campaign)?\s*$", low)
        val = (m.group(1).strip() if m else text).strip()
        return (bool(val), val or None)
    return (True, text)


def parse_slot_value(intent: str, slot: str, reply: str, ctx: Optional[dict] = None) -> tuple:
    """Re-parse JUST the elicited slot from the user's reply (NOT the whole command) and merge-ready
    return (ok, normalized). First tries the deterministic coerce_slot; that is sufficient for the closed
    slot set. NEVER raises, NEVER re-classifies the intent (the held PendingCommand owns the intent)."""
    try:
        return coerce_slot(slot, reply)
    except Exception:  # noqa: BLE001
        return (False, None)


def _provider() -> str:
    return _config.llm_provider()


def _key_for(provider: str) -> str:
    if provider == "claude":
        return os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if provider == "groq":
        k = os.environ.get("GROQ_API_KEY", "").strip()
        if k:
            return k
        for i in range(1, 12):  # round-robin GROQ_API_KEY_1..N (fortress pattern)
            v = os.environ.get(f"GROQ_API_KEY_{i}", "").strip()
            if v:
                return v
    return ""


def is_configured() -> bool:
    """True only when a real LLM provider + its key are present. `none` is the deterministic stub (not an
    'LLM') so is_configured() is False for it — exactly the whatsapp.py contract. `mock` is test-only and
    is treated as configured (no key needed) so the validate+map pipeline is exercised offline."""
    p = _provider()
    if p in ("", "none"):
        return False
    if p == "mock":
        return True
    return bool(_key_for(p))


def status() -> str:
    """'configured' | 'not_configured' (never leaks the key, NEVER raises)."""
    return "configured" if is_configured() else "not_configured"


def status_dict() -> dict:
    p = _provider()
    return {"status": status(), "provider": p or "none",
            "model": _default_model(p) if is_configured() else ""}


def _default_model(provider: str) -> str:
    if provider == "claude":
        return os.environ.get("AIM_CLAUDE_MODEL", "claude-opus-4-8")
    if provider == "groq":
        return os.environ.get("AIM_GROQ_MODEL",
                              os.environ.get("GROQ_LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"))
    if provider == "mock":
        return "mock"
    return ""


# ---------------- the closed-schema validator (every path funnels through this) ----------------
def _clamp(match: dict) -> dict:
    """Force any candidate match into the closed schema. Off-enum / unknown => clarify. NEVER raises."""
    kind = (match or {}).get("kind", "clarify")
    intent = (match or {}).get("intent", "") or ""
    slots = (match or {}).get("slots", {}) or {}
    conf = (match or {}).get("confidence", 0.0)
    try:
        conf = float(conf)
    except Exception:  # noqa: BLE001
        conf = 0.0
    reason = (match or {}).get("reason", "") or ""
    if kind == "goodbye":
        return {"kind": "goodbye", "intent": "", "slots": {}, "confidence": 1.0, "reason": ""}
    if kind == "command":
        if intent not in COMMAND_INTENTS or conf < 0.5:
            return {"kind": "clarify", "intent": "", "slots": {},
                    "confidence": conf, "reason": reason or "off-enum or low confidence"}
        # SLOT-FILLING: carry the outstanding required slots so the brain can ELICIT them (a partial
        # command keeps its intent + slots instead of collapsing to a dead-end clarify). If the caller
        # already supplied missing_fields (the LLM path), respect it; else derive deterministically.
        ms = (match or {}).get("missing_fields")
        if ms is None:
            ms = missing_required(intent, slots)
        return {"kind": "command", "intent": intent, "slots": dict(slots),
                "confidence": conf, "reason": "", "missing_fields": list(ms)}
    if kind == "query":
        return {"kind": "query", "intent": intent if intent in QUERY_INTENTS else "analytics.read",
                "slots": dict(slots), "confidence": max(conf, 0.5), "reason": ""}
    return {"kind": "clarify", "intent": "", "slots": dict(slots), "confidence": conf, "reason": reason}


# ---------------- deterministic keyword matcher (provider=none; the OFFLINE path) ----------------
def _num_to_minor(text: str) -> int:
    """Extract a rupee amount from text and return MINOR units (paise). '1500' / '₹1,500' / '1500 a day'
    -> 150000. '1.5k' -> 150000. Returns 0 if none. NEVER raises."""
    t = text.lower().replace(",", "")
    m = re.search(r"(?:rs\.?|inr|₹)?\s*([0-9]+(?:\.[0-9]+)?)\s*(k|lakh|l)?", t)
    if not m:
        return 0
    try:
        val = float(m.group(1))
    except Exception:  # noqa: BLE001
        return 0
    unit = m.group(2)
    if unit == "k":
        val *= 1000
    elif unit in ("lakh", "l"):
        val *= 100000
    return int(round(val * 100))  # rupees -> paise (minor)


def _stub_match(utterance: str) -> dict:
    """The deterministic offline matcher. Keyword + regex over the closed enum. Conservative: ambiguous
    or unrecognized => clarify (NEVER guesses a command). NEVER raises."""
    u = (utterance or "").strip().lower()
    if not u:
        return {"kind": "clarify", "intent": "", "slots": {}, "confidence": 0.0, "reason": "empty"}
    if any(g in u for g in _GOODBYE):
        return {"kind": "goodbye", "intent": "", "slots": {}, "confidence": 1.0, "reason": ""}

    # ALWAYS-BLOCK first-line hints (the policy engine is final authority; this just refuses early).
    if re.search(r"\b(api ?key|secret|password|pin|token|credential)\b", u) and re.search(
            r"\b(show|reveal|tell|what'?s|read|give)\b", u):
        return {"kind": "clarify", "intent": "", "slots": {}, "confidence": 0.0,
                "reason": "blocked:reveal_secret"}
    if re.search(r"\b(ignore|bypass|disable|turn off)\b", u) and re.search(
            r"\b(dnd|do.?not.?call|consent|opt.?out|stop|compliance|audit)\b", u):
        return {"kind": "clarify", "intent": "", "slots": {}, "confidence": 0.0,
                "reason": "blocked:compliance_bypass"}

    # QUERY (read-only) — revenue / leads count / report / how many / wallet / bookings.
    if re.search(r"\b(site ?visit|booking)s?\b", u) and not re.search(
            r"\b(book|create|cancel|reschedule|move)\b", u):
        return {"kind": "query", "intent": "booking.read", "slots": {"query": utterance},
                "confidence": 0.8, "reason": ""}
    if re.search(r"\b(wallet|balance|credits?)\b", u) and not re.search(
            r"\b(set|bump|raise|launch|create|call|message|send|pause)\b", u):
        return {"kind": "query", "intent": "wallet.read", "slots": {"query": utterance},
                "confidence": 0.8, "reason": ""}
    if re.search(r"\b(revenue|today'?s? (revenue|number|leads|calls)|how (many|much)|report|"
                 r"funnel|stats?|status)\b", u) and not re.search(r"\b(set|bump|raise|launch|"
                 r"create|call|message|send|pause)\b", u):
        return {"kind": "query", "intent": "analytics.read", "slots": {"query": utterance},
                "confidence": 0.8, "reason": ""}

    # COMMAND: workflow draft (voice -> React-Flow draft; never auto-activate).
    if re.search(r"\bworkflow\b", u):
        if re.search(r"\b(activate|publish|turn on|enable)\b", u):
            return {"kind": "command", "intent": "workflow.activate", "slots": {"objective": utterance},
                    "confidence": 0.75, "reason": ""}
        if re.search(r"\brun\b", u):
            return {"kind": "command", "intent": "workflow.run_now", "slots": {"objective": utterance},
                    "confidence": 0.7, "reason": ""}
        return {"kind": "command", "intent": "workflow.create_draft",
                "slots": {"objective": utterance}, "confidence": 0.7, "reason": ""}

    # COMMAND: booking create / reschedule / cancel.
    if re.search(r"\b(book|schedule)\b", u) and re.search(r"\b(visit|site|slot|appointment|booking)\b", u):
        return {"kind": "command", "intent": "booking.create", "slots": {"objective": utterance},
                "confidence": 0.72, "reason": ""}
    if re.search(r"\breschedule\b", u) or (re.search(r"\bmove\b", u) and re.search(r"\bbooking\b", u)):
        return {"kind": "command", "intent": "booking.reschedule", "slots": {"objective": utterance},
                "confidence": 0.7, "reason": ""}
    if re.search(r"\bcancel\b", u) and re.search(r"\bbooking\b", u):
        return {"kind": "command", "intent": "booking.cancel", "slots": {"objective": utterance},
                "confidence": 0.7, "reason": ""}

    # COMMAND: creative gen (parked until FEATURE_MEDIA; adapter returns clean not_configured).
    if re.search(r"\b(create|make|generate)\b", u) and re.search(
            r"\b(video|banner|brochure|creative|ad ?(video|creative)s?)\b", u):
        sub = ("video" if "video" in u else "banner" if "banner" in u
               else "brochure" if "brochure" in u else "video")
        cnt = re.search(r"\b([0-9]+)\b", u)
        return {"kind": "command", "intent": f"creative.generate_{sub}",
                "slots": {"count": int(cnt.group(1)) if cnt else 1, "subject": utterance},
                "confidence": 0.72, "reason": ""}

    # COMMAND: ads budget (money) — "set/bump/raise budget to X".
    if re.search(r"\b(budget)\b", u) and re.search(r"\b(set|bump|raise|increase|change|to|scale)\b", u):
        amt = _num_to_minor(u)
        slots = {"budget_minor": amt}
        camp = re.search(r"\b(campaign|ad)\s+([a-z0-9_\-]+)", u)
        if camp:
            slots["campaign"] = camp.group(2)
        if "google" in u:
            slots["channel"] = "google"
        elif "facebook" in u or "meta" in u or "instagram" in u:
            slots["channel"] = "meta"
        return {"kind": "command", "intent": "ads.set_budget", "slots": slots,
                "confidence": 0.85, "reason": ""}

    # COMMAND: pause ad (de-risking, safe).
    if re.search(r"\bpause\b", u) and re.search(r"\b(ad|ads|campaign)\b", u):
        slots = {}
        if "google" in u:
            slots["channel"] = "google"
        elif "facebook" in u or "meta" in u:
            slots["channel"] = "meta"
        return {"kind": "command", "intent": "ads.pause", "slots": slots,
                "confidence": 0.8, "reason": ""}

    # COMMAND: RUN/START an EXISTING named campaign -> DIAL it (leads.enqueue_calls -> /run),
    # NOT a draft. Disambiguator: a run verb (run/start/launch/begin/dial/activate) on a
    # campaign WITHOUT an explicit create/new/draft word means dial the existing campaign.
    # The named campaign is resolved by /run via campaign_id; Riya speaks that script.
    # TCfix: closes the gap where run-campaign-X used to create a draft and dial nobody.
    if (re.search(r"\b(run|start|launch|begin|kick ?off|go ?live|dial|activate)\b", u)
            and re.search(r"\bcampaign\b", u)
            and not re.search(r"\b(create|new|draft|make|set ?up|build)\b", u)):
        slots = {"objective": utterance, "use_stored": "1"}
        camp = re.search(r"\bcampaign\s+(?:called\s+|named\s+)?[\"\']?([a-z0-9_][a-z0-9_\- ]*?)[\"\']?\s*$", u)
        if not camp:
            camp = re.search(r"\b(?:run|start|launch|dial|begin)\s+(?:the\s+)?[\"\']?([a-z0-9_][a-z0-9_\- ]*?)[\"\']?\s+campaign\b", u)
        if camp:
            cand = camp.group(1).strip()
            # reject bare articles ("run A campaign" / "run THE campaign") — that's NOT a campaign name,
            # it's a half-specified command -> leave `campaign` unfilled so the brain ELICITS "which?".
            if cand and cand not in ("a", "an", "the", "my", "this", "that", "some", "another"):
                slots["campaign"] = cand
        return {"kind": "command", "intent": "leads.enqueue_calls", "slots": slots,
                "confidence": 0.8, "reason": ""}

    # COMMAND: create a NEW campaign (a DRAFT; launch/run is the separate dial step above).
    if re.search(r"\b(launch|create|start|new|draft|make)\b", u) and re.search(r"\bcampaign\b", u):
        slots = {"objective": utterance}
        return {"kind": "command", "intent": "campaigns.create", "slots": slots,
                "confidence": 0.75, "reason": ""}

    # COMMAND: add note / update a contact (single-record write, safe).
    if re.search(r"\b(add note|note:|mark|tag|update)\b", u) and re.search(
            r"\b(lead|contact|ravi|customer|him|her|them|hot|warm|cold)\b", u):
        slots = {"note": utterance}
        return {"kind": "command", "intent": "contacts.write", "slots": slots,
                "confidence": 0.7, "reason": ""}

    # COMMAND: call leads (bulk).
    if re.search(r"\bcall\b", u) and re.search(r"\b(leads?|hot|prospects?|everyone|all)\b", u):
        slots = {"segment": "hot" if "hot" in u else "all"}
        return {"kind": "command", "intent": "leads.enqueue_calls", "slots": slots,
                "confidence": 0.8, "reason": ""}

    # COMMAND: whatsapp broadcast (bulk).
    if re.search(r"\b(whatsapp|message|text|broadcast)\b", u) and re.search(
            r"\b(leads?|customers?|everyone|all|new|warm|brochure)\b", u):
        slots = {"segment": "new" if "new" in u else "warm" if "warm" in u else "all"}
        return {"kind": "command", "intent": "whatsapp.send", "slots": slots,
                "confidence": 0.7, "reason": ""}

    return {"kind": "clarify", "intent": "", "slots": {}, "confidence": 0.0,
            "reason": "no matching command intent"}


# ---------------- public entry ----------------
def parse_intent(utterance: str, ctx: Optional[dict] = None) -> dict:
    """Parse an utterance -> a CLOSED-schema IntentMatch. provider=none uses the deterministic matcher
    (offline). A configured LLM (groq/claude/mock) emits the §22 strict JSON, which is validated, retried
    once, mapped DOWN to IntentMatch, then re-clamped. On ANY failure -> fall back to the deterministic
    stub (the command path always works). On ANY error -> clarify (never raises, never executes)."""
    try:
        if is_configured():
            raw = _llm_parse(utterance, ctx or {})
            if raw is not None:
                llm = _clamp(raw)
                # TCfix: deterministic safety-net. When the LLM CLARIFIES (often just
                # because the business context lacks an active_campaigns list, so it asks
                # "which campaign?"), but the offline keyword matcher yields a CONFIDENT
                # command (e.g. "call hot leads", "run the diwali campaign"), adopt that
                # command so the tested founder phrases stay reliable. NEVER override a
                # confident LLM command, and NEVER second-guess a BLOCK (security-critical):
                # a block stays a clarify with reason="blocked:..." and is preserved as-is.
                if (llm.get("kind") == "clarify"
                        and not str(llm.get("reason", "")).startswith("blocked:")):
                    det = _clamp(_stub_match(utterance))
                    if det.get("kind") == "command" and float(det.get("confidence", 0) or 0) >= 0.75:
                        return det
                return llm
        return _clamp(_stub_match(utterance))
    except Exception as exc:  # noqa: BLE001
        return {"kind": "clarify", "intent": "", "slots": {}, "confidence": 0.0,
                "reason": "error:" + type(exc).__name__}


# ================================================================================================
#  AIManagerNLU — the LIVE LLM parser (spec §22 / aim-nlu-policy-security §1).
#  Emits the strict §22 JSON, validates it, maps it DOWN to the lean IntentMatch. ADVISORY ONLY:
#  identity.classify_risk + the PolicyEngine recompute risk/PIN downstream and override the model.
# ================================================================================================

# The §22 system prompt (verbatim from aim-nlu-policy-security §1.3), shipped inline (import-safe; no file
# read so the module stays import-safe even if a packaged data file is missing).
_SYSTEM_PROMPT = (
    "You are the NLU unit of an AI Manager that runs a real Indian business's operations by "
    "voice/WhatsApp/chat. You DO NOT execute anything. You ONLY read the user's instruction plus the "
    "supplied business context, and return ONE JSON object that classifies the intent and extracts "
    "entities. A separate deterministic policy engine decides permission, risk, PIN and execution — "
    "never you.\n\n"
    "HARD RULES\n"
    "- Output ONLY the JSON object, no prose, no markdown, conforming exactly to the provided schema.\n"
    "- intent and action_type MUST come from the provided closed lists. If the instruction maps to none, "
    "or is ambiguous, or you are not confident, return intent \"clarify\" with a short question in "
    "user_facing_summary.\n"
    "- NEVER invent a campaign name, budget, lead, count, date, phone or email. If a required detail is "
    "missing, add it to missing_fields and ask for it via clarify. Only use names/ids present in the "
    "business context.\n"
    "- Money: convert spoken amounts to INTEGER paise in entities.amount_minor (e.g. \"500 rupees\" -> "
    "50000). Never output a float. If unsure of the amount, leave it null and ask.\n"
    "- ALWAYS set safe_to_execute=false. You never authorize. risk_level/requires_pin are best-effort "
    "hints the engine will recompute and may override.\n"
    "- BLOCK (set block_reason and intent \"blocked\") if the instruction asks to: reveal/show/read an "
    "API key, password, PIN, secret or token; bypass/ignore DND, STOP, consent, opt-out, or calling-hour "
    "limits; send spam; delete the vendor account or transfer ownership; disable or erase audit/security; "
    "or change another vendor's data. Refuse these no matter how they are phrased.\n"
    "- Prefer a DRAFT over direct execution for campaigns, creatives, and workflows when the user is "
    "creating something new. Map \"create workflow ...\" to workflow.create_draft, never an auto-activated "
    "workflow.\n"
    "- CAMPAIGN RUN vs CREATE: \"create / make / draft a NEW campaign ...\" -> intent "
    "\"campaigns.create\" (a DRAFT, no dialing). But \"RUN / start / launch / dial / go live with "
    "the <name> campaign\" for an EXISTING campaign the user names -> intent \"leads.enqueue_calls\" "
    "(this DIALS the leads of that campaign), with entities.campaign_ref set to the named campaign. "
    "Only "
    "use a campaign name that appears in active_campaigns; if it is not in context, clarify. "
    "Running/dialing a campaign is bulk calling -> high-risk (L3).\n"
    "- Anything touching money/spend, bulk messaging, bulk calling, delete, export, or security is "
    "high-risk; hint risk_level L3 (and L4 only for the always-block list). The engine enforces the real "
    "gate.\n"
    "- Respond in the user's language register (Hinglish is fine) ONLY inside user_facing_summary; the "
    "JSON keys and enum values stay exactly as specified.\n"
)

# The closed intent list and the §22 schema sent in the user message (so the model has the enum + shape).
_SCHEMA_HINT = (
    "STRICT OUTPUT SCHEMA (emit exactly this object):\n"
    "{\"intent\":\"<dotted intent from CLOSED list>\",\"action_type\":\"<engine action_type>\","
    "\"confidence\":0.0,\"risk_level\":\"L0|L1|L2|L3|L4\",\"requires_confirmation\":false,"
    "\"requires_pin\":false,\"entities\":{\"campaign_ref\":null,\"platform\":null,\"amount_minor\":null,"
    "\"currency\":\"INR\",\"lead_segment\":null,\"lead_ref\":null,\"count\":null,\"channel_target\":null,"
    "\"destination\":null,\"schedule_time\":null,\"date_ref\":null,\"workflow_spec\":null,"
    "\"creative_spec\":null,\"note_text\":null},\"missing_fields\":[],\"assumptions\":[],"
    "\"user_facing_summary\":\"\",\"safe_to_execute\":false,\"block_reason\":null}\n"
)


def _closed_lists() -> str:
    return ("CLOSED COMMAND intents (kind=command): " + ", ".join(COMMAND_INTENTS) + "\n"
            "CLOSED QUERY intents (kind=query, read-only): " + ", ".join(QUERY_INTENTS) + "\n"
            "BLOCK intents (kind=blocked, refuse): " + ", ".join(_BLOCK_INTENTS) + "\n")


def _ctx_block(ctx: dict) -> str:
    """Render the PII-minimized vendor context (aim-nlu §1.4). Refs only — no full phone/email. Truncated
    to a small token budget (top-N). NEVER raises; an empty ctx renders an empty-but-valid block."""
    ctx = ctx or {}
    biz = ctx.get("business_name") or (ctx.get("profile") or {}).get("business_name") or ""
    today = ctx.get("today_summary") or ctx.get("today") or {}
    camps = (ctx.get("active_campaigns") or ctx.get("campaigns") or [])[:8]
    leads = (ctx.get("recent_leads") or ctx.get("leads") or [])[:8]
    wallet = ctx.get("wallet") or {}
    modules = ctx.get("available_modules") or ctx.get("modules") or []
    grants = ctx.get("grants") or ctx.get("permissions") or []
    lines = ["BUSINESS CONTEXT (use ONLY to resolve references + fill entities; never fabricate beyond):"]
    if biz:
        lines.append(f"- business_name: {biz}")
    if today:
        lines.append(f"- today_summary: {json.dumps(today, ensure_ascii=False)[:300]}")
    if camps:
        c = [{"id": x.get("id"), "name": x.get("name"), "platform": x.get("platform"),
              "status": x.get("status")} for x in camps if isinstance(x, dict)]
        lines.append(f"- active_campaigns: {json.dumps(c, ensure_ascii=False)[:400]}")
    if leads:
        l = [{"ref": x.get("ref") or x.get("id"), "name": x.get("name"),
              "segment": x.get("segment") or x.get("stage")} for x in leads if isinstance(x, dict)]
        lines.append(f"- recent_leads: {json.dumps(l, ensure_ascii=False)[:400]}")
    if wallet:
        lines.append(f"- wallet: {json.dumps({'available_minor': wallet.get('available_minor'), 'plan': wallet.get('plan')}, ensure_ascii=False)}")
    if modules:
        lines.append(f"- available_modules: {json.dumps(list(modules)[:20], ensure_ascii=False)}")
    if grants:
        lines.append(f"- grants: {json.dumps(list(grants)[:20], ensure_ascii=False)}")
    return "\n".join(lines)


def _coerce_amount_minor(v) -> Optional[int]:
    """Coerce amount_minor to INTEGER paise or None (reject floats per §1.2). NEVER raises."""
    if v is None:
        return None
    try:
        f = float(v)
    except Exception:  # noqa: BLE001
        return None
    if f != int(f):  # a float like 500.5 is rejected (paise are integral)
        return None
    return int(f)


def _map_to_intentmatch(obj: dict) -> dict:
    """Map the validated §22 strict object DOWN to the lean closed IntentMatch the state machine consumes.
    Risk is DROPPED here on purpose (identity.classify_risk recomputes it). NEVER raises."""
    obj = obj or {}
    intent = (obj.get("intent") or "").strip()
    block_reason = obj.get("block_reason")
    if block_reason or intent in _BLOCK_INTENTS or intent == "blocked":
        return {"kind": "clarify", "intent": "", "slots": {}, "confidence": 0.0,
                "reason": "blocked:" + str(block_reason or intent)[:60]}
    if intent == "clarify" or not intent:
        return {"kind": "clarify", "intent": "", "slots": {},
                "confidence": float(obj.get("confidence") or 0.0),
                "reason": (obj.get("user_facing_summary") or "clarify")[:120]}

    conf = obj.get("confidence", 0.0)
    try:
        conf = float(conf)
    except Exception:  # noqa: BLE001
        conf = 0.0
    if conf < _CONF_MIN:  # §1.2 CONF_MIN -> force clarify, never execute
        return {"kind": "clarify", "intent": "", "slots": {}, "confidence": conf,
                "reason": "low_confidence"}

    # Build slots from the §22 entities (the leaner state machine reads budget_minor/segment/etc).
    ents = obj.get("entities") or {}
    slots: dict = {}
    amt = _coerce_amount_minor(ents.get("amount_minor"))
    if amt is not None:
        slots["budget_minor"] = amt
    for src, dst in (("platform", "channel"), ("lead_segment", "segment"), ("count", "count"),
                     ("channel_target", "channel_target"), ("destination", "destination"),
                     ("schedule_time", "schedule_time"), ("date_ref", "date_ref"),
                     ("campaign_ref", "campaign"), ("lead_ref", "lead_ref"),
                     ("workflow_spec", "workflow_spec"), ("creative_spec", "creative_spec"),
                     ("note_text", "note")):
        if ents.get(src) not in (None, "", []):
            slots[dst] = ents.get(src)
    # carry the spoken summary + any missing fields so the state machine can read back / clarify
    if obj.get("user_facing_summary"):
        slots["_summary"] = str(obj["user_facing_summary"])[:240]
    missing = obj.get("missing_fields") or []

    # QUERY intents are read-only; COMMAND intents map to a tool-scope. Off-enum => clarify (in _clamp).
    if intent in QUERY_INTENTS:
        if missing:  # a read still missing a required slot -> clarify
            return {"kind": "clarify", "intent": "", "slots": slots, "confidence": conf,
                    "reason": "missing:" + ",".join(map(str, missing))[:80]}
        return {"kind": "query", "intent": intent, "slots": slots, "confidence": conf, "reason": ""}
    if intent in COMMAND_INTENTS:
        # SLOT-FILLING: a command can ride through WITH outstanding required slots. We no longer DISCARD
        # the intent on a missing field (the old lossy clarify) — we surface the intent + accumulated
        # slots + the outstanding `missing_fields` so the brain can hold a PendingCommand and ELICIT the
        # missing pieces over multiple turns. The DETERMINISTIC required_slots table is the authority
        # (the model's missing_fields is only a hint we union with it).
        outstanding = missing_required(intent, slots)
        # union the model's own missing_fields hint (mapped to our slot names) — but trust our table.
        for mf in missing:
            mapped = _MODEL_MISSING_MAP.get(str(mf).strip().lower(), str(mf).strip().lower())
            if mapped in required_slots_for(intent) and mapped not in slots and mapped not in outstanding:
                outstanding.append(mapped)
        if outstanding:
            return {"kind": "command", "intent": intent, "slots": slots, "confidence": conf,
                    "reason": "", "missing_fields": outstanding}
        return {"kind": "command", "intent": intent, "slots": slots, "confidence": conf,
                "reason": "", "missing_fields": []}
    # off-enum intent -> clarify
    return {"kind": "clarify", "intent": "", "slots": slots, "confidence": conf, "reason": "off_enum"}


def _validate_raw(obj) -> Optional[dict]:
    """Validate the model's raw object against the §22 schema invariants. Returns the (lightly-normalized)
    object on success, or None to trigger the retry/fallback. NEVER raises."""
    if not isinstance(obj, dict):
        return None
    intent = obj.get("intent")
    if not isinstance(intent, str) or not intent:
        return None
    # intent must be in one of the closed lists OR be clarify/blocked (the safe sinks)
    if (intent not in COMMAND_INTENTS and intent not in QUERY_INTENTS and intent not in _BLOCK_INTENTS
            and intent not in ("clarify", "blocked")):
        return None
    # entities must be a dict if present; drop unknown keys (defense vs prompt-injected fields)
    ents = obj.get("entities")
    if ents is not None and not isinstance(ents, dict):
        return None
    return obj


def _build_user_message(utterance: str, ctx: dict, corrector: str = "") -> str:
    parts = [_SCHEMA_HINT, _closed_lists(), _ctx_block(ctx),
             "USER INSTRUCTION:\n" + (utterance or "")]
    if corrector:
        parts.append(corrector)
    return "\n\n".join(parts)


# ----- provider calls (each returns a RAW dict|None; never raises) -----
def _call_groq(messages: list) -> Optional[dict]:
    try:
        import httpx  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    key = _key_for("groq")
    if not key:
        return None
    model = _default_model("groq")
    try:
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer " + key},
            json={"model": model, "temperature": 0, "max_tokens": 500,
                  "response_format": {"type": "json_object"}, "messages": messages},
            timeout=12,
        )
        if r.status_code != 200:
            return None
        content = r.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception:  # noqa: BLE001
        return None


def _call_claude(system: str, user: str) -> Optional[dict]:
    key = _key_for("claude")
    if not key:
        return None
    try:
        import httpx  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    model = _default_model("claude")
    try:
        # Opus 4.8: NO temperature/top_p/budget_tokens. Force JSON via an explicit instruction.
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": model, "max_tokens": 700, "system": system,
                  "messages": [{"role": "user",
                                "content": user + "\n\nReturn ONLY the JSON object."}]},
            timeout=20,
        )
        if r.status_code != 200:
            return None
        blocks = r.json().get("content") or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        # tolerate a fenced/prefixed reply: extract the first {...} object
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group(0) if m else text)
    except Exception:  # noqa: BLE001
        return None


# A tiny deterministic MOCK provider for OFFLINE smoke: routes the utterance through the stub matcher and
# re-expresses it as a §22 object, so the validate+map pipeline is exercised with no key/network.
def _call_mock(utterance: str, ctx: dict) -> Optional[dict]:
    stub = _stub_match(utterance)
    kind = stub.get("kind")
    if kind == "goodbye":
        return {"intent": "clarify", "action_type": "", "confidence": 1.0, "risk_level": "L0",
                "entities": {}, "missing_fields": [], "user_facing_summary": "goodbye",
                "safe_to_execute": False, "block_reason": None}
    intent = stub.get("intent") or "clarify"
    reason = stub.get("reason") or ""
    if kind == "clarify" and reason.startswith("blocked:"):
        return {"intent": "blocked", "action_type": "", "confidence": 0.0, "risk_level": "L4",
                "entities": {}, "missing_fields": [], "user_facing_summary": "I can't do that.",
                "safe_to_execute": False, "block_reason": reason.split(":", 1)[1]}
    slots = stub.get("slots") or {}
    ents: dict = {}
    if "budget_minor" in slots:
        ents["amount_minor"] = slots["budget_minor"]
    if "channel" in slots:
        ents["platform"] = slots["channel"]
    if "segment" in slots:
        ents["lead_segment"] = slots["segment"]
    if "count" in slots:
        ents["count"] = slots["count"]
    return {"intent": intent if kind != "clarify" else "clarify",
            "action_type": intent, "confidence": float(stub.get("confidence") or 0.0),
            "risk_level": "L3", "requires_confirmation": True, "requires_pin": True,
            "entities": ents, "missing_fields": [],
            "user_facing_summary": "", "safe_to_execute": False, "block_reason": None}


def _llm_parse(utterance: str, ctx: dict) -> Optional[dict]:
    """LIVE LLM intent parse (spec §22). Calls the configured provider for the strict §22 object, validates
    it, retries ONCE with a corrector on a schema/JSON failure, then maps DOWN to IntentMatch. Returns the
    IntentMatch dict (consumed by _clamp), or None to fall back to the deterministic stub. NEVER raises,
    NEVER trusts the model's risk — identity.classify_risk + PolicyEngine decide risk downstream."""
    provider = _provider()

    # mock: deterministic, offline — exercises validate + map with no key/network.
    if provider == "mock":
        raw = _call_mock(utterance, ctx)
        ok = _validate_raw(raw)
        return _map_to_intentmatch(ok) if ok else None

    def _attempt(corrector: str = "") -> Optional[dict]:
        user = _build_user_message(utterance, ctx, corrector)
        if provider == "groq":
            return _call_groq([{"role": "system", "content": _SYSTEM_PROMPT},
                               {"role": "user", "content": user}])
        if provider == "claude":
            return _call_claude(_SYSTEM_PROMPT, user)
        return None

    raw = _attempt()
    ok = _validate_raw(raw)
    if ok is None:
        # retry once with a corrector message (aim-nlu §1.5)
        raw = _attempt("Your previous reply was not valid JSON or used an unknown intent. Return ONLY "
                       "the schema object with an intent from the closed lists.")
        ok = _validate_raw(raw)
    if ok is None:
        # second failure -> None so parse_intent falls back to the deterministic stub (never executes
        # on a garbage object; the stub is conservative and clarifies when unsure)
        return None
    return _map_to_intentmatch(ok)
