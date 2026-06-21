LK=$(grep -E "^GROQ_API_KEY=" /opt/famit-agent/.env | sed "s/^[^=]*=//" | tr -d "\"'")
echo "=== index-0 key remaining-budget headers ==="
curl -s -D - -o /dev/null --max-time 15 https://api.groq.com/openai/v1/chat/completions -H "Authorization: Bearer $LK" -H "Content-Type: application/json" -d "{\"model\":\"meta-llama/llama-4-scout-17b-16e-instruct\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":40}" | grep -iE "x-ratelimit|retry-after"
