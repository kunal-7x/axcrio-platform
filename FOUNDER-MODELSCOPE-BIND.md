# Make Your ModelScope API Key Work — Click-by-Click

**Read this first.** Your API key already exists. You do **NOT** need to make a new
key. The key is being rejected (error "401 Authentication failed") for **one
reason only**: your ModelScope account is not yet **linked to an Alibaba Cloud
account**. ModelScope refuses to run the AI until that link is done. This guide
fixes exactly that. It takes about 5–10 minutes and is **free**.

> What "linking" means in plain words: ModelScope is owned by Alibaba. To use
> their AI engine (called "API-Inference"), they make you connect a free Alibaba
> Cloud account to your ModelScope account. Until you click that link button,
> every request is blocked — which is the error you're seeing.

---

## STEP 1 — Log in to ModelScope

1. Open your web browser (Chrome is fine).
2. Go to: **https://www.modelscope.ai** — this is the **international** site.
   - Note: there are two versions of the site. `modelscope.ai` is the
     international one (English, Singapore servers). `modelscope.cn` is the
     China one (mostly Chinese). **Use the same one you originally signed up on
     and made your key on.** If you're not sure, try `modelscope.ai` first; if
     your key/account isn't there, try `modelscope.cn`.
3. Click **Login / Sign In** (top-right corner) and log in with the same account
   that owns your key.

**Confirm:** you can see your name or profile picture in the top-right corner.

---

## STEP 2 — Open the Access Token page

1. Click your **profile picture / avatar** in the top-right corner.
2. From the dropdown menu, click **Access Token** (it may also be shown under
   **Account Settings → Access Token**).

You are now on the page that controls your API key — the same page where your
`ms-...` key lives. **Do not create a new one.**

**Confirm:** you can see your existing token on this page (it will start with
`ms-` — you don't need to copy or change it).

---

## STEP 3 — Bind (link) your Alibaba Cloud account

This is the one missing step that fixes the error.

1. On that same **Access Token** page, look for a button or banner that says one
   of these:
   - **"Bind Alibaba Cloud Account"**, or
   - **"Link Alibaba Cloud Account"**, or
   - **"Associate Aliyun Account"**.
   It usually appears as a notice/button near the top of the token page.
2. Click it. A new page or popup from **Alibaba Cloud** will open.

### If you DON'T already have an Alibaba Cloud account
- The popup will offer **"Sign up" / "Register"** — do that. It's **free**.
- You'll enter an email, set a password, and verify the email.
- Alibaba may ask for **real-name / identity verification** (this is normal and
  required for the free AI quota). Follow the on-screen prompts to complete it.
- **You will NOT be charged.** The AI image quota you need is **free: up to
  2,000 images/requests per day**. You do not need to add money or a card to use
  the free quota.

### If you ALREADY have an Alibaba Cloud account
- Just **log in** in that popup with it.

3. After logging in / signing up, Alibaba will show an **"Authorize" / "Agree" /
   "Confirm"** button to let ModelScope connect to it. **Click it.**
4. The window will return you to ModelScope.

**Confirm:** back on the **Access Token** page, the "Bind Alibaba Cloud" button
is now gone, OR it now shows something like **"Bound"** / **"Linked"** / your
Alibaba account name. That means the link worked.

---

## STEP 4 — Confirm API-Inference is on

1. Stay on the **Access Token** page (or open **API-Inference** from the menu if
   you see it).
2. It should now show your token as **active / enabled**, with no red warning or
   "bind your account first" notice.
3. Your key is still the same `ms-...` key you already had — nothing to copy or
   resend.

**That's it. The fix is the binding in Step 3 — nothing else changes.**

---

## Quick recap (the whole thing in one breath)
1. Log in at **modelscope.ai** (or **.cn** if that's where you signed up).
2. Avatar → **Access Token**.
3. Click **Bind / Link Alibaba Cloud Account** → sign up free (or log in) →
   finish identity check → click **Authorize**. The free quota is **2,000
   images/day**.
4. Page now shows **Bound / active** — done.

---

## If you get stuck
- **Can't find the "Bind" button on the Access Token page?** Try the other site
  (`.ai` vs `.cn`) — the button only appears on the site where your account
  actually lives.
- **Official help page (Alibaba binding tutorial):**
  https://modelscope.cn/docs/accounts/aliyun-binding-and-authorization
- **Official API-Inference intro:**
  https://modelscope.cn/docs/model-service/API-Inference/intro

---

**When you've done this, tell Claude — I'll generate a test image to confirm it works.**
