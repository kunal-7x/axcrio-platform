# silence-registry.md — DIAGNOSE-2: the `reject:unregistered` registry blocker

Scope of THIS doc: the registry mechanism behind `outcome=reject:unregistered`, the exact seed
performed for the founder, and the right unknown-caller product behavior. (The STT/`AgentSession is
closing` silence is blocker (A) — a separate fix in `aim_voice_agent.py`, not this doc.)

CRITICAL HONESTY: we cannot place a real SIP call from here. Everything below is proven at the
CODE-PATH + DATA level (the live `ai_manager.registry` module run in the agent's own venv against
the live `aim_numbers.jsonl`). The founder confirms by actually calling +918071583488.

---

## 1. The registry mechanism (how a caller-id maps to tenant/role/PIN/grants)

Three pieces, all live on the inbound box `famit@168.144.153.145`:

1. **Number registry** — `/opt/famit-agent/ai_manager/registry.py`
   - Storage: **append-only JSONL** at `config.numbers_file()` =
     `/opt/famit-agent/var/aim_numbers.jsonl` (var dir overridable by env `AIM_VAR_DIR`; the
     systemd unit `aim-voice-agent` runs with `WorkingDirectory=/opt/famit-agent`, so the default
     resolves to `/opt/famit-agent/var/`).
   - Folding: `_read_all()` reads every line and keeps **last-write-wins on `number_id`**. So you
     UPDATE a row by re-appending a line with the same `number_id`.
   - Key: `canonical_phone(phone)` = `"+"`(if present) + digits only. **It does NOT strip a leading
     `0` and does NOT add `+91`.** So `06375548830`, `6375548830`, `+916375548830`, `916375548830`
     are FOUR DISTINCT keys. You must seed every form the trunk might present.
   - Row fields: `number_id, tenant_id, phone, label, role, verify_mode, grants, verified, status,
     registered_at, updated_at`.
   - `lookup(phone)` returns a row ONLY if `verified == True` AND `status == "active"`; else `None`.

2. **Identity resolution** — `/opt/famit-agent/ai_manager/identity.py`
   - `resolve(caller_id)` = thin wrapper over `registry.lookup`. `None` => the S1 reject.
   - `permits(role, grants, action)` = default-deny; role-family AND per-number grant must BOTH allow.
   - role `admin` grants ALL action families.

3. **PIN store (verify_mode = voice_pin)** — `/opt/famit-agent/firewall.py`, `var/pins.json`.
   - **PINs are keyed on `tenant_id`, NOT on the phone number.** Format
     `{tenant_id: {salt, pin_hash, set_at}}`, `pin_hash = sha256(salt + ":" + pin)`.
   - The state machine authenticates via `firewall.check_pin(res.tenant_id, secret)` — so EVERY
     number that maps to `tenant_id="admin"` shares the one `admin` PIN.

### The S1 → S2 flow (state_machine.py `_run_inner`)
```
S1: number = identity.resolve(caller_id)
    if not number:  say("This number isn't registered...");  outcome="reject:unregistered";  return
    tenant_id = number.tenant_id;  role = number.role;  verify_mode = number.verify_mode
S2: _authenticate(...) -> firewall.check_pin(tenant_id, spoken_pin)   # PIN is per-TENANT
S3+: business context + command loop
```

---

## 2. ROOT CAUSE of `reject:unregistered`

The founder's **actual presented caller-id is the Vobiz CLI `06375548830`** (not the SIM
`7861019021`). On disk, the SIM `+917861019021` was registered+verified, but `06375548830` was
**NOT in `aim_numbers.jsonl` at all** → `lookup("06375548830")` returned `None` → reject.

Proven live before the fix:
```
canon 06375548830 -> 06375548830
lookup vobiz 06375548830 -> None          # <-- the reject
lookup sim   +917861019021 -> True
```

Secondary latent bug found: a stale `verified:false` row (`num_c36c8bdb381f`, phone `7861019021`)
existed. `lookup()` returns on the FIRST phone match irrespective of verified — if it hits the
unverified row first it returns `None` even though a later verified row exists for the same number.

PIN is fine: `var/pins.json` tenant `admin` hash == `sha256("277572b6986dd493:4827")` — VERIFIED
equal. So **4827 is the live admin PIN**; no PIN change needed.

