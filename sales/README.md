# Famit / Axcrio — Sales Proposal (how to use)

**File:** `Famit-AI-Revenue-Platform-Proposal.html`

This is your customer-facing proposal — the one-pager you send a business owner
(real-estate / salon / clinic / coaching / D2C / agency) to get them to **buy**.
It is one self-contained HTML file: logo, styling, fonts-fallback, the loop
animation, and the live ROI calculator are all baked in. **It works offline** —
no internet, no install, nothing to host.

---

## 1. To open it
Double-click `Famit-AI-Revenue-Platform-Proposal.html`. It opens in any browser
(Chrome, Edge, Safari). Works on a laptop or a phone. Scroll through it — the
loop diagram animates, the numbers count up, and the **ROI calculator** is live:
drag the sliders / type your prospect's numbers and the gain, ROI multiple, and
payback update instantly.

## 2. To send it to a prospect
Just attach the single `.html` file to an email / WhatsApp / drive link. They
double-click and it opens — no software needed.

## 3. To make a PDF (a clean leave-behind)
1. Open the file in **Chrome or Edge**.
2. Press **Ctrl + P** (Windows) or **Cmd + P** (Mac).
3. Destination → **Save as PDF**.
4. Recommended settings: paper **A4**, margins **Default**, and turn **ON**
   "Background graphics" (so the dark cards print in colour).
5. Save. You get a clean ~8-page PDF — the nav bar and the floating button are
   automatically hidden, and cards won't get chopped across pages.

> Tip: before you print, you can type your prospect's business name into the
> blue "your business" word in the headline (click it, type, it stays).

---

## 4. Personalise it (no coding needed)
- **Prospect's name in the headline:** click the blue *"your business"* text on
  screen and type their name (e.g. *"Sharma Real Estate"*). The page remembers
  it while it's open.
- **The ROI numbers:** the calculator already defaults to a realistic case
  (500 leads/mo, 5% conversion, ₹15k/customer, replacing 1 telecaller on the
  Growth plan). Move the sliders to match *their* business before the meeting —
  the headline gain (₹98,751/mo · 5× · pays for itself in ~6 days) recalculates.

## 5. Swapping in real logos / testimonials later (needs a small text edit)
Open the `.html` in any plain text editor (Notepad, VS Code) and search for:

- **Your logo** — it's embedded as text starting with
  `data:image/png;base64,iVBOR...`. To swap it, convert a new PNG to base64
  (e.g. base64.guru) and replace that long string. *Or just ask the build
  assistant to swap it — it's a 1-line change.*
- **Testimonials** — there are **none in the file yet** (we never invent
  quotes). When you have a real client quote + permission, search the file for
  the `proof` section and add a card there, or hand the quote to the build
  assistant to drop in.
- **Pricing** — the plan amounts (Starter ₹9,999 / Growth ₹24,999 /
  Enterprise ₹75,000+) appear both in the pricing section and in the ROI
  calculator's plan buttons (`data-fee="..."`). Change them in both places, or
  ask the assistant.

---

## What's already verified (so you can send it with confidence)
- Fully **offline / self-contained** — logo embedded, fonts fall back to system
  fonts if Google Fonts can't load. No broken links.
- **ROI calculator computes correctly** and matches the headline numbers.
- **Prints to a clean ~8-page PDF** — nav/sticky button hidden, no cut-off cards.
- **Looks premium on desktop and mobile** (no sideways scrolling on phones).
- **No fake claims** — every proof point is real and honestly tagged
  *Live / Ready / Soon*; there are no placeholder/"lorem" leftovers.

Questions or edits → ask the build assistant; most changes are a one-line tweak.
