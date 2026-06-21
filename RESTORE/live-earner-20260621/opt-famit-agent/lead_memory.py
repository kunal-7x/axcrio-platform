"""lead_memory.py — DURABLE multi-channel relationship-memory extraction (VOICE-BRAIN W3b).

Spec: design/VOICE-BRAIN-MASTER-PLAN.md §3-D + design/W3b-EXTRACTION-STATE.md.

WHAT THIS IS
------------
A *leaf* module (imports only stdlib + httpx + db.engine; NO import of caller.py /
agent.py / aim_voice_agent.py / prompt.py — so it can never couple to the earner's
render path). It implements the WRITE side of the multi-channel memory layer:

  * enqueue_episode(...)  — called from a call-end / WA-update hook. Does ONE tiny,
        idempotent transactional INSERT into lead_memory_outbox. The transcript itself
        is already durable (inbound ai_manager_sessions, outbound transcripts/{room}.json,
        WA thread path) so the job + its payload snapshot is fully recoverable.
  * run_outbox_tick(...) — called from the long-lived caller.py scheduler_loop (the
        RESTARTABLE FastAPI process, NOT the LiveKit worker that gets drained at hangup).
        Claims a batch of due jobs via `SELECT ... FOR UPDATE SKIP LOCKED` with a lease,
        runs a cheap Groq extraction pass per job, UPSERTs lead_memory (with a
        `SELECT ... FOR UPDATE` row-lock so same-phone concurrent calls don't lose a
        facts-merge), appends a lead_episodes row, and marks the job done. A crash
        mid-extraction leaves the row claimed-but-stale; the lease expires and the next
        tick reclaims + retries it idempotently. THIS is the "survive a restart" property.

DURABLE, NOT FIRE-AND-FORGET
----------------------------
The naive design (a bare asyncio.create_task in the LiveKit shutdown hook) is killed by
worker drain → memory silently lost on the high-value calls. The outbox decouples CAPTURE
(a tiny synchronous INSERT inside the call process) from COMPUTE (the LLM extraction on a
separate, restart-surviving process). The job is the durable unit of work.

FLAG-OFF NO-OP (LEAD_MEMORY_PG, default 0)
------------------------------------------
Every public entry point checks `enabled()` FIRST and early-returns. Flag off ⇒ ZERO PG
reads, ZERO writes, ZERO LLM calls ⇒ the inbound / WA / earner paths are byte-identical.

SPLIT-BRAIN AVOIDANCE
---------------------
The earner NEVER reads PG memory — the tenant-prefixed FILE recap stays AUTHORITATIVE.
This module writes ONLY to PG (lead_memory / lead_episodes / lead_memory_outbox) and NEVER
touches the file recap, so the two layers can never race on the same artifact. PG is a
strictly ADDITIVE richer layer for the CRM panel / a future inbound reader.

LOSSLESS STORE
--------------
The full extracted structure is kept in JSONB (durable_facts map, objections list,
preferences, profile) — never summarized away. Only the human-readable `summary` is bounded
(≤600 chars). Facts merge (not overwrite) across episodes.

RLS
---
All PG ops go through db.engine.session(). The cross-tenant claim/sweep uses is_admin=True
(an admin queue-drain op); the actual lead_memory / lead_episodes write for a job is done
under engine.session(tenant_id=<job tenant>, is_admin=False) so a tenant's facts can NEVER
land in another tenant's row (red-team §3-D).
"""
from __future__ import annotations

import json
import os
import re
import socket
import time
from typing import Any, Optional

# ── flag + pre-gate constants ───────────────────────────────────────────────────
_FLAG = "LEAD_MEMORY_PG"
_MIN_TURNS = 4          # skip extraction below this (pre-gate)
_MIN_DURATION_S = 20    # skip extraction below this (pre-gate)
# outcomes that are not worth a token (and would pollute memory)
_SKIP_OUTCOMES = {"wrong_number", "hangup", "dnd", "no_answer", "busy", "failed", "voicemail"}
_CHANNELS = ("call", "whatsapp")

