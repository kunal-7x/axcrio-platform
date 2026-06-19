# W-SURGICAL-A2 — AI-self-label removal DEPLOYED (code + the one campaign DATA fix)

**Wave:** W-SURGICAL-A2 (the gated follow-up that completes W-SURGICAL-A) ·
**Built/deployed:** 2026-06-18 · **Re-verified live on box:** 2026-06-19
**Box:** `famit@168.144.153.145` · key `~/.ssh/do-blr-test/id_ed25519`
**Live earner:** `/opt/famit-agent/agent.py` + `/opt/famit-agent/prompt.py` · service `famit-agent` ·
`KERNEL_OUTBOUND=0` (systemd drop-in `kernel-outbound.conf`, NOT `.env`) — UNCHANGED.

## VERDICT: **DEPLOY COMPLETE AND VERIFIED.** All gates passed. No rollback needed. No real PSTN. `aim-voice-agent` never touched.

W-SURGICAL-A halted PRE-DEPLOY because the patched code was correct but ONE live campaign JSON
(`c17e55e9f3.json`, Shapoorji Pallonji) stored its OWN `ai_disclosure="Shapoorji Pallonji की एक AI assistant"`
which overrode the clean code default. W-SURGICAL-A2 fixes that single saved field AND ships the authorized
code strings, reaching an **airtight 100%-clean canary (AI-self-label hits = 0 across all 15 campaigns)** —
with the **voice path byte-identical** (TTS/STT/LLM/VAD/turn-detection/opener-mechanics untouched), `.env`
untouched, and `KERNEL_OUTBOUND` still OFF.

---

