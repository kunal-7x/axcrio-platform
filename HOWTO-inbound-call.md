# 📞 HOW TO TEST YOUR AI MANAGER PHONE LINE (dead-simple)

**What this is:** the goal is that you *call* your AI Manager, speak a command, and it
does it — after checking your PIN.

> ## ⛔ HONEST STATUS (2026-06-12): NOT YET WORKING ON A REAL CALL — DO NOT EXPECT AUDIO YET
> A real inbound test call DID reach our server on Jun 11 (19:37) — so the phone-number
> routing already works. **But the AI agent still crashed the moment it tried to start
> listening (speech-to-text), so the call went silent with no greeting.** We have proven
> this is *not* the keys or the network (the very same speech engine connects fine in a
> plain test and on the live outbound caller, which made 96 calls). The crash is specific
> to the new inbound agent's startup and we have **not** fixed it yet — an earlier
> "fix" (adding retries) did NOT stop the crash on the real call. **Next engineering step
> is below in "REMAINING GAP".** Please hold off on the full test until we tell you the
> crash is actually fixed — but if you want to help us capture a fresh log, you CAN place
> one call and tell us the exact minute (see "HELP US CATCH IT" at the bottom).

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