# worker / lease tuning
_LEASE_TTL_S = 300              # a claimed-but-unfinished job is reclaimable after this
_BATCH = 5                      # jobs claimed per tick (bounded so a burst can't hog caller.py)
_BACKOFF_BASE_S = 60           # retry backoff base (× 2^attempts)
_SUMMARY_MAX = 600
_GROQ_MODEL = os.getenv("LEAD_MEMORY_MODEL", "llama-3.1-8b-instant")  # cheap 8B per spec
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

_WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


def enabled() -> bool:
    """The single source of truth for the flag. Default OFF."""
    return os.getenv(_FLAG, "0").strip() in ("1", "true", "True", "yes", "on")


# ── canonical phone (ONE form, matches crm.canonical_phone / the file-key form) ──
def canonical_phone(p: str) -> str:
    """Digits-only E.164 body, NO '+'. This is the SAME form crm.canonical_phone and the
    wa_threads/memory file keys use, so voice (+91…) and WhatsApp (91…) collapse to ONE
    lead_memory row (avoids a split phone identity). '' if unjoinable."""
    if not p:
        return ""
    s = str(p).strip()
    if s.startswith("+"):
        return re.sub(r"\D", "", s)
    return re.sub(r"\D", "", s)


# ── db helpers (lazy import so this module is import-safe even if db is absent) ──
def _engine():
    try:
        from db import engine as _E  # local import: never a hard dep at module import
        return _E
    except Exception:  # noqa: BLE001
        return None


def _db_ready() -> bool:
    E = _engine()
    return bool(E is not None and E.available())


# ════════════════════════════════════════════════════════════════════════════════
#  ENQUEUE  (call-end / WA-update hook → one tiny durable INSERT)
# ════════════════════════════════════════════════════════════════════════════════
def pre_gate(*, n_turns: int, duration_s: int, outcome: str) -> Optional[str]:
    """Return a skip-reason string if this episode is NOT worth extracting, else None.
    Cheap, pure — run it BEFORE enqueue so we don't even queue junk."""
    if (outcome or "").strip().lower() in _SKIP_OUTCOMES:
        return f"outcome={outcome}"
    if int(n_turns or 0) < _MIN_TURNS:
        return f"turns={n_turns}<{_MIN_TURNS}"
    if int(duration_s or 0) < _MIN_DURATION_S:
        return f"duration={duration_s}<{_MIN_DURATION_S}"
    return None


def enqueue_episode(
    *,
    tenant_id: str,
    phone: str,
    channel: str,
    transcript_ref: str,
    turns: Optional[list] = None,
    summary: str = "",
    duration_s: int = 0,
    outcome: str = "",
    meta: Optional[dict] = None,
) -> dict:
    """Enqueue ONE durable extraction job. Idempotent on (tenant, phone, transcript_ref)
    via the unique index → a redelivered shutdown hook is a clean no-op. Pre-gated so junk
    never queues. NEVER raises (a memory-enqueue failure must never break the call path).

    Returns {"enqueued": bool, "reason": str} for logging. Flag OFF ⇒ {"enqueued": False,
    "reason": "flag_off"} with ZERO PG contact.
    """
    if not enabled():
        return {"enqueued": False, "reason": "flag_off"}
    try:
        ch = (channel or "").strip().lower()
        if ch not in _CHANNELS:
            return {"enqueued": False, "reason": f"bad_channel={channel}"}
        ph = canonical_phone(phone)
        tid = (tenant_id or "").strip()
        if not tid or not ph:
            return {"enqueued": False, "reason": "missing_tenant_or_phone"}
        turns = turns or []
        n_turns = len(turns)
        skip = pre_gate(n_turns=n_turns, duration_s=duration_s, outcome=outcome)
        if skip:
            return {"enqueued": False, "reason": "pregate:" + skip}
        if not _db_ready():
            return {"enqueued": False, "reason": "db_unavailable"}

        # Self-contained snapshot the worker extracts from — so it never re-reads the aim
        # store / a file. Cap the turns we carry (last ~40) so a long call can't bloat the row;
        # the verbatim source is still pointed-to by transcript_ref for exact recall.
        payload = {
            "turns": turns[-40:],
            "summary": (summary or "")[:4000],
            "duration_s": int(duration_s or 0),
            "n_turns": int(n_turns),
            "outcome_hint": (outcome or "")[:80],
            "meta": (meta or {}),
        }
        E = _engine()
        import sqlalchemy as sa
        # tenant-scoped (is_admin=False) write = the real path; RLS WITH CHECK binds it.
        with E.session(tenant_id=tid, is_admin=False) as s:
            row = s.execute(sa.text(
                "INSERT INTO lead_memory_outbox "
                "(tenant_id, phone, channel, transcript_ref, payload, status, next_attempt_at) "
                "VALUES (:t, :p, :c, :r, CAST(:pl AS jsonb), 'pending', now()) "
                "ON CONFLICT (tenant_id, phone, transcript_ref) DO NOTHING "
                "RETURNING id"),
                {"t": tid, "p": ph, "c": ch, "r": transcript_ref or "",
                 "pl": json.dumps(payload)}).fetchone()
        if row is None:
            return {"enqueued": False, "reason": "duplicate"}
        return {"enqueued": True, "reason": "ok", "id": int(row[0])}
    except Exception as exc:  # noqa: BLE001 — enqueue can NEVER break the caller
        return {"enqueued": False, "reason": "error:" + repr(exc)[:160]}