---

## 3. The EXACT seed performed (DONE + verified)

Backup first (untouched-rollback):
```
cp -p /opt/famit-agent/var/aim_numbers.jsonl \
      /opt/famit-agent/var/aim_numbers.jsonl.VOBIZbak.20260612-021106
```

Seed via the registry's own API in the agent venv (guarantees correct row shape), full admin grants,
`verify_mode=voice_pin`, `verified=True`, `status=active`, `tenant_id="admin"`, `role="admin"`:

```python
# run as: /opt/capsy-agent/.venv/bin/python  (AIM_VAR_DIR=/opt/famit-agent/var, sys.path += /opt/famit-agent)
from ai_manager import registry as r
FULL = ["campaigns","leads","calls","whatsapp","ads","ads:read","analytics","contacts","billing"]

# (a) Vobiz CLI — the caller-id actually seen — every form the trunk may present:
for ph in ["06375548830", "6375548830", "+916375548830", "916375548830"]:
    r.register(tenant_id="admin", phone=ph, label="Founder Vobiz CLI (AIM inbound)",
               role="admin", verify_mode="voice_pin", grants=FULL,
               registered_by="silence-fix-arm", verified=True)

# (b) SIM forms (completeness so neither founder number ever rejects):
for ph in ["7861019021", "07861019021", "917861019021"]:   # +917861019021 already OK
    if not r.lookup(ph):
        r.register(tenant_id="admin", phone=ph, label="Founder SIM (AIM inbound)",
                   role="admin", verify_mode="voice_pin", grants=FULL,
                   registered_by="silence-fix-arm", verified=True)

# (c) Fix the stale unverified bare-SIM row via last-write-wins re-append:
rows = r._read_all(); stale = dict(rows["num_c36c8bdb381f"])
stale.update(verified=True, status="active", role="admin", grants=FULL)
r._upsert(stale)
```

PIN — **NO action needed** (already correct):
```
firewall.check_pin("admin", "4827") == True   # var/pins.json salt 277572b6986dd493 verified
```

### Post-seed verification (live registry module, ALL founder forms resolve)
```
06375548830   -> OK (tenant=admin role=admin grants=9)
6375548830    -> OK
+916375548830 -> OK
916375548830  -> OK
+917861019021 -> OK
7861019021    -> OK   (after stale-row fix)
07861019021   -> OK
917861019021  -> OK
```

Rollback (registry only): `cp -p aim_numbers.jsonl.VOBIZbak.20260612-021106 aim_numbers.jsonl`.
No restart needed for registry changes (JSONL is read fresh per call). agent.py / the outbound
earner were NOT touched.

---

## 4. Unknown-caller product behavior (no caller ever hits SILENCE)

CURRENT (correct, in `state_machine.py` S1): an unregistered caller is GREETED then told
`"This number isn't registered for AI Manager."` and the call ends `reject:unregistered` — it does
NOT reveal business data and does NOT go silent at the state-machine layer. That behavior is right;
KEEP it. (Spelling it slightly warmer is optional, e.g. *"Thanks for calling. This number isn't
registered for AI Manager yet — ask your admin to add it, then call back."*)

IMPORTANT: the *actual* silence the founder heard is NOT this path — it is blocker (A): the STT
WebSocket connect fails, `AgentSession` goes to "closing", and the greeting `transport.speak()` at
line 540 fails BEFORE any of this S1 text is ever spoken. That is fixed separately in
`aim_voice_agent.py` (make the greeting play on a guaranteed-open transport / before/independent of
the STT pump, mirroring the working outbound `agent.py` Sarvam pattern). Until (A) is fixed, even a
registered caller hears silence. This registry fix removes blocker (B) only.

---

## 5. Residual / follow-ups
- Latent `lookup()` first-match-wins bug (returns None if an unverified row for the same canonical
  phone is encountered first). Worked around by data (no stale unverified rows remain for founder
  numbers). A proper code fix would make `lookup` skip non-matching rows and keep scanning for a
  verified+active one. NOT done here to keep the change data-only.
- All founder numbers share tenant `admin` and therefore the single `admin` PIN 4827. Fine for the
  founder; per-number PINs would need a per-number secret store (not in scope).
