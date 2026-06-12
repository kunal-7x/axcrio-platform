"""ai_manager.state_machine — THE deterministic command state machine (spec §4, security-critical).

S0 CONNECT -> S1 VERIFY IDENTITY -> S2 AUTHENTICATE (anti-spoof PIN/OTP) -> S3 CONTEXT -> S4 CAPTURE
INTENT -> S5 PERMISSION -> S6 STEP-UP (risky only, fresh+scoped) -> S7 CONFIRM -> S8 DELEGATE+EXECUTE ->
S9 REPORT -> S_END. EVERY transition is code-decided; the LLM only FILLS SLOTS, never AUTHORIZES.

CHANNEL-AGNOSTIC (task: "voice/chat command center"; AI_MANAGER_STATE correction #5). The machine drives
an injected `transport` with three methods — speak(text), listen()->utterance, collect_secret(n,mode)->
digits — and an optional `recorder` with pause()/resume() for PIN AUDIO hygiene (spec §6.5). The LiveKit
voice adapter and a chat adapter are THIN wrappers over this same machine. The offline test injects a
ScriptedTransport so the entire safety spine runs with ZERO keys / network / telephony.

SAFETY PROPERTIES (baked into the ORDER, spec §6):
  1. caller-ID alone never grants access — a fresh PIN/OTP (S2) proves the human BEFORE any business
     data is spoken.
  2. every risky action gets its OWN fresh, scoped step-up (S6) — one login PIN can't silently authorize
     ten ad-budget bumps.
  3. an explicit spoken CONFIRM with the amount read back (S7) precedes any side effect.
  4. the runner re-enforces caps/idempotency/kill-switch in S8 (defense in depth) — voice is not trusted.
  5. lockout after N PIN failures (config.max_pin_attempts), per number.
  6. everything is audited with the verified TENANT as actor, never "system".
  7. PIN AUDIO suppressed: recorder.pause() wraps every collect_secret span; digits consumed in-memory,
     stored as "****", NEVER persisted.

IMPORT-SAFE / NEVER RAISES at the boundary: run() catches everything and ends the call gracefully.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import audit_bridge as _audit
from . import config as _config
from . import delegate as _delegate
from . import firewall_bridge as _firewall
from . import identity as _identity
from . import store as _store
from .intent import driver as _intent


# ---------------- the transport contract (injected; voice/chat/scripted all implement it) ----------------
class Transport:
    """Minimal duck-typed contract. A real adapter speaks/listens over LiveKit or chat; the offline test
    injects a ScriptedTransport. Methods MUST NOT raise (the machine treats a None/empty as hangup)."""

    def speak(self, text: str) -> None: ...
    def listen(self) -> str: ...                          # next utterance ("" => hangup)
    def collect_secret(self, n: int = 4, mode: str = "voice_pin") -> str: ...  # digits (never logged)


class _NullRecorder:
    """No-op recorder when none injected (chat path has no audio to suppress)."""
    def pause(self) -> None: ...
    def resume(self) -> None: ...


# ---------------- the session result ----------------
@dataclass
class SessionResult:
    session_id: str
    tenant_id: str = ""
    number_id: str = ""
    outcome: str = ""                 # ok | reject:<reason> | error
    authed: bool = False
    auth_method: str = ""
    n_actions: int = 0
    turns: list = field(default_factory=list)     # PIN/OTP digits NEVER appear here (masked "****")
    actions: list = field(default_factory=list)
    _turn_seq: int = 0                            # monotonic per-session turn counter (for the PG turns rows)

    def to_record(self, *, caller_id: str = "") -> dict:
        return {"session_id": self.session_id, "tenant_id": self.tenant_id, "number_id": self.number_id,
                "caller_id": caller_id, "authed": self.authed, "auth_method": self.auth_method,
                "turns": self.turns, "actions": self.actions, "outcome": self.outcome,
                "n_actions": self.n_actions}


# ---------------- the machine ----------------
class CommandMachine:
    def __init__(self, transport: Transport, *, recorder: Any = None, firewall: Any = None,
                 runner: Optional[Callable] = None, tenant_by_id: Optional[Callable] = None,
                 channel: str = "dashboard"):
        self.t = transport
        self.rec = recorder or _NullRecorder()
        self.fw = firewall            # injected REAL firewall module (or None -> bridge imports it)
        self.runner = runner          # injected workforce.run_agent (or a StubDelegate fake)
        self.tenant_by_id = tenant_by_id or (lambda tid: {"tenant_id": tid, "role": "manager"})
        self.channel = channel or "dashboard"   # phone|whatsapp|dashboard (persisted on the session row)

    # -- helpers --
    def _persist_turn(self, res: SessionResult, role: str, text: str) -> None:
        """Append this turn to the durable PG transcript (ai_manager_session_turns). Best-effort: a no-op
        until the session row exists (post-S1 tenant_id) and whenever PG is down. PIN/OTP digits never
        reach here (the secret span is collected via _collect_secret, never _say/_hear). NEVER raises."""
        if not res.tenant_id or not (text or "").strip():
            return
        try:
            seq = res._turn_seq
            res._turn_seq += 1
            _store.add_turn(res.tenant_id, res.session_id, role, text, seq=seq)
        except Exception:  # noqa: BLE001
            pass

    def _say(self, res: SessionResult, text: str) -> None:
        res.turns.append({"role": "agent", "text": text})
        self._persist_turn(res, "agent", text)
        try:
            self.t.speak(text)
        except Exception:  # noqa: BLE001
            pass

    def _hear(self, res: SessionResult) -> str:
        try:
            u = self.t.listen() or ""
        except Exception:  # noqa: BLE001
            u = ""
        if u:
            res.turns.append({"role": "user", "text": u})
            self._persist_turn(res, "user", u)
        return u

    def _collect_secret(self, n: int, mode: str) -> str:
        """Collect a PIN/OTP with AUDIO SUPPRESSED (recorder paused around the span) — spec §6.5/§9 8b.
        The transcript NEVER sees the digits (we append a masked turn, not the value)."""
        self.rec.pause()
        try:
            digits = ""
            try:
                digits = self.t.collect_secret(n=n, mode=mode) or ""
            except Exception:  # noqa: BLE001
                digits = ""
        finally:
            self.rec.resume()
        return digits

    # -- the loop --
    def run(self, caller_id: str, *, session_id: str = "") -> SessionResult:
        # session_id may be supplied by the voice adapter so the recording object-key (chosen at egress
        # start, BEFORE this runs) and the persisted session row share one id. Default: mint a fresh one.
        sid = session_id or ("vs_" + uuid.uuid4().hex[:12])
        res = SessionResult(session_id=sid)
        max_attempts = _config.max_pin_attempts()
        try:
            return self._run_inner(caller_id, res, max_attempts)
        except Exception as exc:  # noqa: BLE001 — boundary: never let the machine crash a call.
            res.outcome = "error"
            try:
                _store.end_session(res.tenant_id, sid, status="failed")
            except Exception:  # noqa: BLE001
                pass
            _audit.call_end(actor=res.tenant_id or "system", tenant_id=res.tenant_id or "",
                            session_id=sid, outcome="error:" + type(exc).__name__,
                            n_actions=res.n_actions)
            return res

    def _run_inner(self, caller_id: str, res: SessionResult, max_attempts: int) -> SessionResult:
        sid = res.session_id

        # S0 CONNECT
        _audit.call_start(actor="anon", tenant_id="", session_id=sid,
                          meta={"caller_id": _mask_phone(caller_id)})

        # S1 VERIFY IDENTITY (caller-ID is a HINT only)
        number = _identity.resolve(caller_id)
        if not number:
            self._say(res, "This number isn't registered for AI Manager.")
            res.outcome = "reject:unregistered"
            _audit.call_end(actor="anon", tenant_id="", session_id=sid,
                            outcome=res.outcome, n_actions=0)
            return res
        res.tenant_id = number.get("tenant_id", "")
        res.number_id = number.get("number_id", "")
        role = number.get("role", "operator")
        grants = number.get("grants", [])
        verify_mode = number.get("verify_mode", "voice_pin")
        tenant_dict = self.tenant_by_id(res.tenant_id) or {"tenant_id": res.tenant_id, "role": role}
        is_admin = bool(tenant_dict.get("is_admin")) or role == "admin"

        # PERSIST the session row (durable §8 mirror; best-effort, never gates the call).
        try:
            _store.create_session(res.tenant_id, sid, channel=self.channel,
                                  caller_phone=_mask_phone(caller_id),
                                  llm_provider=_config.llm_provider())
        except Exception:  # noqa: BLE001
            pass

        # S2 AUTHENTICATE THE HUMAN (anti-spoof; BEFORE any business data is revealed)
        if not self._authenticate(res, verify_mode, max_attempts):
            return res  # outcome already set (reject:lockout)
        res.authed = True
        res.auth_method = verify_mode
        _audit.authed(actor=res.tenant_id, tenant_id=res.tenant_id, session_id=sid, method=verify_mode)

        # S3 LOAD BUSINESS CONTEXT (read-only)
        ctx = _delegate.read_context(res.tenant_id, runner=self.runner)
        name = ctx.get("business_name") or "there"
        self._say(res, f"Hi {name}. You're verified. What would you like to do?")

        # S4..S9 COMMAND LOOP
        while True:
            utterance = self._hear(res)
            if not utterance:
                res.outcome = res.outcome or "ok"
                break
            match = _intent.parse_intent(utterance, ctx)
            kind = match.get("kind")

            if kind == "goodbye":
                res.outcome = "ok"
                break
            if kind == "clarify":
                # A TRUE no-intent clarify (we couldn't recognize ANY action). A missing-SLOT command no
                # longer lands here — it arrives as kind=="command" with missing_fields and is elicited
                # below — so this branch is only the genuine "rephrase" case (and security blocks).
                reason = match.get("reason", "") or ""
                if reason.startswith("blocked:"):
                    self._say(res, "I can't do that — it's not allowed.")
                else:
                    self._say(res, "I didn't quite catch a clear action — could you say that again?")
                continue
            if kind == "query":
                self._say(res, _answer_query(match, ctx))
                continue
            if kind != "command":
                self._say(res, "I can't do that yet.")
                continue

            # ---- S4.5 ELICIT (multi-turn slot-filling) ----
            # The command may arrive HALF-SPECIFIED (e.g. "run a campaign" with no campaign/segment). We
            # hold it as a PendingCommand and ask the single most-important missing slot at a time, merge
            # the reply (re-parse JUST that slot, never the whole command), and loop until every required
            # slot is filled — instead of the old dead-end clarify that discarded the intent. Bounded by
            # MAX_CLARIFY so a user who can't supply a slot isn't trapped. The completed command then flows
            # UNCHANGED into the existing S5->S6->S7->S8 safety spine.
            intent_name = match.get("intent", "") or ""
            slots = dict(match.get("slots", {}) or {})
            outstanding = list(match.get("missing_fields")
                               or _intent.missing_required(intent_name, slots))
            elicit_ok = True
            tries = 0
            while outstanding:
                if tries >= _MAX_CLARIFY:
                    self._say(res, "Let's leave that for now. What else can I do?")
                    elicit_ok = False
                    break
                tries += 1
                nxt = outstanding[0]
                self._say(res, _intent.slot_question(nxt))
                reply = self._hear(res)
                if not reply:
                    elicit_ok = False
                    break
                # the user may pivot to a brand-new command mid-elicit; if so, abandon this PendingCommand
                # and let the OUTER loop reclassify next turn (we just re-queue the reply isn't possible
                # in a sync loop, so we re-parse it here: a confident NEW command intent wins).
                re_match = _intent.parse_intent(reply, ctx)
                if (re_match.get("kind") == "command"
                        and (re_match.get("intent") or "") != intent_name
                        and float(re_match.get("confidence", 0) or 0) >= 0.75):
                    match = re_match
                    intent_name = match.get("intent", "") or ""
                    slots = dict(match.get("slots", {}) or {})
                    outstanding = list(match.get("missing_fields")
                                       or _intent.missing_required(intent_name, slots))
                    tries = 0
                    continue
                ok, val = _intent.parse_slot_value(intent_name, nxt, reply, ctx)
                if ok:
                    slots[nxt] = val
                    outstanding = _intent.missing_required(intent_name, slots)
                else:
                    self._say(res, "Sorry, I didn't get that.")
                # loop re-asks the (still) first outstanding slot
            if not elicit_ok:
                continue
            # fold the elicited slots back into the match the rest of the spine consumes
            match = dict(match)
            match["slots"] = slots
            match["missing_fields"] = []

            # ---- a COMMAND: S5 PERMISSION ----
            action = _delegate.map_intent_to_action(match)
            tool = action["tool"]
            risk = action["risk"]
            risky = _identity.is_risky(tool)

            # PERSIST the command row at lifecycle start (§12 "create ai_manager_commands row"). The
            # (vendor_id, idempotency_key) UNIQUE makes a retried turn resolve to the SAME row (no
            # double-execute). All store calls are best-effort — a PG-down box still runs the turn.
            idem_key = _store.make_idempotency_key(res.tenant_id, sid, tool, action.get("args", {}))
            command_id = _store.create_command(
                res.tenant_id, session_id=sid, raw_text=utterance, normalized_text=utterance,
                detected_intent=match.get("intent", "") or tool, action_type=tool,
                action_payload=action.get("args", {}), risk_level=_risk_to_int(risk),
                status="pending", idempotency_key=idem_key) or ""

            if not _identity.permits(role, grants, tool):
                _store.update_command(res.tenant_id, command_id, status="denied",
                                      permission_result={"permitted": False, "role": role})
                _store.record_audit_log(res.tenant_id, event_type="permission_denied",
                                        severity="warning", session_id=sid, command_id=command_id,
                                        message="permission denied", metadata={"action": tool})
                _audit.permission_denied(actor=res.tenant_id, tenant_id=res.tenant_id,
                                         session_id=sid, action=tool)
                self._say(res, "You're not permitted to do that.")
                continue
            _store.update_command(res.tenant_id, command_id, pin_required=risky,
                                  confirmation_required=True,
                                  permission_result={"permitted": True, "role": role})

            # ---- S6 STEP-UP for risky (FRESH, per-action, scoped) ----
            step_up_token = ""
            if risky:
                _store.update_command(res.tenant_id, command_id, status="needs_pin")
                step_up_token = self._step_up(res, action, verify_mode, max_attempts)
                if step_up_token is None:
                    # lockout during step-up -> end call
                    _store.update_command(res.tenant_id, command_id, status="denied",
                                          error_message="lockout during step-up")
                    return res
                if step_up_token == "":
                    # failed but not locked out -> abort THIS command, keep the session
                    _store.update_command(res.tenant_id, command_id, status="failed",
                                          error_message="step-up PIN not verified")
                    self._say(res, "I couldn't verify your PIN. Cancelling that.")
                    continue
                _store.update_command(res.tenant_id, command_id, pin_verified=True)

            # ---- S7 CONFIRM (amount read back) ----
            _store.update_command(res.tenant_id, command_id, status="needs_confirmation")
            self._say(res, _confirm_text(action))
            ans = self._hear(res)
            if not _is_yes(ans):
                _store.update_command(res.tenant_id, command_id, status="cancelled",
                                      confirmation_status="declined")
                _store.record_audit_log(res.tenant_id, event_type="cancelled", session_id=sid,
                                        command_id=command_id, message="cancelled by caller",
                                        metadata={"action": tool})
                _audit.cancelled(actor=res.tenant_id, tenant_id=res.tenant_id,
                                 session_id=sid, action=tool)
                self._say(res, "Cancelled.")
                continue
            _store.update_command(res.tenant_id, command_id, confirmation_status="confirmed",
                                  status="executing")

            # ---- S8 DELEGATE & EXECUTE (the runner re-enforces caps/kill-switch independently) ----
            # The action_run row is the dispatched-execution record (§12 "create action_run -> execute").
            run_db_id = _store.create_action_run(
                res.tenant_id, command_id=command_id, action_type=tool,
                target_module=_delegate.role_for(tool), status="running",
                input=action.get("args", {})) or ""
            result = _delegate.execute(res.tenant_id, action, tenant_dict=tenant_dict,
                                       step_up_token=step_up_token, actor=res.tenant_id,
                                       runner=self.runner, is_admin=is_admin)
            status = result.get("status", "")
            # executed is GROUND TRUTH: only a runner "done" means the side effect actually ran. A
            # parked/killed/not_configured/error result is NOT an execution — record it honestly (the
            # runner re-enforced its own caps/kill-switch independently; defense in depth, spec §4 S8).
            executed = status == "done"
            res.actions.append({"intent": tool, "risk": risk,
                                "stepup": bool(step_up_token), "executed": executed,
                                "result_status": status})
            if executed:
                res.n_actions += 1
            # PERSIST the terminal command status + execution result (§12 "save result -> audit log").
            _store.finish_action_run(res.tenant_id, run_db_id,
                                     status=("succeeded" if executed else "failed"),
                                     output={"status": status, "run_id": result.get("run_id", "")})
            _store.update_command(res.tenant_id, command_id,
                                  status=("succeeded" if executed else "failed"),
                                  execution_result={"status": status, "executed": executed,
                                                    "run_id": result.get("run_id", "")},
                                  error_message=("" if executed else (result.get("reason", "") or status)))
            _store.record_audit_log(res.tenant_id, event_type="execute",
                                    severity=("info" if executed else "warning"), session_id=sid,
                                    command_id=command_id, message=f"execute {tool} -> {status}",
                                    metadata={"action": tool, "executed": executed,
                                              "run_id": result.get("run_id", "")})
            _audit.execute(actor=res.tenant_id, tenant_id=res.tenant_id, session_id=sid,
                           action=tool, meta={"status": status, "executed": executed,
                                              "run_id": result.get("run_id", "")})
            # ---- S9 REPORT ----
            self._say(res, _report_text(action, result))

        # S_END — close the session row with the final transcript + outcome + executed-action count so
        # the panel list/detail has the headline without joining. Best-effort; never gates the hangup.
        try:
            _store.end_session(res.tenant_id, sid,
                               status=("completed" if (res.outcome or "ok").startswith("ok")
                                       else "failed"),
                               transcript_text=_flatten_transcript(res.turns),
                               outcome=res.outcome or "ok", n_actions=res.n_actions)
        except Exception:  # noqa: BLE001
            pass
        _audit.call_end(actor=res.tenant_id or "anon", tenant_id=res.tenant_id, session_id=sid,
                        outcome=res.outcome, n_actions=res.n_actions)
        return res

    # ---- S2 authenticate (login) ----
    def _authenticate(self, res: SessionResult, verify_mode: str, max_attempts: int) -> bool:
        """Prove the human BEFORE any data is revealed. Returns True on success; on N failures locks the
        number and sets outcome=reject:lockout (returns False). NO step-up scope here (login != action-auth)."""
        attempts = 0
        while True:
            self._say(res, "Please say your 4-digit PIN."
                      if verify_mode == "voice_pin" else "I've sent you a code. Please say it.")
            secret = self._collect_secret(n=6 if verify_mode == "otp" else 4, mode=verify_mode)
            auth = _firewall.authenticate(res.tenant_id, secret, scope="", method=verify_mode, fw=self.fw)
            if auth.get("ok"):
                return True
            attempts += 1
            _audit.auth_fail(actor=res.tenant_id, tenant_id=res.tenant_id, session_id=res.session_id,
                             attempts=attempts, reason=auth.get("reason", ""))
            if attempts >= max_attempts:
                self._lock_number(res)
                self._say(res, "Too many incorrect attempts. This number is locked. Goodbye.")
                res.outcome = "reject:lockout"
                try:
                    _store.end_session(res.tenant_id, res.session_id, status="blocked")
                    _store.record_audit_log(res.tenant_id, event_type="lockout", severity="critical",
                                            session_id=res.session_id, message="login lockout",
                                            metadata={"attempts": attempts})
                except Exception:  # noqa: BLE001
                    pass
                _audit.call_end(actor=res.tenant_id, tenant_id=res.tenant_id, session_id=res.session_id,
                                outcome=res.outcome, n_actions=0)
                return False
            self._say(res, "That PIN didn't match. Try again.")

    # ---- S6 step-up (per-action) ----
    def _step_up(self, res: SessionResult, action: dict, verify_mode: str, max_attempts: int):
        """Fresh, scoped per-action step-up. Returns: the token (success), "" (failed, not locked -> abort
        this command), or None (locked out -> end call). Audits stepup_ok/stepup_fail."""
        scope = action["scope"] or "spend"
        tool = action["tool"]
        attempts = 0
        while True:
            self._say(res, _consequence_text(action) + " Say your PIN to confirm.")
            secret = self._collect_secret(n=6 if verify_mode == "otp" else 4, mode=verify_mode)
            auth = _firewall.authenticate(res.tenant_id, secret, scope=scope, method=verify_mode,
                                          fw=self.fw)
            if auth.get("ok") and auth.get("step_up"):
                _audit.stepup_ok(actor=res.tenant_id, tenant_id=res.tenant_id,
                                 session_id=res.session_id, scope=scope, action=tool)
                return auth["step_up"].get("step_up_token", "") or _NO_TOKEN_BUT_OK
            attempts += 1
            _audit.stepup_fail(actor=res.tenant_id, tenant_id=res.tenant_id,
                               session_id=res.session_id, scope=scope, action=tool, attempts=attempts)
            if attempts >= max_attempts:
                self._lock_number(res)
                self._say(res, "Too many incorrect attempts. This number is locked. Goodbye.")
                res.outcome = "reject:lockout"
                try:
                    _store.end_session(res.tenant_id, res.session_id, status="blocked")
                    _store.record_audit_log(res.tenant_id, event_type="lockout", severity="critical",
                                            session_id=res.session_id, message="step-up lockout",
                                            metadata={"scope": scope, "action": tool, "attempts": attempts})
                except Exception:  # noqa: BLE001
                    pass
                _audit.call_end(actor=res.tenant_id, tenant_id=res.tenant_id,
                                session_id=res.session_id, outcome=res.outcome, n_actions=res.n_actions)
                return None
            self._say(res, "That PIN didn't match. Try again.")
            # if auth ok but no token (firewall not init'd), don't loop forever — treat as failure once
            if auth.get("ok") and not auth.get("step_up"):
                return ""

    def _lock_number(self, res: SessionResult) -> None:
        try:
            from . import registry as _registry
            if res.number_id and res.tenant_id:
                _registry.lock(res.number_id, tenant_id=res.tenant_id)
        except Exception:  # noqa: BLE001
            pass


# When the firewall verifies the PIN but can't mint a token (not init'd in a degraded env), we still
# proceed (auth proven) but with no token to attach — represented by a sentinel the delegate treats as
# "no token". In a properly-init'd box a real token is always returned.
_NO_TOKEN_BUT_OK = "stepup_ok_no_token"

# S4.5 ELICIT bound: max clarifying questions per command before a graceful give-up (aim-nlu §1.2
# MAX_CLARIFY). Keeps a user who can't supply a slot from being trapped in an ask loop.
_MAX_CLARIFY = 3


# ---------------- speech composition (deterministic; amount ALWAYS read back for money) ----------------
def _rupees(minor: int) -> str:
    try:
        r = int(minor) / 100.0
        return f"₹{r:,.0f}" if r == int(r) else f"₹{r:,.2f}"
    except Exception:  # noqa: BLE001
        return "₹0"


def _consequence_text(action: dict) -> str:
    tool = action["tool"]
    args = action.get("args", {})
    if tool == "ads.set_budget":
        amt = _rupees(args.get("budget_minor", 0))
        ch = args.get("channel", "ads")
        return f"This will set the {ch} budget to {amt} per day."
    if tool == "ads.create_campaign":
        return f"This will create a new ad campaign with a daily budget of " \
               f"{_rupees(args.get('daily_budget_minor', 0))}."
    if tool == "leads.enqueue_calls":
        camp = args.get("campaign") or args.get("campaign_id") or ""
        seg = args.get("segment", "all")
        if camp:
            return f"This will start calling the {seg} leads in the {camp} campaign."
        return f"This will start calling your {seg} leads."
    if tool == "whatsapp.send":
        return f"This will send a WhatsApp message to your {args.get('segment', 'all')} leads."
    if tool == "campaigns.create":
        return "This will launch a new campaign."
    return f"This will run {tool}."


def _confirm_text(action: dict) -> str:
    return "Confirm: " + _consequence_text(action) + " Yes or no?"


def _report_text(action: dict, result: dict) -> str:
    status = result.get("status", "")
    if status in ("awaiting_approval", "parked"):
        return "That needs an extra approval — I've sent it for sign-off."
    if status in ("not_configured", "error"):
        return "I couldn't complete that right now."
    if status in ("killed",):
        return "Operations are paused by admin right now."
    tool = action["tool"]
    args = action.get("args", {})
    if tool == "ads.set_budget":
        return f"Done — budget set to {_rupees(args.get('budget_minor', 0))} per day."
    if tool == "leads.enqueue_calls":
        return f"Done — your {args.get('segment', 'all')} leads are queued for calls."
    return "Done."


def _answer_query(match: dict, ctx: dict) -> str:
    """Read-only answer from context (no gate). Degrade-safe placeholder readout."""
    prof = ctx.get("profile", {}) or {}
    name = ctx.get("business_name") or "your business"
    # The full analytics readout is a context join (leads/revenue/wallet) wired when the brain blob lands;
    # here we answer from whatever profile context is available, never gating.
    return f"Here's the latest for {name}. (Detailed metrics readout connects to analytics.)"


# classify_risk label -> the spec §6 numeric risk level (L0..L4) stored on ai_manager_commands.risk_level.
# safe=0 (read/single-edit), bulk=2 (mass outreach), money=3 (external spend), destructive=4 (delete/refund).
_RISK_LEVEL = {"safe": 0, "bulk": 2, "money": 3, "destructive": 4}


def _risk_to_int(risk: str) -> int:
    return _RISK_LEVEL.get((risk or "").strip().lower(), 0)


def _is_yes(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in ("yes", "yeah", "yep", "yup", "confirm", "go ahead", "do it", "sure", "ok", "okay", "haan")


def _mask_phone(phone: str) -> str:
    """Mask the middle of a caller-ID for audit (keep cc + last 2). NEVER raises."""
    p = (phone or "").strip()
    if len(p) <= 5:
        return "***"
    return p[:3] + "***" + p[-2:]


def _flatten_transcript(turns: list) -> str:
    """Render the in-memory turns into a single 'Role: text' transcript for the session row's
    transcript_text snapshot (the per-turn rows are the structured source of truth). NEVER raises."""
    try:
        lines = []
        for t in (turns or []):
            role = (t.get("role") or "agent").capitalize()
            txt = (t.get("text") or "").strip()
            if txt:
                lines.append(f"{role}: {txt}")
        return "\n".join(lines)[:16000]
    except Exception:  # noqa: BLE001
        return ""


# ---------------- convenience entrypoint (channel-agnostic) ----------------
def run_command_offline(caller_id: str, *, transport: Transport, recorder: Any = None,
                        firewall: Any = None, runner: Optional[Callable] = None,
                        tenant_by_id: Optional[Callable] = None,
                        channel: str = "dashboard") -> SessionResult:
    """Drive the full machine with an injected transport — the offline acceptance entrypoint (spec §9)
    AND the seam every live adapter (LiveKit voice, chat) wraps. NEVER raises."""
    m = CommandMachine(transport, recorder=recorder, firewall=firewall, runner=runner,
                       tenant_by_id=tenant_by_id, channel=channel)
    return m.run(caller_id)
