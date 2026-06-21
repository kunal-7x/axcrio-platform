echo "=== STATE ==="
md5sum /opt/famit-agent/agent.py /opt/famit-agent/prompt.py
grep -hE "GROQ_MAX_TOKENS|EARNER_POOL_LLM|KERNEL_OUTBOUND" /etc/systemd/system/famit-agent.service.d/*.conf
systemctl is-active famit-agent
systemctl show famit-agent -p NRestarts -p MainPID --value
echo "=== 429 count last 30m ==="
sudo journalctl -u famit-agent --since "30 min ago" --no-pager 2>/dev/null | grep -ciE "429|tokens per day"
echo "=== NON-429 errors last 30m (the real bug if any) ==="
sudo journalctl -u famit-agent --since "30 min ago" --no-pager 2>/dev/null | grep -iE "traceback|exception|Error|failed" | grep -viE "tokens per day|429|rate_limit" | tail -25
echo "=== per-turn behavior last 30m ==="
sudo journalctl -u famit-agent --since "30 min ago" --no-pager 2>/dev/null | grep -iE "turn\[user\]|turn\[assistant\]|failed to generate|finish_reason|empty|closing agent|process exit|registered worker|llm_node|generating|api_key|GROQ|pool|_next_groq" | tail -60
