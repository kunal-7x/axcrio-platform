"""Offline test for comm.brain — the reply-only conversation brain (Wave 2).

Acceptance (COMMUNICATION-MASTER-PLAN §2.4 + WAVE 2):
  * the PRE-LLM keyword gate (precheck) runs FIRST and is FREE:
      - an opt-out word (STOP/unsubscribe/band karo) -> opted_out + short_circuit (NO Groq call)
      - a handoff word (talk to human/call me)        -> needs_human + short_circuit
      - a normal message                              -> noted, NOT short-circuited
  * generate_reply makes EXACTLY ONE Groq call, grounded in the prior call (call_summary /
    next_action / outcome / interest) + the campaign brand + the rolling turns + the persona —
    the grounding is actually injected into the system prompt.
  * a Groq failure / no key -> ReplyPlan.text="" (the webhook still acks 200, no reply). NEVER raises.
  * tools are OFF this wave (tool_calls always empty; tools_enabled() False by default).
  * the brain imports NO caller.py / agent.py (its Groq client is self-contained).

No network. The Groq client (_groq_chat) is monkeypatched. Run: python -m comm.tests.test_brain_offline
"""
from __future__ import annotations

import os
import sys

from comm import brain


def main() -> int:
    fails = []
    calls = {"groq": 0}

    def check(name, cond):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            fails.append(name)

    # ensure tools are OFF (the wave default) regardless of the ambient env
    os.environ.pop("COMM_TOOLS_ENABLED", None)

    # --- (1) the pre-LLM keyword gate (FREE — must NOT call Groq) ---
    pc_stop = brain.precheck("please STOP messaging me")
    check("precheck.optout.action", pc_stop.action == "opted_out")
    check("precheck.optout.short_circuit", pc_stop.short_circuit is True)
    check("precheck.optout.has_reply", bool(pc_stop.reply))

    pc_hindi = brain.precheck("band karo bhai")
    check("precheck.optout.hinglish", pc_hindi.action == "opted_out" and pc_hindi.short_circuit)

    pc_human = brain.precheck("I want to talk to human")
    check("precheck.handoff.action", pc_human.action == "needs_human" and pc_human.short_circuit)

    pc_norm = brain.precheck("haan mujhe 2BHK ka site visit chahiye")
    check("precheck.normal.noted", pc_norm.action == "noted" and pc_norm.short_circuit is False)

    pc_empty = brain.precheck("")
    check("precheck.empty.noted", pc_empty.action == "noted" and pc_empty.short_circuit is False)

    # --- (2) the system prompt actually injects the grounding (the call context) ---
    ctx = {
        "channel": "telegram", "agent_name": "Riya", "company_name": "Acme Homes",
        "product_name": "2BHK flats", "product_summary": "ready-to-move, near the metro",
        "name": "Rahul", "call_summary": "Rahul asked for a site visit this weekend",
        "next_action": "share the brochure + confirm Saturday", "outcome": "interested",
        "interest": "hot",
    }
    sp = brain.build_system_prompt(ctx)
    check("prompt.persona", "Riya" in sp)
    check("prompt.company", "Acme Homes" in sp)
    check("prompt.grounding.call_summary", "site visit this weekend" in sp)
    check("prompt.grounding.next_action", "share the brochure" in sp)
    check("prompt.grounding.outcome", "interested" in sp and "hot" in sp)
    check("prompt.channel_label", "Telegram" in sp)
    check("prompt.channel_suffix", "conversational" in sp.lower())

    # --- (3) generate_reply makes EXACTLY ONE Groq call with the grounded messages ---
    orig_groq = brain._groq_chat
    captured = {"msgs": None}

    def fake_groq(messages, *, max_tokens=220, temperature=0.6, timeout=20.0):
        calls["groq"] += 1
        captured["msgs"] = messages
        return "Bilkul Rahul, Saturday ka site visit fix karte hain — brochure abhi bhejti hoon."

    brain._groq_chat = fake_groq  # type: ignore
    try:
        plan = brain.generate_reply({**ctx, "incoming": "is weekend visit ho sakta hai?",
                                     "turns": [{"role": "assistant", "text": "Hi Rahul!"},
                                               {"role": "user", "text": "haan"}]})
        check("generate.one_groq_call", calls["groq"] == 1)
        check("generate.returns_text", bool(plan.text) and "site visit" in plan.text)
        check("generate.action_replied", plan.action == "replied")
        check("generate.tools_empty", plan.tool_calls == [])
        # the messages handed to Groq: a system msg with grounding + the turns + the incoming
        msgs = captured["msgs"] or []
        check("generate.system_first", msgs and msgs[0]["role"] == "system"
              and "site visit this weekend" in msgs[0]["content"])
        check("generate.incoming_last", msgs and msgs[-1]["role"] == "user"
              and "is weekend visit ho sakta hai?" in msgs[-1]["content"])
        roles = [m["role"] for m in msgs]
        check("generate.turns_included", "assistant" in roles)

        # --- (4) a Groq failure / empty -> text="" (the webhook acks 200, no reply). Never raises.
        def fail_groq(messages, **kw):
            calls["groq"] += 1
            return ""
        brain._groq_chat = fail_groq  # type: ignore
        plan2 = brain.generate_reply({**ctx, "incoming": "hello"})
        check("generate.empty_llm_text_blank", plan2.text == "")
        check("generate.empty_llm_action", plan2.action == "draft_failed")

        # a raising client -> still no raise out of the brain
        def boom_groq(messages, **kw):
            raise RuntimeError("groq down")
        brain._groq_chat = boom_groq  # type: ignore
        try:
            plan3 = brain.generate_reply({**ctx, "incoming": "hi"})
            check("generate.never_raises", plan3.text == "" and plan3.action in ("error", "draft_failed"))
        except Exception:  # noqa: BLE001
            check("generate.never_raises", False)
    finally:
        brain._groq_chat = orig_groq  # type: ignore

    # --- (5) tools OFF default + no caller.py/agent.py import coupling ---
    check("tools.off_default", brain.tools_enabled() is False)
    import comm.brain as _b
    src_modnames = set(getattr(sys.modules.get("comm.brain"), "__dict__", {}).keys())
    # brain must not have pulled caller/agent into its namespace
    check("no_caller_import", "caller" not in src_modnames and "agent" not in src_modnames)

    print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
