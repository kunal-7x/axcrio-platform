# LIVE VOICE EARNER — RESTORE SNAPSHOT (2026-06-21)

Secrets-stripped, byte-exact snapshot of the **working** voice earner taken
from the live box `/opt/famit-agent` **before** any voice-brain change.
This is the founder's #1 safety net: the voice was FIXED and working
(dead-air gone, no 'haan' loop, key-spread architecture). If a brain change
breaks the voice, restore from here.

## What this is / is NOT
- IS: a read-only copy of the `*.py` source on the box at snapshot time.
- IS NOT: the `.env` / secrets. Those were deliberately NOT copied and must
  NEVER be committed. The box keeps its own `.env`; restoring source does not
  change secrets.

## Gold-copy integrity (verified at snapshot time, MD5)
| file       | md5                                |
|------------|------------------------------------|
| agent.py   | `11a865feb758b25a20cc3e0c291b4ad2`  |
| prompt.py  | `4ae81ac64d2faf5da225b4b5965978e5`  |

These two are the live earner per the founder. `agent.py = 11a865fe` and
`prompt.py = 4ae81ac6` == the working voice. After restoring, re-check md5 on
the box to confirm byte-identity, then a REAL outbound test call is the only
true proof.

## Box / access
- Box: `famit@168.144.153.145`  path `/opt/famit-agent`
- Read: `ssh -i ~/.ssh/do-blr-test/id_ed25519 famit@168.144.153.145`

## Restore procedure (source only — does NOT touch .env)
1. Back up current box source first:
   `ssh ... 'cp /opt/famit-agent/agent.py /opt/famit-agent/agent.py.prerestore.$(date +%s); cp /opt/famit-agent/prompt.py /opt/famit-agent/prompt.py.prerestore.$(date +%s)'`
2. Copy a file back from this snapshot, e.g.:
   `scp -i ~/.ssh/do-blr-test/id_ed25519 opt-famit-agent/agent.py famit@168.144.153.145:/opt/famit-agent/agent.py`
3. Verify md5 on the box matches the table above.
4. Restart the agent service, then place ONE real outbound test call. The
   real call is the only proof — offline-green != working.

## Security
gitleaks (no-git filesystem scan) on this snapshot = 0 leaks. No `.env`,
no `*cred*`, `*secret*`, `*.key`, no `provider_keys.json` were copied.
