# Founder test — call your AI Manager (inbound voice)

**Status: ARMED + PROVEN with a real call.** On 2026-06-12 06:41 UTC a real call from your
handset already reached the AI Manager with live two-way audio — the only thing that blocked
the command was a PIN-lockout on your number, which is now cleared. Follow the steps below.

## What to do (60 seconds)

1. **From your phone, dial the AI Manager number:**

   ## +91 80715 83488

   (Call it like any normal phone number. Use the SIM whose number is `+91 6375548830`
   or `+91 7861019021` — both are registered as the founder/admin.)

2. **Wait ~1 second. You'll hear Riya greet you first**, something like:
   *"Hey! This is Riya from Famit — your AI manager. To get you in securely, please say or
   key in your four-digit PIN."*

3. **Give your PIN: `4827`** — either:
   - **Say it** out loud: "four eight two seven", OR
   - **Key it in** on the dialpad: press `4` `8` `2` `7`.

4. **After it accepts the PIN, give a command in plain language.** Try one of:
   - *"How many leads are in Codename Joy?"*
   - *"Call the next 5 leads in Codename Joy."*
   - *"What's my campaign status?"*

   (Inbound command execution = build queue #4, in progress — early commands may just be
   acknowledged/slot-filled rather than fully executed. The voice + PIN gate is the part
   proven live now.)

5. **Hang up when done.**

## If it doesn't work

- **"This number isn't registered"** → you called from a different SIM. Use the
  `+91 6375548830` or `+91 7861019021` handset.
- **It rejects after a few wrong PINs ("locked")** → too many wrong PIN tries lock the
  number for ~15 min (security). The correct PIN is **4827**. If you get locked, wait 15
  min or tell me and I'll clear it (one command, data-only).
- **Silence / immediate hangup** → tell me; I'll check the live logs. (The known silence
  bug was fixed in a prior wave; the agent now self-heals a transient STT blip and always
  greets first.)

## What's proven vs. what this test exercises
- PROVEN at the carrier/LiveKit level: DID rings in 8ms, call connects, two-way RTP audio,
  routes to the `manager` agent, caller-id resolves you as admin.
- THIS TEST exercises: the live STT transcribing your *real* spoken PIN, PIN-accept, and the
  first command — the last human-audio leg that can only be done by a real phone call.
