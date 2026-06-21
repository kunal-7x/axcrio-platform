import prompt

mini = {"company_name": "Acme", "agent_name": "Riya", "product_name": "X"}
sm = prompt.build_system_prompt(mini)

# section sizes
def chunk(name, start, end=None):
    i = sm.find(start)
    if i < 0:
        print("MISS", name); return
    j = sm.find(end, i) if end else len(sm)
    if j < 0: j = len(sm)
    seg = sm[i:j]
    print(f"{name}: {len(seg)} chars  ({int(len(seg)/3.5)} tok)")

print("TOTAL", len(sm), int(len(sm)/3.5), "tok")
chunk("TOP3", "### TOP 3 RULES", "तुम \"")
chunk("PERSONA+OPENER", "तुम \"", "=== 🧭 असली VETERAN")
chunk("FLOW", "=== 🧭 असली VETERAN", "=== असली इंसान जैसा बोलने")
chunk("SHARED_RULES", "=== असली इंसान जैसा बोलने", "=== CAMPAIGN DATA")
chunk("CAMPAIGN_DATA", "=== CAMPAIGN DATA", None)
print("---")
print("SHARED_RULES_const_chars", len(prompt.SHARED_RULES), int(len(prompt.SHARED_RULES)/3.5))
