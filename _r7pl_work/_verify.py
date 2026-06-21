import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import prompt

d = prompt.resolve_providers({})
print('RESOLVE_DEFAULT', d)

f = {
  'agent_name':'Riya','company_name':'Godrej','product_name':'Godrej Reserve',
  'location':'Devanahalli','landmark':'Airport','lead_name':'Rohan',
  'voice_gender':'female','goal':'site visit',
  'price':'85 lakh','credibility':'RERA approved','eoi':'pre-launch','value':'best ROI',
  'qualification':'aap self-use ke liye dekh rahe hain ya investment?',
}
sp = prompt.build_system_prompt(f)
print('SYSLEN', len(sp))

# Every meta-directive must now be INSIDE a [...] bracket. Verify the previously-leaking
# bare phrases no longer appear as un-bracketed speech.
leaks = ['फिर रुको', 'बस इतना, फिर रुको', 'देखो caller को', '(अगर busy']
for L in leaks:
    present = L in sp
    print('LEAK_PRESENT', repr(L), present)

# Confirm the silent-instruction reading-rule header is present in the flow block
print('READING_RULE', 'SILENT' in sp)