# ════════════════════════════════════════════════════════════════════════════════
#  EXTRACTION  (cheap Groq 8B pass → structured memory)
# ════════════════════════════════════════════════════════════════════════════════
_EXTRACT_SYS = (
    "You are a CRM memory extractor for a sales tele-calling / WhatsApp agent. "
    "Read the conversation and return ONLY a JSON object with EXACTLY these keys:\n"
    "  durable_facts: object of stable learned facts about this person (name, company, role, "
    "budget, location, product_interest, family/context — only what was actually stated; {} if none).\n"
    "  preferences: object of contact/comms prefs (best_time, channel, language, do_not_call_window, tone — {} if none).\n"
    "  objections: array of short strings, each an objection/concern the person raised ([] if none).\n"
    "  sentiment: one of 'positive','neutral','negative','mixed'.\n"
    "  outcome: one of 'booked','interested','callback','not_interested','wrong_number','no_answer','info_only','other'.\n"
    "  next_best_action: object {action, reason, priority} for the NEXT contact ({} if none).\n"
    "  summary: a <=600-char plain-text recap of what happened and what matters next.\n"
    "Extract ONLY facts present in the conversation. Never invent. Keep it concise but lossless on facts."
)


def _groq_key() -> str:
    """A Groq key with rotation if the llm_router pool is importable, else the env seed.
    Returns '' if none (extraction then fails gracefully → the job retries/backs off)."""
    try:
        from llm_router import get_pool as _get_pool  # type: ignore
        pool = _get_pool("groq")
        if pool is not None:
            k = pool.pick()
            if k and k.get("key"):
                return k["key"]
    except Exception:  # noqa: BLE001
        pass
    return (os.getenv("GROQ_API_KEY", "") or os.getenv("GROQ_KEY", "") or "").strip()


def _transcript_text(payload: dict) -> str:
    """Build the extraction input from the snapshot: prefer an existing summary + the last
    few turns (cheap, per spec 'summary + last-4-turns'), fall back to the full turn list."""
    turns = payload.get("turns") or []
    lines = []
    for x in turns[-12:]:
        role = (x.get("role") or "").strip() or "?"
        txt = (x.get("text") or "").strip()
        if txt:
            lines.append(f"{role}: {txt}")
    body = "\n".join(lines)
    summ = (payload.get("summary") or "").strip()
    if summ:
        body = "PRIOR SUMMARY: " + summ[:1500] + "\n\n" + body
    return body[:8000]


def _clamp(v: Any, allowed: set, default: str) -> str:
    s = (str(v or "")).strip().lower()
    return s if s in allowed else default


