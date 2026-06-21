import prompt

# minimal campaign (just names) -> measures the FIXED scaffolding size
mini = {"company_name": "Acme", "agent_name": "Riya", "product_name": "X"}
sm = prompt.build_system_prompt(mini)
print("MINI_CHARS", len(sm))
print("MINI_TOK_div3_5", int(len(sm) / 3.5))

# where does 'site visit' / 'BHK' appear in the insurance scaffold?
ins = dict(prompt.GODREJ_FIELDS); ins["vertical"] = "insurance"; ins["product_name"]="Term cover"
ins.pop("appointment_options", None); ins.pop("goal", None)
si = prompt.build_system_prompt(ins)
scaf = si.split("=== CAMPAIGN DATA")[0]
for needle in ["site visit", "BHK"]:
    idx = scaf.find(needle)
    if idx >= 0:
        print("LEAK", repr(needle), "->", repr(scaf[max(0,idx-40):idx+40]))
    else:
        print("LEAK", repr(needle), "-> none")
