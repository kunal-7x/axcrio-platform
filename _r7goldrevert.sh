cd /opt/famit-agent || exit 1
echo "=== BEFORE ==="
md5sum agent.py prompt.py
GA=""
for f in agent.py.PERFECTgolden.20260618-210445 agent.py.A1bak.20260619-022912 agent.py.HEARTbak.1781812510 agent.py.PREgoldrev.* agent.py.PRErev.*; do
  [ -f "$f" ] || continue
  if [ "$(md5sum "$f" | cut -c1-8)" = "5c055a31" ]; then GA="$f"; break; fi
done
if [ -z "$GA" ]; then echo "GOLDEN_5c055a31_NOT_FOUND"; exit 2; fi
echo "restoring PURE golden agent.py from: $GA"
ts=$(date +%s)
cp -p agent.py "agent.py.PREgoldrev.$ts"
cp "$GA" agent.py
chown famit:famit agent.py
echo "=== AFTER ==="
md5sum agent.py prompt.py
echo -n "store/pool/rotation machinery refs in golden agent.py (MUST be 0): "
grep -ciE "PROVIDER_KEYSTORE|GROQ_POOL|PoolLLM|provider_pool|key_store|hot.?store" agent.py
C=/etc/systemd/system/famit-agent.service.d/kernel-outbound.conf
sudo sed -i "/^Environment=EARNER_POOL_LLM=/d" "$C"
if /opt/capsy-agent/.venv/bin/python -m py_compile agent.py prompt.py; then echo COMPILE_OK; else echo COMPILE_FAIL; cp "agent.py.PREgoldrev.$ts" agent.py; chown famit:famit agent.py; exit 3; fi
sudo systemctl daemon-reload
sudo systemctl restart famit-agent
sleep 4
if ! systemctl is-active --quiet famit-agent; then echo "NOT_ACTIVE_AUTOROLLBACK"; cp "agent.py.PREgoldrev.$ts" agent.py; chown famit:famit agent.py; sudo systemctl restart famit-agent; sleep 2; systemctl is-active famit-agent; exit 4; fi
echo "=== SVC OK ==="
systemctl is-active famit-agent
systemctl show famit-agent -p NRestarts -p MainPID --value
echo "=== voice intact ==="
grep -E "EL_STABILITY|ELEVENLABS_VOICE_ID" .env
echo -n "fresh .env GROQ keys: "
grep -cE "^GROQ_API_KEY(_[0-9]+)?=" .env
echo "=== drop-in ==="
grep -hE "GROQ_MAX_TOKENS|EARNER_POOL_LLM|KERNEL_OUTBOUND" "$C"
echo "=== 429 in last 1m (real call is the proof) ==="
sudo journalctl -u famit-agent --since "1 min ago" --no-pager 2>/dev/null | grep -ciE "429|tokens per day"
