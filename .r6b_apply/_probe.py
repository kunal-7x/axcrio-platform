import prompt, re

s = prompt.build_system_prompt(prompt.GODREJ_FIELDS)
print("CHARS", len(s))
print("APPROX_TOK_div4", len(s) // 4)
# devanagari-aware token proxy the kernel uses (chars/3.5)
print("APPROX_TOK_div3_5", int(len(s) / 3.5))

# byte-identical contracts (earner surface)
print("V2EQ_GODREJ", prompt.build_system_prompt_v2(prompt.GODREJ_FIELDS) == prompt.build_system_prompt(prompt.GODREJ_FIELDS))
print("V2EQ_EMPTY", prompt.build_system_prompt_v2({}) == prompt.build_system_prompt({}))
print("RP_DEFAULT", prompt.resolve_providers({}) == prompt._DEFAULT_PROVIDERS)
print("SYSPROMPT_OK", isinstance(prompt.SYSTEM_PROMPT, str) and len(prompt.SYSTEM_PROMPT) > 1000)

# genius arc present
arc_markers = ["NAAM CONFIRM", "DISCOVER", "CURIOSITY", "OBJECTION", "BUYING-SIGNAL",
               "ISOLATE", "feel-felt-found", "trial-close", "veteran".upper()]
for m in arc_markers:
    print("ARC", m, m in s)

# greeting: no pre-name before confirm (opener_section state machine present, no "hello {name}" pre-confirm)
print("GREET_STATEMACHINE", "OPENING STATE MACHINE" in s)
print("GREET_NO_PRENAME_RULE", "दोबारा कभी greet मत करना" in s)

# RE-bias removed from persona scaffolding (campaign DATA may still say BHK — that's data, fine)
# Check the FIXED scaffolding (everything before CAMPAIGN DATA) has no RE-locked persona tokens.
scaffold = s.split("=== CAMPAIGN DATA")[0]
for tok in ["EOI", "inventory", "BHK", "per sq ft", "experience center", "DUAL-OFFER", "site visit या presentation"]:
    print("NORE_SCAFFOLD", repr(tok), tok not in scaffold)

# numbers/units rules present
print("RULE_RUPEES", "rupees" in s and "square feet" in s)
print("RULE_BAN_SYMBOLS", "₹" in s and '"sq. ft"' in s)  # they appear in the BAN list (instructing the LLM)

# cross-vertical: a NON-real-estate campaign renders the vertical block + correct goal, NO RE persona
ins = dict(prompt.GODREJ_FIELDS)
ins["vertical"] = "insurance"
ins["product_name"] = "Term Life cover"
ins.pop("appointment_options", None); ins.pop("goal", None)
si = prompt.build_system_prompt(ins)
print("INS_TILT", "मिज़ाज (insurance)" in si)
print("INS_GOAL_ADVISOR", "advisor" in si)
si_scaffold = si.split("=== CAMPAIGN DATA")[0]
print("INS_NO_SITEVISIT_FLOW", "site visit" not in si_scaffold.replace("मिज़ाज", ""))

# generic vertical (no `vertical`) renders NO tilt block, pure campaign-driven
gen = dict(prompt.GODREJ_FIELDS)
sg = prompt.build_system_prompt(gen)
print("GENERIC_NO_TILT", "इस call का मिज़ाज" not in sg)
