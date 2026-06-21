# RESTORE-SYSTEM — revert the working VOICE BRAIN in seconds

> Founder rule #1: the **voice is FIXED and working** (dead-air gone, no 'haan'
> loop, key-spread multi-key architecture, `EL_STABILITY=0.55`). This file is the
> seconds-to-revert system so any future brain break reverts INSTANTLY — whether
> the break is already deployed or you're rebuilding a fresh box.

Snapshot taken: **2026-06-21**. Box: `famit-livekit` (`168.144.153.145`), service
`famit-agent.service`, app dir `/opt/famit-agent`.

## The golden brain (byte-locked — the "voice law")
| artifact | md5 |
|----------|-----|
| `agent.py`  | `11a865feb758b25a20cc3e0c291b4ad2` |
| `prompt.py` | `4ae81ac64d2faf5da225b4b5965978e5` |
| TTS span (`agent.py` lines 596-616, the `elevenlabs.TTS(...)` block) | `4ada9f1e0cb8304ea69194ef38f0ae25` |

Voice tuning (non-secret): `EL_STABILITY=0.55`, `EL_SIMILARITY=0.80`,
`EL_SPEED=1.08`, model `eleven_flash_v2_5`, voice_id `QTKSa2Iyv0yoxvXY2V8a`,
`GROQ_MAX_TOKENS=90`, `KERNEL_OUTBOUND=0`.

There are **two** independent copies of this golden brain, so a restore never
depends on a single point of failure:
1. **On the box:** `/opt/famit-agent/_GOLDEN_R9_20260621/` (instant restore).
2. **On GitHub:** branch `earner-golden`, dir `earner-golden/` on
   `kunal-7x/axcrio-platform` (secrets-stripped; for a fresh box).

---

## CASE A — "It's deployed and the voice broke" (revert in ~5 seconds)

SSH to the box and run the one command. It backs up the current files, copies the
golden brain in, **asserts every md5 + the TTS span + `EL_STABILITY=0.55` BEFORE
restarting, and ABORTS on any mismatch** (never restarts a non-golden brain):

```bash
ssh -i ~/.ssh/do-blr-test/id_ed25519 famit@168.144.153.145
sudo /opt/famit-agent/_GOLDEN_R9_20260621/restore.sh
```

What it does: backs up live files to `*.preR9restore.<ts>` → installs golden
`agent.py` / `prompt.py` / `llm_router/*.py` + the systemd drop-in → asserts the 3
md5s + `EL_STABILITY=0.55` → `py_compile` → `daemon-reload` + `restart
famit-agent`. Then **make ONE real call to confirm** (only a real call is truth).

Manual md5 self-check at any time:
```bash
cd /opt/famit-agent
md5sum agent.py prompt.py          # expect 11a865fe... / 4ae81ac6...
sed -n '596,616p' agent.py | md5sum  # expect 4ada9f1e...
grep ^EL_STABILITY= .env            # expect EL_STABILITY=0.55
```

---

## CASE B — "Fresh box / the on-box golden is gone" (rebuild from GitHub)

The `earner-golden` branch holds a secrets-stripped copy. Secrets are NOT in git —
the real keys live only in `/opt/famit-agent/.env` (provided out-of-band).

```bash
# 1. get the golden brain from GitHub
git clone -b earner-golden https://github.com/kunal-7x/axcrio-platform.git /tmp/golden
cd /tmp/golden/earner-golden

# 2. put the .env in place (real keys — out-of-band, NEVER in git).
#    earner.env.example lists every key NAME you must fill (+ the safe voice values).

# 3. install the brain onto the box
sudo mkdir -p /opt/famit-agent/llm_router /etc/systemd/system/famit-agent.service.d
sudo install -o famit -g famit -m 644 agent.py  /opt/famit-agent/agent.py
sudo install -o famit -g famit -m 644 prompt.py /opt/famit-agent/prompt.py
sudo install -o famit -g famit -m 644 llm_router/*.py /opt/famit-agent/llm_router/
sudo cp kernel-outbound.conf /etc/systemd/system/famit-agent.service.d/kernel-outbound.conf
sudo cp famit-agent.service  /etc/systemd/system/famit-agent.service   # base unit (reads .env)

# 4. assert the voice law (must match before you start it)
cd /opt/famit-agent
md5sum agent.py prompt.py            # 11a865fe... / 4ae81ac6...
sed -n '596,616p' agent.py | md5sum  # 4ada9f1e...
grep ^EL_STABILITY= .env || echo 'EL_STABILITY=0.55' | sudo tee -a .env

# 5. start
sudo systemctl daemon-reload && sudo systemctl restart famit-agent
systemctl is-active famit-agent
```
Then make ONE real call to confirm.

> Tip: once a box has `/opt/famit-agent/_GOLDEN_R9_20260621/` again, future reverts
> are just CASE A (`sudo .../restore.sh`).

---

## What's where (the durable copies)
- On box: `/opt/famit-agent/_GOLDEN_R9_20260621/{agent.py,prompt.py,llm_router/,
  kernel-outbound.conf,famit-agent.service,earner.env.example→ENV.example,README.md,restore.sh}`
- GitHub: branch `earner-golden`, dir `earner-golden/` (same set, secrets-stripped,
  `earner.env.example` = key NAMES only). `gitleaks protect --staged = 0`.

## Hard rules (don't break the earner)
- The voice (`agent.py` + the TTS span + `.env` voice values) is **byte-locked**.
  Brain work = `prompt.py` ONLY; keep `agent.py` and the voice settings identical.
- Offline-green ≠ working. Only a **real call** proves the brain.
- One box-mutating change at a time, with this restore as the immediate revert path.
