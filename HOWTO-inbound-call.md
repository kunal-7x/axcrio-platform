# FOUNDER LIVE-TEST RECIPE (2026-06-14 — WORKING)

## STATUS: LIVE AND WORKING

Voice surgery complete. Sarvam v3/priya is deployed. The inbound AI voice agent speaks natural Hinglish — English words like "BHK", "Codename Joy" are pronounced correctly, not garbled.

---

## TEST 1 — CALL THE INBOUND LINE

**Number:** +91 80 7158 3488

**What to say (in Hindi):**
> "मुझे 2 BHK Codename Joy 3.0 book करना है"
> (Say it naturally. The agent should reply in Hindi with clear English brand words.)

**What you should hear (good):**
- Agent greets you in Hindi
- "BHK" sounds like "बीएचके" (bee-aitch-kay) — NOT "उसाई" or gibberish
- "Codename Joy" sounds like "कोड नेम जॉय" — NOT "हुड नेमो"
- Natural Hinglish, casual register, no robot-voice

**If you switch to English mid-call** → agent switches to English automatically (MLV mirror intact)

**Rollback (if anything sounds wrong):** Tell the team — they can revert to the old config in 30 seconds.

---

## TEST 2 — SEE THE TRANSCRIPT IN THE PANEL

After your call, go to:

**panel.famit.in/ai-manager/sessions**

You will see:
- Your call listed with phone number, time, duration, status
- Click the row → transcript slides open on the right
- AI turns on the LEFT (grey background)
- Your turns on the RIGHT (blue/tinted background)
- Timestamps on each turn

This is the inbound call transcript view — now live for the first time.

---

## OLD CONTENT (kept for reference below)

---

## ⚠️ STEP 0 — Vobiz routing (needed before any call reaches us)

Our side is fully ready and armed. The *only* remaining step is on the Vobiz website —
tell Vobiz to send calls for your number to our server. If you (or we) already did this,
skip to **"THE TEST"** below.

1. Log in to **Vobiz** → left menu **SIP Trunk** → **Inbound Trunks**.
2. Open (or create) the inbound trunk named **AI Manager Inbound**.
3. Under **Authentication & Routing → Primary Origination URI**, set:
   - **URI:** `sip:168.144.153.145:5060`
   - **Transport:** **TCP**  ← important, must be TCP (not UDP)
   - **Priority:** `1`  ·  **Weight:** `10`  ·  **Enabled:** on
4. Under **Link Phone Numbers**, make sure **+91 80710 83488** is ticked/linked to this trunk.
5. **Save.**

(That's it. Full detail is in `ai_manager_INBOUND_SETUP.md` if you need it.)

---

## ✅ THE TEST — call the number  _(only after we confirm the crash is fixed)_

**Call FROM your phone `+91 78610 19021`** (this exact number — it's the one we authorized).
**Call this number: ☎️ +91 80710 83488**

Then follow along:

### Step 1 — It greets you and asks for your PIN
You'll hear: *"Hello, this is your Famit AI Manager. Please say or enter your PIN."*

### Step 2 — Give your PIN: **4 8 2 7**
- **Best way:** press **4 8 2 7** on your phone keypad, then **#**.
- **Or:** just *say* "four eight two seven" out loud.

It should reply: *"You're verified. What would you like to do?"* ✅

### Step 3 — Try a SAFE command (no PIN needed again)
Say: **"how many leads today"** (or in Hindi: *"aaj kitne leads aaye"*).
→ It answers with the number right away. ✅ (Safe = read-only = no extra PIN.)

### Step 4 — Try a RISKY command (it will ask for your PIN again)
Say: **"run my campaign"** (or *"campaign chalao"*), or **"increase the budget"** (*"budget badha do"*).
→ It will say this changes something / spends money and will **ask for your PIN again**.
   This is correct — every money/bulk action needs a fresh PIN. ✅

### Step 5 — Approve it
- Enter **4 8 2 7** again (keypad + # or say it).
- It reads back exactly what it will do and asks **"Haan ya na?"** (yes or no).
- Say **"haan"** (yes).
→ It does the action and tells you it's done. ✅

### Step 6 (optional) — Prove the lock works
Call again, try a risky command, and on purpose enter a **WRONG** PIN (e.g. 0000).
→ It must **refuse** and NOT do anything. After a few wrong tries it locks the line. ✅

---

## What "it works" looks like
- Greeting → asks PIN → **4827** verifies.
- "how many leads today" → answered, **no second PIN**.
- "run my campaign" / "increase budget" → **asks PIN again** → 4827 + "haan" → **it executes**.
- Wrong PIN → **refuses**.

If any of those is wrong, **hang up and tell us** — don't keep using it for real money actions.

---

## If the call doesn't connect at all
That's almost always the Vobiz step above (URI / Transport TCP / number linked). Re-check
**Step 1–5** of the Vobiz setup. If it still fails, tell us the time you called and we'll
look at the server logs (we can see your call arrive).

---

### The facts, in one place
| Thing | Value |
|---|---|
| Call THIS number | **+91 80710 83488** |
| Call FROM this number | **+91 78610 19021** (only this one is authorized) |
| Your PIN | **4827** |
| Safe command (no PIN) | "how many leads today" / "aaj kitne leads aaye" |
| Risky command (asks PIN) | "run my campaign" / "increase the budget" / "budget badha do" |
| Approve word | "haan" (yes) |

---

## 🆘 HELP US CATCH IT (optional, 1 call) — only if you want to speed up the fix
The crash only happens during a *real* call, so a real call gives us the exact log we
need. If you're willing:
1. Make sure Vobiz routing (Step 0) is done.
2. Call **+91 80710 83488** from **+91 78610 19021** once.
3. You will likely hear **silence / dead air** (that's the bug — expected for now).
4. **Write down the exact time you called** (e.g. "6:42 pm, Jun 12") and send it to us.
We'll pull the server log for that minute and fix the startup crash. You do NOT need to
do anything technical.

## 📋 What's actually true right now (for the record)
- ✅ Phone-number routing reaches our server (a real call arrived Jun 11 19:37).
- ✅ The AI "brain" (understands commands, PIN gate, runs campaigns, reads leads/billing)
  is built and passes its offline tests.
- ✅ The panel "Call History" page is live at panel.famit.in/ai-manager → Calls tab
  (it will fill in once calls actually complete; right now it's empty because no call
  has survived).
- ✅ Your live outbound caller ("Riya") is **completely untouched and healthy** — none of
  this affected your earning calls.
- ❌ **The inbound agent crashes on speech-to-text startup during a real call → no greeting,
  silence.** This is the one blocker. Not fixed yet.
