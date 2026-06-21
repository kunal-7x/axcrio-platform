import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import prompt
f = {
  'agent_name':'Riya','company_name':'Godrej','product_name':'Godrej Reserve',
  'location':'Devanahalli','voice_gender':'female','goal':'site visit',
  'price':'85 lakh','qualification':'self-use ya investment?',
}
v2 = prompt.build_system_prompt_v2(f)
print('V2LEN', len(v2))
leaks = ['फिर रुको', 'बस इतना, फिर रुको', 'देखो caller को', '(अगर busy']
for L in leaks:
    print('V2_LEAK', repr(L), L in v2)