## Timestamps (UTC)
- Earner-gate read (BEFORE): famit-agent active; golden md5s `98655dbf` / `fb87ea56`; port 8090=200, 8091=200.
- Campaign DATA fix applied + backed up (`c17e55e9f3.json.AIbak.1781807526`) — carried in from PREP, re-confirmed intact at deploy.
- Code patch applied (agent.py :218; prompt.py disclosure-string hunks) + `py_compile` clean.
- Deploy = copy patched `.py` to `/opt/famit-agent/` + `systemctl restart famit-agent`.
- Earner-gate read (AFTER): new MainPID **4042950**; active; worker "capsy" re-registered; 8090=200, 8091=200; journal-since-restart = ZERO errors.
- 15-campaign canary against the LIVE deployed code: **AI-SELF-LABEL HITS = 0.**
- Live re-verification on box: **2026-06-19** (this file's confirmation pass) — all facts below re-read from the box, not memory.

## md5 — OLD golden -> NEW deployed (LIVE, re-confirmed 2026-06-19)
| file | OLD (golden, before) | NEW (deployed, live now) |
|------|----------------------|--------------------------|
| `/opt/famit-agent/agent.py`  | `98655dbfc71d5c3da36bcfe3f848082c` | `5c055a31b2608d6381ab475af1e64761` |
| `/opt/famit-agent/prompt.py` | `fb87ea56ee7f7688b6af712a52627e72` | `660f1ec666329094e9d90ca137312e70` |

(Brief golden refs: agent.py `98655dbf`, prompt.py `fb87ea56`. Both confirmed replaced by the patched md5s above.)

## Campaign DATA fix — OLD -> NEW (the root-cause defect from W-SURGICAL-A)
- **File:** `/opt/famit-agent/var/campaigns/c17e55e9f3.json` = **Codename Joy 3.0 / Shapoorji Pallonji Real Estate**
  (the ONLY one of 15 campaigns with a non-null `ai_disclosure`).
- **Field `ai_disclosure`:**
  - OLD (self-label, the defect): `'Shapoorji Pallonji की एक AI assistant'`
  - NEW (clean, deployed): `'Shapoorji Pallonji Real Estate से'`
- **Backup:** `/opt/famit-agent/var/campaigns/c17e55e9f3.json.AIbak.1781807526`
  — verified on box to CONTAIN the ORIGINAL self-label string (clean restore path).
- Why this mattered: at `prompt.py` the stored `custom_disc = ai_disclosure` WINS over `disc_default`
  (`disc_phrase = custom_disc or disc_default`), so the code-only patch alone could not silence this campaign —
  the saved field had to be corrected. It is a DATA defect, fixed in DATA; no behavioral logic changed.
- Note: 3 OTHER campaigns also carry "Shapoorji Pallonji" as a company name but had `ai_disclosure: null`,
  so they fall through to the clean code default and render clean automatically.

## Code diffs (re-verified at deploy vs golden)
### agent.py — exactly ONE line
- `:218` — the disclosure/self-label DEFAULT string only.
- **Voice-path ranges diff EMPTY:** `550-670` (TTS / AgentSession / STT / LLM / VAD / turn_detection / endpointing)
  and `695-890` (`session.say` / `session.start` opener mechanics) — byte-identical to golden.

### prompt.py — only the authorized disclosure/self-label TEXT strings
- Lines `94, 99, 208, 225-226, 358, 361-362, 683` — disclosure-text / self-label strings only (all prompt TEXT, zero voice).
- Intent of `:358`: golden `disc_default = f"{company} की एक AI assistant"` -> clean `f"{company} से"`.
- `py_compile` both files = OK.

## Proof: .env + VOICE constructors UNTOUCHED (re-read live 2026-06-19)
- **`.env` (live):** `EL_STABILITY=0.55` · `OPENER_ALREADY_SAID=1` · `OPENER_IN_CTX=0`. Unchanged. No TTS/prosody/
  opener-mechanics/turn-taking key touched.
- **`KERNEL_OUTBOUND=0`** — set via systemd drop-in `/etc/systemd/system/famit-agent.service.d/kernel-outbound.conf`
  (NOT in `.env`); `systemctl show -p Environment` resolves `KERNEL_OUTBOUND=0`. Brain stays the legacy worker; OFF.
- agent.py voice-constructor ranges byte-identical golden vs deployed (TTS / VoiceSettings / sarvam.STT / groq.LLM /
  AgentSession / opener `session.say`) — the two brain anchors fall OUTSIDE every voice span.

## Earner gate — BEFORE vs AFTER
- **BEFORE:** famit-agent active; port 8090 `/` = 200, port 8091 `/` = 200.
- **AFTER (live now):** new MainPID **4042950**, active, worker "capsy" re-registered; 8090 = 200, 8091 = 200;
  journal strictly since restart = ZERO errors. (The exit-255 lines in the log were the OLD pid 4024906 shutting
  down, not the new worker.) **No real ring placed** (no real PSTN/minutes spent).

## Canary verdict — self-label gone across ALL campaigns?  **YES.**
Full **15-campaign render against the LIVE deployed code: AI-SELF-LABEL HITS = 0.** The 16 residual token
substrings are TWO benign non-self-ID strings only:
- anti-robotic coaching line `इनके बिना robotic लगता है`
- AGARO product-objection string `"Machine heating"`

Live openers after the fix (no self-ID anywhere):
- Shapoorji -> `मैं Riya, Shapoorji Pallonji Real Estate से बोल रही हूँ…`
- AGARO -> `मैं Riya, AGARO से बोल रही हूँ…`
- Surat Homes -> `मैं Riya, Surat Homes से बोल रही हूँ…`

## Final live state (re-confirmed on box 2026-06-19)
- `famit-agent` active, MainPID 4042950; both ports 200.
- Patched md5s live (`5c055a31…` agent.py / `660f1ec6…` prompt.py).
- Campaign `c17e55e9f3.json` `ai_disclosure = 'Shapoorji Pallonji Real Estate से'` (fixed); backup intact.
- `aim-voice-agent` (the inbound voice service) **NOT restarted, NOT touched** at any point.
- `.env` untouched; `KERNEL_OUTBOUND=0`.

## Rollback (one command — restores CODE + the campaign JSON; nothing to roll back now)
```
ssh -i ~/.ssh/do-blr-test/id_ed25519 famit@168.144.153.145 \
 'cp /opt/famit-agent/agent.py.WOUTbak.1781793303  /opt/famit-agent/agent.py && \
  cp /opt/famit-agent/prompt.py.AIFIXbak.1781801811 /opt/famit-agent/prompt.py && \
  cp /opt/famit-agent/var/campaigns/c17e55e9f3.json.AIbak.1781807526 /opt/famit-agent/var/campaigns/c17e55e9f3.json && \
  sudo systemctl restart famit-agent && \
  md5sum /opt/famit-agent/agent.py /opt/famit-agent/prompt.py'
```
Expect after rollback: `98655dbf… agent.py` / `fb87ea56… prompt.py`, and the campaign `ai_disclosure` back to
`'Shapoorji Pallonji की एक AI assistant'`. (KERNEL_OUTBOUND stays 0; `.env` and `aim-voice-agent` are not involved.)
