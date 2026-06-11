# How to Test Your AI Caller (Plain-English Guide)

This guide shows you two things, step by step:

- **PART A** — Make a real AI phone call to **your own phone** (Riya, your AI, calls you and talks).
- **PART B** — Tell the **AI Manager** (the chat/command brain) to run a campaign and have it dial.

Everything here is already wired and tested. Your own test number is **+91 78610 19021**. The AI Manager admin PIN is **4827**.

> Golden rule for testing: only ever put **your own number** as the lead when you're testing. A campaign dials whatever leads are in it — so for a clean test, use a campaign that has only your number.

---

## PART A — Place a test AI call to your own phone

This is the main path. It's the exact path that has already made 96 real calls. It works.

1. Open the panel in your browser: **panel.famit.in** and log in.
2. In the left menu, click **Run a Campaign**.
3. Pick any campaign from the list (or create a fresh one — see the tip below for a clean 1-call test).
4. Add **ONE lead** = your own number: **7861019021**.
   - If there's an **Upload** option, upload a tiny list with just that one number.
   - If there's a **Manual / Add lead** box, type **7861019021** there.
   - Make sure no other leads are selected — you want exactly one.
5. Set **concurrency** (how many calls at once) to **1**.
6. Click **Start / Run**.
   - If it says something like **"out of calling window"**, click **Force** (or the "call anyway" option). That just overrides the time-of-day limit.
7. **Watch your phone — it will ring within a few seconds.** Pick up. You'll hear **Riya**, your AI, start talking. That's the live product working end to end.

**What success looks like:** your phone rings, you answer, the AI speaks naturally. On the panel the call shows as **calling → done**. (If you don't pick up, it logs as *voicemail* — that's normal and still proves it dialed.)

> **Tip for a perfectly clean single-call test:** before step 3, create a brand-new campaign that contains **only your number (7861019021)**. Then "Run" can never accidentally dial real customers — it can only call you. This is the safest way to test.

---

## PART B — Tell the AI Manager to run a campaign

This proves the **AI Manager brain** can dial on command (not just the button). Use this once you're comfortable with Part A.

1. In the panel's left menu, open **AI Manager** (the `/ai-manager` page — it has a chat / Test Console box where you type commands).
2. In the chat box, type the command that **dials**. The phrasing matters:
   - To run a specific campaign, type: **`run the <campaign name> campaign`**
     (for example: `run the Codename Joy 3.0 campaign`)
   - Or to call a segment, type: **`call all hot leads`**
3. The AI Manager will recognize it as a **real dialing action** and ask you for your **PIN**. Type **`4827`** and confirm.
4. After you confirm, it triggers the **same dialer** as the button in Part A, and it starts calling the leads stored in that campaign.

**What success looks like:** after you enter the PIN and confirm, the AI Manager says it's enqueuing/running the calls, and phones in that campaign start ringing (the call shows up in your call logs just like Part A).

> **IMPORTANT — two different phrases do two different things:**
> - Saying **"create a new campaign"** only makes a **draft** — it does **NOT** dial anyone. (Safe.)
> - Saying **"run the … campaign"** or **"call all hot leads"** is what actually **DIALS**. (This one calls real numbers — only use it when you mean it.)
>
> So when you want it to actually call, use **"run the &lt;campaign&gt; campaign"** or **"call all hot leads"**, then PIN **4827**.

> **Safety for testing Part B:** "run the &lt;campaign&gt; campaign" dials **every lead stored in that campaign**. To test the brain without calling real customers, first make a campaign that contains **only your number (7861019021)**, then tell the AI Manager: `run the <that campaign> campaign` → PIN **4827**. Only your phone will ring.

---

## If something doesn't work

- **Phone never rings (Part A):** make sure the lead number is exactly **7861019021**, concurrency is **1**, and you clicked **Start** (and **Force** if it mentioned a calling window).
- **AI Manager says "blocked" or asks for PIN again:** the PIN is **4827**. Type it exactly.
- **AI Manager made a "draft" instead of calling:** you used "create a campaign" — instead say **"run the &lt;campaign&gt; campaign"** or **"call all hot leads"** to actually dial.
- **Still stuck:** note the campaign name and what you typed, and send it over — the dial path itself is confirmed healthy, so it'll be a quick fix.

---

### Quick reference
- Your test number: **+91 78610 19021** (enter as **7861019021**)
- AI Manager PIN: **4827**
- Dial-from-button path: **Run a Campaign → one lead = your number → concurrency 1 → Start (Force if needed)**
- Dial-from-AI-Manager phrase: **"run the &lt;campaign&gt; campaign"** or **"call all hot leads"** → PIN **4827** → confirm