def extract_memory(payload: dict) -> dict:
    """Run the cheap Groq pass → a sanitized structured-memory dict. NEVER raises;
    returns a minimal dict with an _error on failure (the worker then decides retry vs give-up)."""
    text = _transcript_text(payload)
    if not text:
        return {"_error": "empty_transcript"}
    key = _groq_key()
    if not key:
        return {"_error": "no_groq_key"}
    try:
        import httpx
        r = httpx.post(
            _GROQ_URL,
            headers={"Authorization": "Bearer " + key},
            json={"model": _GROQ_MODEL, "temperature": 0.1, "max_tokens": 700,
                  "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": _EXTRACT_SYS},
                               {"role": "user", "content": text}]},
            timeout=30,
        )
        if r.status_code != 200:
            return {"_error": f"groq_{r.status_code}", "_body": r.text[:200]}
        content = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", content, re.DOTALL)
        data = json.loads(m.group(0) if m else content)
    except Exception as exc:  # noqa: BLE001
        return {"_error": repr(exc)[:200]}
    return _sanitize(data, payload)


def _sanitize(data: dict, payload: dict) -> dict:
    """Schema-clamp the LLM output (it's an injection sink). Keep facts LOSSLESS; bound only
    the human summary. Always returns a complete, well-typed dict."""
    if not isinstance(data, dict):
        data = {}
    facts = data.get("durable_facts")
    prefs = data.get("preferences")
    nba = data.get("next_best_action")
    objs = data.get("objections")
    summ = (str(data.get("summary") or "")).strip()[:_SUMMARY_MAX]
    if not summ:
        summ = (payload.get("summary") or "")[:_SUMMARY_MAX]
    out = {
        "durable_facts": facts if isinstance(facts, dict) else {},
        "preferences": prefs if isinstance(prefs, dict) else {},
        "next_best_action": nba if isinstance(nba, dict) else {},
        "objections": [str(o)[:240] for o in objs][:24] if isinstance(objs, list) else [],
        "sentiment": _clamp(data.get("sentiment"),
                            {"positive", "neutral", "negative", "mixed"}, "neutral"),
        "outcome": _clamp(data.get("outcome"),
                          {"booked", "interested", "callback", "not_interested",
                           "wrong_number", "no_answer", "info_only", "other"},
                          _clamp(payload.get("outcome_hint"),
                                 {"booked", "interested", "callback", "not_interested",
                                  "wrong_number", "no_answer", "info_only", "other"}, "other")),
        "summary": summ,
    }
    return out


def _merge_facts(old: dict, new: dict) -> dict:
    """Lossless merge: new facts win on a key collision, but a previously-known key is NEVER
    dropped just because this episode didn't restate it. (No fact is summarized away.)"""
    if not isinstance(old, dict):
        old = {}
    merged = dict(old)
    for k, v in (new or {}).items():
        if v in (None, "", {}, []):
            continue
        merged[k] = v
    return merged


