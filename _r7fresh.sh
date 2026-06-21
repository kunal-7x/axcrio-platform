ENV=/opt/famit-agent/.env
echo "=== probing keys for ~2K headroom (real lean-turn size) ==="
mapfile -t KEYS < <(grep -E "^GROQ_API_KEY(_[0-9]+)?=" "$ENV" | sed "s/^[^=]*=//" | tr -d "\"'")
FRESH=()
EXH=0
i=0
for k in "${KEYS[@]}"; do
  i=$((i+1))
  code=$(curl -s --max-time 12 -o /dev/null -w "%{http_code}" https://api.groq.com/openai/v1/chat/completions -H "Authorization: Bearer $k" -H "Content-Type: application/json" -d "{\"model\":\"meta-llama/llama-4-scout-17b-16e-instruct\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":2000}")
  if [ "$code" = "200" ]; then echo "key#$i FRESH"; FRESH+=("$k"); else echo "key#$i EXHAUSTED ($code)"; EXH=$((EXH+1)); fi
done
echo "=== fresh=${#FRESH[@]} exhausted=$EXH total=${#KEYS[@]} ==="
if [ "${#FRESH[@]}" -lt 1 ]; then echo "ALL_EXHAUSTED_today"; exit 5; fi
cp -p "$ENV" "$ENV.R7FRESH.$(date +%s)"
grep -vE "^GROQ_API_KEY(_[0-9]+)?=" "$ENV" > /tmp/envnew
echo "GROQ_API_KEY=${FRESH[0]}" >> /tmp/envnew
idx=2
for ((j=1;j<${#FRESH[@]};j++)); do
  echo "GROQ_API_KEY_$idx=${FRESH[$j]}" >> /tmp/envnew
  idx=$((idx+1))
done
cp -p /tmp/envnew "$ENV"
chown famit:famit "$ENV"
chmod 660 "$ENV"
C=/etc/systemd/system/famit-agent.service.d/kernel-outbound.conf
sudo sed -i "s/^Environment=EARNER_POOL_LLM=.*/Environment=EARNER_POOL_LLM=0/" "$C"
sudo systemctl daemon-reload
sudo systemctl restart famit-agent
sleep 3
echo "=== SVC ==="
systemctl is-active famit-agent
systemctl show famit-agent -p NRestarts --value
LK=$(grep -E "^GROQ_API_KEY=" "$ENV" | sed "s/^[^=]*=//" | tr -d "\"'")
curl -s --max-time 12 -o /dev/null -w "live primary key 2K-probe -> %{http_code}\n" https://api.groq.com/openai/v1/chat/completions -H "Authorization: Bearer $LK" -H "Content-Type: application/json" -d "{\"model\":\"meta-llama/llama-4-scout-17b-16e-instruct\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":2000}"
echo "=== brain+voice intact ==="
md5sum /opt/famit-agent/agent.py /opt/famit-agent/prompt.py
grep -E "EL_STABILITY|ELEVENLABS_VOICE_ID" "$ENV"
echo -n "fresh GROQ keys in .env now: "
grep -cE "^GROQ_API_KEY(_[0-9]+)?=" "$ENV"
