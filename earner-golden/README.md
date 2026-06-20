# EARNER-GOLDEN — restore point for the working voice brain (2026-06-20, ROUND-7 FINAL)

This is a **secrets-stripped snapshot** of the live, founder-grade working outbound voice
earner brain. It is the tagged restore point. **No keys, no `.env` values are in this repo** —
only the code + an `ENV.example.md` listing the var NAMES (empty values).

## The working state (what's LIVE on the box)
- Box: `famit@168.144.153.145`, `/opt/famit-agent/`, service `famit-agent` (systemd).
- **`agent.py` md5 `10662d32fc857d88c62c7cc2549134cb`** — ROUND-6 penalty brain + the additive
  R7 GROQ_POOL rotation block (OFF path byte-identical to the penalty brain `ee3e4b5e`).
- **`prompt.py` md5 `b99c25eaa9dc80edffb9ce615d5892c7`** — ROUND-6 brain + the R7 prompt-leak
  fix (stage-directions wrapped `[...]`=SILENT) + the R7 PROSE-REWRITE that cures the
  structured-output `"key": "value"` degeneration (the flow/opener/rules rewritten from
  numbered/quoted/bracketed scaffolding into natural Hindi prose; explicit no-JSON/no-labels
  guard + never-give-up-on-budget closer).
- **`llm_router/`** — the shared least-used pool + per-key 429 cooldown + instant re-pick
  (`GROQ_POOL`, `PoolLLM`). The earner wires it behind `EARNER_POOL_LLM=1`, sticky-per-call.
- **systemd drop-in** = `kernel-outbound.conf` here. Key flags: `EARNER_POOL_LLM=1`,
  `KERNEL_OUTBOUND=0`, `GROQ_MAX_TOKENS=220`, `GROQ_FREQ_PENALTY=0.5`, `GROQ_PRES_PENALTY=0.3`.
- **14 `GROQ_API_KEY*` in `.env`** (14 multi-account keys = ~7M tokens/day) + 15 panel hot-store
  keys decrypted via `PROVIDER_KEYSTORE_SECRET` → pool `available_count` = 29.
- `.env` perms MUST stay **`famit:famit 660`** (root:root/600 crash-loops the service).

## THE VOICE LAW (never violate)
Never touch the TTS constructor / `.env` `EL_STABILITY=0.55` / `voice_id QTKSa2Iyv0yoxvXY2V8a`.
TTS-span md5 (`agent.py` ll.1161-1185) MUST be `7b36c4f9d57cd76d5116d93156560dcb` before==after
every deploy. One box change → founder real-call test → one-command rollback.

## What was FIXED (Round-7)
1. **Silence after 1 turn** — was the Groq FREE-TIER daily token limit (500k/day/account) exhausted,
   NOT the brain. Fixed by 14 multi-account keys (+ 15 panel keys via the pool).
2. **"हाँ हाँ हाँ" repetition garbage** — model degeneration; cured by `GROQ_FREQ_PENALTY=0.5` +
   `GROQ_PRES_PENALTY=0.3` (the penalty brain).
3. **Rotation / instant 429-fallback** — `EARNER_POOL_LLM=1` wires `GROQ_POOL`: sticky key per call,
   switches mid-call only on a 429 (no dead air). 29-key concurrency capacity.
4. **Prompt-leak** — the LLM occasionally VOICED Hindi stage-directions; the flow block now marks
   `"..." = बोलो; [ ... ] = SILENT`, every meta-instruction wrapped in `[...]`.

## RESTORE — from this snapshot to the box (one push)
```bash
# from a checkout of this golden branch, on a machine with the box SSH key:
KEY=~/.ssh/do-blr-test/id_ed25519
scp -i $KEY agent.py prompt.py famit@168.144.153.145:/tmp/
scp -i $KEY llm_router/*.py famit@168.144.153.145:/tmp/llm_router/
scp -i $KEY kernel-outbound.conf famit@168.144.153.145:/tmp/
ssh -i $KEY famit@168.144.153.145 '
  cd /opt/famit-agent
  # GUARD: refuse if TTS span would change
  sudo cp -p agent.py /tmp/agent.prev.py
  sudo install -o famit -g famit -m 644 /tmp/agent.py agent.py
  sudo install -o famit -g famit -m 644 /tmp/prompt.py prompt.py
  sudo install -o famit -g famit -m 644 /tmp/llm_router/*.py llm_router/
  sudo cp /tmp/kernel-outbound.conf /etc/systemd/system/famit-agent.service.d/kernel-outbound.conf
  # assert voice law
  test "$(sed -n "1161,1185p" agent.py | md5sum | cut -d" " -f1)" = "7b36c4f9d57cd76d5116d93156560dcb" || { echo "TTS SPAN CHANGED — ABORT"; exit 1; }
  test "$(md5sum agent.py | cut -d" " -f1)" = "10662d32fc857d88c62c7cc2549134cb"
  test "$(md5sum prompt.py | cut -d" " -f1)" = "b99c25eaa9dc80edffb9ce615d5892c7"
  sudo systemctl daemon-reload && sudo systemctl restart famit-agent
  systemctl is-active famit-agent
'
```
NOTE: this restores CODE only. `.env` (keys) is NEVER in git — it already lives on the box.

## RESTORE — on-box golden dir (fastest; no laptop needed)
A `_GOLDEN_ROUND7/` dir on the box holds these exact files. One command:
```bash
sudo /opt/famit-agent/_GOLDEN_ROUND7/restore.sh
```
(See that script — it copies the golden agent.py/prompt.py/llm_router + drop-in back, asserts the
md5s + the TTS span, fixes perms, daemon-reload + restart, prints is-active.)

## Founder test
Make one real outbound call. Expect: AI RESPONDS every turn (no silence), COMPLETE sentences,
NO "हाँ हाँ" repetition loop, NEVER speaks a Hindi stage-direction, and the SAME voice as before.