# ════════════════════════════════════════════════════════════════════════════════
#  PERSIST  (UPSERT lead_memory w/ row-lock + append lead_episodes) — per job, tenant-scoped
# ════════════════════════════════════════════════════════════════════════════════
def _persist(tenant_id: str, phone: str, channel: str, transcript_ref: str,
             extracted: dict, payload: dict) -> None:
    """UPSERT lead_memory (SELECT ... FOR UPDATE row-lock so same-phone concurrent jobs don't
    lose a facts-merge) + append a lead_episodes row. Tenant-scoped (is_admin=False) so RLS
    binds the write into THIS tenant only. Raises on failure (the worker catches → retry)."""
    E = _engine()
    import sqlalchemy as sa
    with E.session(tenant_id=tenant_id, is_admin=False) as s:
        # row-lock the (tenant, phone) profile if present (merge-race guard).
        cur = s.execute(sa.text(
            "SELECT durable_facts, preferences, profile, episode_count, version "
            "FROM lead_memory WHERE tenant_id=:t AND phone=:p FOR UPDATE"),
            {"t": tenant_id, "p": phone}).fetchone()
        old_facts = cur[0] if cur else {}
        old_prefs = cur[1] if cur else {}
        old_profile = cur[2] if cur else {}
        prev_count = int(cur[3]) if cur else 0
        prev_ver = int(cur[4]) if cur else 0

        merged_facts = _merge_facts(old_facts or {}, extracted.get("durable_facts") or {})
        merged_prefs = _merge_facts(old_prefs or {}, extracted.get("preferences") or {})
        # profile = identity subset lifted out of facts (name/company/role/language…)
        prof_keys = ("name", "company", "role", "language", "location")
        prof_update = {k: merged_facts[k] for k in prof_keys if k in merged_facts}
        merged_profile = _merge_facts(old_profile or {}, prof_update)

        last_outcome = {
            "outcome": extracted.get("outcome", ""),
            "sentiment": extracted.get("sentiment", ""),
            "channel": channel,
            "at": payload.get("meta", {}).get("ended_at", "") or "",
        }
        s.execute(sa.text(
            "INSERT INTO lead_memory "
            "(tenant_id, phone, profile, durable_facts, preferences, last_outcome, "
            " next_best_action, episode_count, version, last_channel, last_seen_at, updated_at) "
            "VALUES (:t, :p, CAST(:prof AS jsonb), CAST(:df AS jsonb), CAST(:pr AS jsonb), "
            " CAST(:lo AS jsonb), CAST(:nba AS jsonb), :ec, :ver, :ch, now(), now()) "
            "ON CONFLICT (tenant_id, phone) DO UPDATE SET "
            " profile=EXCLUDED.profile, durable_facts=EXCLUDED.durable_facts, "
            " preferences=EXCLUDED.preferences, last_outcome=EXCLUDED.last_outcome, "
            " next_best_action=EXCLUDED.next_best_action, "
            " episode_count=EXCLUDED.episode_count, version=EXCLUDED.version, "
            " last_channel=EXCLUDED.last_channel, last_seen_at=now(), updated_at=now()"),
            {"t": tenant_id, "p": phone,
             "prof": json.dumps(merged_profile), "df": json.dumps(merged_facts),
             "pr": json.dumps(merged_prefs), "lo": json.dumps(last_outcome),
             "nba": json.dumps(extracted.get("next_best_action") or {}),
             "ec": prev_count + 1, "ver": prev_ver + 1, "ch": channel})

        # append-only episode (the per-interaction record; transcript_ref points at verbatim).
        s.execute(sa.text(
            "INSERT INTO lead_episodes "
            "(tenant_id, phone, channel, transcript_ref, summary, objections, sentiment, outcome, meta) "
            "VALUES (:t, :p, :c, :r, :su, CAST(:ob AS jsonb), :se, :oc, CAST(:mt AS jsonb))"),
            {"t": tenant_id, "p": phone, "c": channel, "r": transcript_ref or "",
             "su": extracted.get("summary", "")[:_SUMMARY_MAX],
             "ob": json.dumps(extracted.get("objections") or []),
             "se": extracted.get("sentiment", ""), "oc": extracted.get("outcome", ""),
             "mt": json.dumps({
                 "duration_s": payload.get("duration_s", 0),
                 "n_turns": payload.get("n_turns", 0),
                 "model": _GROQ_MODEL,
                 **(payload.get("meta") or {})})})


# ════════════════════════════════════════════════════════════════════════════════
#  WORKER TICK  (claim → extract → persist → mark) — rides caller.py scheduler_loop
# ════════════════════════════════════════════════════════════════════════════════
def _claim_jobs(limit: int) -> list[dict]:
    """Claim up to `limit` due jobs atomically. Admin session (cross-tenant queue drain).
    `FOR UPDATE SKIP LOCKED` so two ticks/processes never grab the same row. A row is due if
    it's pending-and-ready OR claimed-but-stale (lease expired = a worker that died). Each
    claimed row's attempts++ and status→'claimed' with a fresh lease in the SAME txn."""
    E = _engine()
    import sqlalchemy as sa
    jobs: list[dict] = []
    with E.session(is_admin=True) as s:
        rows = s.execute(sa.text(
            "SELECT id, tenant_id, phone, channel, transcript_ref, payload, attempts, max_attempts "
            "FROM lead_memory_outbox "
            "WHERE (status='pending' AND next_attempt_at <= now()) "
            "   OR (status='claimed' AND claimed_at < now() - (:lease || ' seconds')::interval) "
            "ORDER BY next_attempt_at ASC "
            "LIMIT :lim FOR UPDATE SKIP LOCKED"),
            {"lease": str(_LEASE_TTL_S), "lim": limit}).fetchall()
        for r in rows:
            jid, tid, ph, ch, ref, pl, att, maxatt = r
            s.execute(sa.text(
                "UPDATE lead_memory_outbox SET status='claimed', claimed_at=now(), "
                "claimed_by=:w, attempts=attempts+1, updated_at=now() WHERE id=:id"),
                {"w": _WORKER_ID, "id": jid})
            jobs.append({
                "id": int(jid), "tenant_id": tid, "phone": ph, "channel": ch,
                "transcript_ref": ref or "",
                "payload": pl if isinstance(pl, dict) else (json.loads(pl) if pl else {}),
                "attempts": int(att) + 1, "max_attempts": int(maxatt)})
    return jobs


