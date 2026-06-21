import importlib.util
spec = importlib.util.spec_from_file_location("pcand", "/tmp/prompt_r7pl_candidate.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print("IMPORT_BOX_OK")
print("RESOLVE", m.resolve_providers({}))
f = {'agent_name':'Riya','company_name':'Godrej','product_name':'Godrej Reserve',
     'location':'Devanahalli','voice_gender':'female','goal':'site visit',
     'qualification':'self-use ya investment?'}
sp = m.build_system_prompt(f)
for L in ['फिर रुको','बस इतना, फिर रुको','देखो caller को','(अगर busy']:
    print("LEAK", repr(L), L in sp)
