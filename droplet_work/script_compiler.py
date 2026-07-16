"""script_compiler — P7 Script Studio 2.0: compile typed script BLOCKS down to the campaign fields
that build_system_prompt (prompt.py) already consumes.

THE GUARDRAIL: the live voice agent renders every call from the flat `fields` dict via
build_system_prompt(fields). Script Studio 2.0 lets an operator author a script as ordered, typed
blocks (Greeting / Qualification / Discovery / Objection / FAQ / Closing / Follow-up / Escalation /
Variables / Conditions). Rather than change the agent or prompt.py, we COMPILE those blocks DOWN to
the SAME consumed fields (persona, qualification, qualifying_questions, objections, objection_bank,
goal, appointment_options). So a v2 campaign produces a normal `fields` dict the existing earner
reads unchanged — zero live-path risk. Compilation only runs when a campaign opts in
(fields.script_studio_v2), so legacy campaigns are byte-identical.

Pure stdlib, import-guarded by the caller, NEVER raises (returns {} on any problem). Blocks whose
type has no prompt-consumed target (followup / escalation / variables / condition) are builder +
simulator metadata only — they do NOT alter the compiled prompt.
"""
from __future__ import annotations

import re

# Variables filled at CALL TIME by the agent (e.g. {{lead_name}}). The compiler must NEVER
# substitute these — they pass through to the live prompt untouched.
_RUNTIME_VARS = {"lead_name", "name", "phone", "company", "agent", "today", "time"}

# Per-field caps mirror prompt.py's lean-render expectations (it clips again, but we keep payloads
# bounded so a runaway block can't bloat a campaign field).
_CAPS = {"persona": 600, "qualification": 300, "goal": 200}
_LIST_CAPS = {"qualifying_questions": 12, "objections": 20, "objection_bank": 20, "appointment_options": 8}


def _s(v) -> str:
    return str(v).strip() if v is not None else ""


def _sub(text: str, variables: dict) -> str:
    """Substitute author-defined {{var}} placeholders, leaving runtime/unknown ones intact (so the
    agent's {{lead_name}} etc. still reach the live prompt). Never raises."""
    if not text or not variables:
        return text or ""
    def repl(m):  # noqa: ANN001
        key = m.group(1).strip()
        if key in variables and key not in _RUNTIME_VARS:
            return str(variables[key])
        return m.group(0)
    try:
        return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", repl, text)
    except Exception:  # noqa: BLE001
        return text


def compile_blocks(blocks, variables=None) -> dict:
    """Compile ordered, typed blocks -> a dict of campaign-field OVERRIDES (only keys that have
    content, so unauthored block types never blank an existing field). Never raises."""
    variables = variables if isinstance(variables, dict) else {}
    out: dict = {}
    if not isinstance(blocks, list):
        return out
    quals: list = []
    objs: list = []
    faqs: list = []
    persona_bits: list = []
    appt: list = []
    goal = ""
    qualification = ""
    try:
        for b in blocks:
            if not isinstance(b, dict) or b.get("enabled") is False:
                continue
            btype = _s(b.get("type")).lower()
            text = _sub(_s(b.get("text")), variables)
            items = [_sub(_s(x), variables) for x in (b.get("items") or []) if _s(x)]
            qa = [
                {"q": _sub(_s(p.get("q")), variables), "a": _sub(_s(p.get("a")), variables)}
                for p in (b.get("qa") or [])
                if isinstance(p, dict) and (_s(p.get("q")) or _s(p.get("a")))
            ]
            options = [_sub(_s(x), variables) for x in (b.get("options") or []) if _s(x)]

            if btype == "greeting":
                if text:
                    persona_bits.append(text)
            elif btype == "qualification":
                if text and not qualification:
                    qualification = text
                quals.extend(items)
            elif btype == "discovery":
                quals.extend(items)
                if text:
                    quals.append(text)
            elif btype == "objection":
                objs.extend(qa)
            elif btype == "faq":
                faqs.extend(qa)
            elif btype == "closing":
                g = _sub(_s(b.get("goal")), variables) or text
                if g and not goal:
                    goal = g
                appt.extend(options)
            # followup / escalation / variables / condition -> builder + simulator metadata only.

        if persona_bits:
            out["persona"] = " ".join(persona_bits)[: _CAPS["persona"]]
        if qualification:
            out["qualification"] = qualification[: _CAPS["qualification"]]
        if quals:
            out["qualifying_questions"] = quals[: _LIST_CAPS["qualifying_questions"]]
        if objs:
            out["objections"] = objs[: _LIST_CAPS["objections"]]
        if faqs:
            out["objection_bank"] = faqs[: _LIST_CAPS["objection_bank"]]
        if goal:
            out["goal"] = goal[: _CAPS["goal"]]
        if appt:
            out["appointment_options"] = appt[: _LIST_CAPS["appointment_options"]]
    except Exception:  # noqa: BLE001
        return {}
    return out