def _mark(job_id: int, status: str, error: str = "", attempts: int = 0,
          max_attempts: int = 5) -> None:
    """Terminal/retry bookkeeping (admin session — queue control)."""
    E = _engine()
    import sqlalchemy as sa
    with E.session(is_admin=True) as s:
        if status == "retry":
            if attempts >= max_attempts:
                s.execute(sa.text(
                    "UPDATE lead_memory_outbox SET status='failed', last_error=:e, "
                    "updated_at=now() WHERE id=:id"),
                    {"e": error[:500], "id": job_id})
            else:
                backoff = _BACKOFF_BASE_S * (2 ** max(0, attempts - 1))
                s.execute(sa.text(
                    "UPDATE lead_memory_outbox SET status='pending', last_error=:e, "
                    "next_attempt_at=now() + (:bo || ' seconds')::interval, "
                    "claimed_by='', claimed_at=NULL, updated_at=now() WHERE id=:id"),
                    {"e": error[:500], "bo": str(int(backoff)), "id": job_id})
        else:
            s.execute(sa.text(
                "UPDATE lead_memory_outbox SET status=:st, last_error=:e, updated_at=now() "
                "WHERE id=:id"),
                {"st": status, "e": error[:500], "id": job_id})


def _process_one(job: dict) -> str:
    """Extract + persist ONE job. Returns 'done' | 'skipped' | 'retry'. NEVER raises."""
    try:
        payload = job.get("payload") or {}
        # re-run the pre-gate from the durable snapshot (defends against an enqueue that
        # slipped through a flag flip, and keeps the worker self-sufficient).
        skip = pre_gate(n_turns=payload.get("n_turns", 0),
                        duration_s=payload.get("duration_s", 0),
                        outcome=payload.get("outcome_hint", ""))
        if skip:
            return "skipped"
        extracted = extract_memory(payload)
        if "_error" in extracted:
            # transient (no key / 429 / network) → retry; the merge dict is never partial-written.
            return "retry"
        _persist(job["tenant_id"], job["phone"], job["channel"],
                 job["transcript_ref"], extracted, payload)
        return "done"
    except Exception:  # noqa: BLE001 — any persist failure is a retry, never a crash
        return "retry"


def run_outbox_tick(limit: int = _BATCH) -> dict:
    """One worker pass: claim a batch, process each, mark. Call from caller.py's
    scheduler_loop (the restartable process). Flag OFF ⇒ instant no-op with ZERO PG contact.
    NEVER raises — returns a small stats dict for logging."""
    if not enabled():
        return {"ran": False, "reason": "flag_off"}
    if not _db_ready():
        return {"ran": False, "reason": "db_unavailable"}
    stats = {"ran": True, "claimed": 0, "done": 0, "skipped": 0, "retry": 0, "failed": 0}
    try:
        jobs = _claim_jobs(limit)
    except Exception as exc:  # noqa: BLE001
        return {"ran": False, "reason": "claim_error:" + repr(exc)[:160]}
    stats["claimed"] = len(jobs)
    for job in jobs:
        result = _process_one(job)
        if result == "done":
            _mark(job["id"], "done")
            stats["done"] += 1
        elif result == "skipped":
            _mark(job["id"], "skipped")
            stats["skipped"] += 1
        else:  # retry
            _mark(job["id"], "retry", error="extract_or_persist_failed",
                  attempts=job["attempts"], max_attempts=job["max_attempts"])
            if job["attempts"] >= job["max_attempts"]:
                stats["failed"] += 1
            else:
                stats["retry"] += 1
    return stats


