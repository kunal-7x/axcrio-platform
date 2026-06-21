cd /opt/famit-agent || exit 1
echo "=== STEP0: live PID binary vs on-disk golden ==="
PID=$(systemctl show famit-agent -p MainPID --value)
echo "MainPID=$PID"
echo -n "disk agent.py: "; md5sum agent.py | cut -c1-12
echo -n "live agent.py: "; sudo md5sum /proc/$PID/root/opt/famit-agent/agent.py 2>/dev/null | cut -c1-12 || echo "(n/a)"
echo "=== STEP1: probe all keys for FULL budget (>=6K headroom) ==="
mapfile -t KEYS < <(grep -E "^GROQ_API_KEY(_[0-9]+)?=" .env | sed "s/^[^=]*=//" | tr -d "\"'")
FULL=()
i=0
for k in "${KEYS[@]}"; do
  i=$((i+1))
  code=$(curl -s --max-time 15 -o /tmp/pp.json -w "%{http_code}" https://api.groq.com/openai/v1/chat/completions -H "Authorization: Bearer $k" -H "Content-Type: application/json" -d "{\"model\":\"meta-llama/llama-4-scout-17b-16e-instruct\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":6000}")
  if [ "$code" = "200" ]; then echo "key#$i FULL"; FULL+=("$k"); else echo "key#$i LOW ($code)"; fi
done
echo "=== full=${#FULL[@]} / total=${#KEYS[@]} ==="
if [ "${#FULL[@]}" -lt 1 ]; then echo "NO_FULL_KEY_avail"; exit 5; fi
cp -p .env ".env.R8s1.$(date +%s)"
grep -vE "^GROQ_API_KEY(_[0-9]+)?=" .env > /tmp/env8
echo "GROQ_API_KEY=${FULL[0]}" >> /tmp/env8
idx=2
for ((j=1;j<${#FULL[@]};j++)); do echo "GROQ_API_KEY_$idx=${FULL[$j]}" >> /tmp/env8; idx=$((idx+1)); done
for k in "${KEYS[@]}"; do
  skip=0
  for f in "${FULL[@]}"; do [ "$k" = "$f" ] && skip=1 && break; done
  [ "$skip" = "0" ] && { echo "GROQ_API_KEY_$idx=$k" >> /tmp/env8; idx=$((idx+1)); }
done
cp -p /tmp/env8 .env
chown famit:famit .env
chmod 660 .env
rm -f /tmp/env8 /tmp/pp.json
sudo systemctl restart famit-agent
sleep 4
echo "=== SVC ==="
systemctl is-active famit-agent
systemctl show famit-agent -p NRestarts -p MainPID --value
echo "=== new index-0 key full? ==="
LK=$(grep -E "^GROQ_API_KEY=" .env | sed "s/^[^=]*=//" | tr -d "\"'")
curl -s --max-time 15 -o /dev/null -w "new GROQ_API_KEY 6K-probe -> %{http_code}\n" https://api.groq.com/openai/v1/chat/completions -H "Authorization: Bearer $LK" -H "Content-Type: application/json" -d "{\"model\":\"meta-llama/llama-4-scout-17b-16e-instruct\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":6000}"
echo "=== brain+voice intact ==="
md5sum agent.py prompt.py
grep -E "EL_STABILITY|ELEVENLABS_VOICE_ID" .env
echo -n "keys in .env: "
grep -cE "^GROQ_API_KEY(_[0-9]+)?=" .env
