# Free AI images for your app — the simple truth + the 2-minute fix

**Read this first (plain English):**

You did nothing wrong. Google's "Nano Banana" image model (`gemini-2.5-flash-image`)
**is** free — but the key you currently have is the **wrong kind of key**, and Google
will not let your account make a working one right now. So instead of fighting Google,
we use the **other free option that's already built into your app** and costs you ₹0.

**Bottom line: you will NOT have to pay anything.** Follow Part A (2 minutes) and you're done.

---

## Why your Gemini key doesn't work (no jargon)

- A real Google AI Studio key looks like this: **`AIza...`**
- Your key looks like this: **`AQ.Ab8RN6...`**

That `AQ.` kind of key is a **restricted token**. It does **not** work with the image
service — Google's own system rejects it and reports "no quota" (`limit: 0`). This is a
Google account restriction (lots of people are hit by it in June 2026, usually after a
key got shared/exposed). **It is not a billing problem and not your fault — you simply
can't make a working `AIza` key on this account today.**

So the smart move is **not** to spend hours begging Google. The smart move is to use the
**free Pollinations option**, which is already wired into your app as the default and
needs **no credit card, no Google, no billing — ever.**

---

# PART A — The 2-minute FREE fix (do this one) ✅

Pollinations gives your app free image generation. It already works with **no token at
all**. Adding a free token just makes it faster and removes the per-IP limit. Still ₹0.

### Step 1 — Open the Pollinations sign-in page
In your web browser, go to: **https://enter.pollinations.ai**

### Step 2 — Sign in with GitHub
- Click the **"Sign in with GitHub"** button.
- If you don't have a GitHub account, it will let you make one for free in ~1 minute
  (just an email + password). No card, no payment.
- After signing in, GitHub will ask **"Authorize Pollinations?"** — click the green
  **Authorize** button.

### Step 3 — Copy your token
- After authorizing, the page shows your **token** (a long line of letters and numbers).
- There's usually a **Copy** button next to it — click it. (Or select the whole token
  and copy it.)
- **Do NOT paste this token into a chat or email.** Treat it like a password.

### Step 4 — Put the token in your settings file
- Open this file on your computer:
  **`C:\Users\kunal\Desktop\caps\.env.local`**
- Go to the very bottom and add a new line that looks like this (paste your real token
  after the `=`, no spaces, no quotes):

  ```
  POLLINATIONS_TOKEN=paste-your-copied-token-here
  ```

- Save the file.

### Step 5 — Tell your developer/agent it's set
That's it. Your app already uses Pollinations as the **default free image provider**, so
images will start working. If the app runs on the server too, the same line also needs to
go in `/opt/famit-aiasset/.env` on the box — your agent can do that for you (just say
"the Pollinations token is in .env.local, please put it on the box and restart the
service"). **Never type the token itself into chat.**

> ✅ **You are done.** No money spent. No Google. No billing.

---

# PART B — (Optional, ONLY if you really want Gemini later)

You do **not** need this. Part A already gives you free images. But if you ever want to
try the Gemini image model specifically, here's the honest situation:

1. The Gemini image model is free on the **Google AI Studio free tier** (around a few
   hundred free images a day, no credit card).
2. **BUT** it only works with a key that starts with **`AIza...`**.
3. Your current account can only make the broken **`AQ.`** kind. To get a real `AIza` key
   you would have to either:
   - **(a)** Try a **different Google account** that isn't restricted: go to
     **https://aistudio.google.com/apikey** → **"Create API key"** → check that the key
     it gives you starts with **`AIza`** (if it starts with `AQ.`, that account is
     restricted too — stop, use Part A). Then put it in `.env.local` as
     `GEMINI_API_KEY=AIza...`, or
   - **(b)** Ask Google to lift the restriction on your current account (slow, not
     guaranteed) by posting on the Google AI developer forum.

**Honest recommendation:** skip Part B. Pollinations (Part A) is genuinely free, already
the default in your app, and has no Google restriction headaches. Use it.

---

## Quick safety reminder
- The token is like a password — **never paste it into a chat window**. Put it in the
  `.env.local` file (and the server file) only.
- Nothing in this guide costs money. If any screen ever asks for a **credit card to
  continue**, stop — you don't need to, and you should not enter one.