# ════════════════════════════════════════════════════════════════════════════════
#  READ  (W4b — connect-window retrieval for the INBOUND returning-caller greeting)
# ════════════════════════════════════════════════════════════════════════════════
# These are the READ side of the memory layer, used by the inbound aim_voice_agent
# connect path to greet a RETURNING caller with their history (name / prior outcome /
# next-best-action / recent episode one-liners). They are:
#   * FLAG-GATED  — enabled() (LEAD_MEMORY_PG) is checked FIRST; flag off ⇒ {} / "" ⇒ ZERO PG
#                   contact ⇒ the inbound brain renders byte-identical to today.
#   * FALLBACK-SAFE — db down / no rows / any error ⇒ {} / "" (NEVER raises). The CALLER (the
#                   connect path) additionally wraps the call in a hard asyncio timeout so a slow
#                   PG read can never block the greeting — on timeout it just proceeds with no memory.
#   * RLS-SCOPED  — read under engine.session(tenant_id=..., is_admin=False) (NEVER the is_admin
#                   escape hatch, which would make a caller read every tenant's memory — red-team §3-D).
#   * SPLIT-BRAIN-SAFE — this is a PURE READ of the additive PG layer; it never writes the file recap
#                   and the earner never calls it. The file recap stays the earner's authoritative source.
_EPISODES_MAX = 6  # hard cap on episodes pulled at connect (cheap; keeps the injected block small)


def read_lead_brief(tenant_id: str, phone: str, n_episodes: int = 3) -> dict:
    """Load the (tenant, phone) lead_memory profile + the last N lead_episodes (newest-first)
    for the INBOUND connect-time greeting. Returns a structured dict:
        {"phone","memory":{...}|None,"episodes":[...]}
    Flag OFF / db down / no profile+no episodes / ANY error ⇒ {} (empty). NEVER raises.

    The caller MUST still wrap this in a hard timeout (it does a PG round-trip); on timeout the
    caller proceeds with no memory. This fn itself does no timeout — it just never throws."""
    if not enabled():
        return {}
    try:
        ph = canonical_phone(phone)
        tid = (tenant_id or "").strip()
        if not tid or not ph:
            return {}
        if not _db_ready():
            return {}
        n = max(0, min(int(n_episodes or 0), _EPISODES_MAX))
        E = _engine()
        import sqlalchemy as sa
        mem = None
        eps: list[dict] = []
        # tenant-scoped, NON-admin → RLS binds the read to THIS tenant only.
        with E.session(tenant_id=tid, is_admin=False) as s:
            mrow = s.execute(sa.text(
                "SELECT profile, durable_facts, preferences, last_outcome, next_best_action, "
                "       episode_count, version, last_channel, last_seen_at, updated_at "
                "FROM lead_memory WHERE tenant_id=:t AND phone=:p"),
                {"t": tid, "p": ph}).fetchone()
            if mrow is not None:
                mem = {
                    "profile": mrow[0] or {},
                    "durable_facts": mrow[1] or {},
                    "preferences": mrow[2] or {},
                    "last_outcome": mrow[3] or {},
                    "next_best_action": mrow[4] or {},
                    "episode_count": int(mrow[5] or 0),
                    "version": int(mrow[6] or 0),
                    "last_channel": mrow[7] or "",
                    "last_seen_at": (mrow[8].isoformat() if mrow[8] else None),
                    "updated_at": (mrow[9].isoformat() if mrow[9] else None),
                }
            if n > 0:
                erows = s.execute(sa.text(
                    "SELECT channel, summary, objections, sentiment, outcome, created_at "
                    "FROM lead_episodes WHERE tenant_id=:t AND phone=:p "
                    "ORDER BY created_at DESC LIMIT :n"),
                    {"t": tid, "p": ph, "n": n}).fetchall()
                for er in erows:
                    eps.append({
                        "channel": er[0] or "",
                        "summary": er[1] or "",
                        "objections": er[2] or [],
                        "sentiment": er[3] or "",
                        "outcome": er[4] or "",
                        "created_at": (er[5].isoformat() if er[5] else None),
                    })
        if mem is None and not eps:
            return {}  # genuinely no history for this caller → "" block downstream
        return {"phone": ph, "memory": mem, "episodes": eps}
    except Exception:  # noqa: BLE001 — a memory READ can NEVER break the call connect
        return {}


def _kv_line(label: str, d: Any, keys: tuple, limit: int = 220) -> str:
    """Render 'label: k=v, k=v' from the present subset of `keys` in dict `d`. '' if none present."""
    if not isinstance(d, dict) or not d:
        return ""
    parts = []
    for k in keys:
        v = d.get(k)
        if v in (None, "", {}, []):
            continue
        sv = ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)
        sv = sv.replace("\n", " ").strip()
        if sv:
            parts.append(f"{k}={sv}")
    if not parts:
        return ""
    return (label + ": " + "; ".join(parts))[:limit]


def render_brief_block(brief: dict) -> str:
    """Pure formatter: a compact fenced CALLER-MEMORY block for the inbound brain, or "" if empty.

    Kept short (a few lines) and framed as BUSINESS CONTEXT so it sits ABOVE the vendor/knowledge
    pack (so the model uses it to greet warmly) without bloating the prompt. Nothing here is verbatim
    recall — it's the distilled relationship memory (the verbatim turns live in the transcript store)."""
    if not isinstance(brief, dict) or not brief:
        return ""
    mem = brief.get("memory") or {}
    eps = brief.get("episodes") or []
    lines: list[str] = []

    profile = mem.get("profile") if isinstance(mem, dict) else {}
    facts = mem.get("durable_facts") if isinstance(mem, dict) else {}
    prefs = mem.get("preferences") if isinstance(mem, dict) else {}
    last_outcome = mem.get("last_outcome") if isinstance(mem, dict) else {}
    nba = mem.get("next_best_action") if isinstance(mem, dict) else {}

    name = ""
    if isinstance(profile, dict):
        name = str(profile.get("name") or "").strip()
    if not name and isinstance(facts, dict):
        name = str(facts.get("name") or "").strip()
    if name:
        lines.append(f"Name on file: {name}")

    fline = _kv_line("Known", facts,
                     ("company", "role", "budget", "location", "product_interest",
                      "configuration", "timeline", "language"))
    if fline:
        lines.append(fline)
    pline = _kv_line("Prefs", prefs,
                     ("best_time", "channel", "language", "tone", "do_not_call_window"))
    if pline:
        lines.append(pline)

    if isinstance(last_outcome, dict) and last_outcome:
        oc = str(last_outcome.get("outcome") or "").strip()
        se = str(last_outcome.get("sentiment") or "").strip()
        bits = ", ".join(b for b in (oc, se) if b)
        if bits:
            lines.append(f"Last interaction: {bits}")

    if isinstance(nba, dict) and nba:
        act = str(nba.get("action") or "").strip()
        if act:
            rsn = str(nba.get("reason") or "").strip()
            lines.append(f"Suggested next step: {act}" + (f" ({rsn})" if rsn else ""))

    if eps:
        lines.append("Recent conversations (newest first):")
        for e in eps[:3]:
            ch = str(e.get("channel") or "").strip() or "call"
            summ = str(e.get("summary") or "").strip().replace("\n", " ")
            if not summ:
                continue
            lines.append(f"  - [{ch}] {summ[:200]}")

    if not lines:
        return ""
    body = "\n".join(lines)
    return (
        "\n\n=== CALLER MEMORY (what we already know about THIS caller from past calls/WhatsApp — "
        "BUSINESS CONTEXT, use it to greet them warmly and continue, do NOT restate it back verbatim) ===\n"
        + body +
        "\nThis is reference history only; if the caller says something different now, the LIVE call wins.\n"
    )


def load_lead_brief(tenant_id: str, phone: str, n_episodes: int = 3) -> str:
    """Convenience one-shot used by the inbound connect path: read + render in one call.
    Flag OFF / no history / any error ⇒ "" (a clean no-op the injection treats as "no memory")."""
    try:
        return render_brief_block(read_lead_brief(tenant_id, phone, n_episodes=n_episodes))
    except Exception:  # noqa: BLE001
        return ""
