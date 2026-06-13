# 🎙️ Script Studio — paste a vendor's script, the AI adopts it (founder recipe)

**What this gives you:** for any campaign, you (or a vendor) can paste a free-form
brief — how to greet, what to ask, the tone, the language — and the inbound AI
caller will **adopt that persona and greeting** instead of the old fixed template.
The whole script is stored losslessly (nothing is cut), and you can PREVIEW the
exact "brain" and DRY-RUN a sample turn before any real call.

It is LIVE now at **panel.famit.in** (inbound). No new call is placed by any of
the steps below — preview and dry-run are free and safe.

---

## Do this (5 clicks)

1. **Open a campaign.** Go to **panel.famit.in → Campaigns**. Find the campaign row
   you want (e.g. "DLF The Crest").

2. **Click the "Script" button** on that row (the little magic-pencil icon). A
   two-pane Script Studio window opens for that campaign.

3. **Paste the script (LEFT pane).** Type or paste the vendor's free-form brief —
   the greeting line, the tone ("warm, like a family friend"), what to ask (budget,
   family size, locality), the language, do's and don'ts. Click **Save**. You'll see
   a character count and a set of "persona chips" (greeting / tone / language /
   do / don't) the system parsed out for you. (Your full text is kept exactly — the
   chips are just a convenience summary.)

4. **Preview the brain (RIGHT-top).** Click **Refresh** on the right pane to see the
   EXACT instructions the AI will adopt, with a green "persona on" pill. This is the
   real rendered brain — what the inbound agent will use.

5. **Dry-run a turn (RIGHT-bottom).** Type a caller line (e.g. "Hi, I saw your ad")
   or click a sample chip, then hit **Run**. The AI replies in the adopted persona
   (e.g. *"Namaste! Main Anjali bol rahi hoon Skyline Realty se…"*), shown as a chat
   bubble with a "persona adopted" badge. **No call is placed, nothing is charged.**

That's it. The campaign now carries the vendor's script.

---

## To hear it on a REAL call

The dry-run proves the text adoption. The only thing that proves the **live voice**
is a real inbound call:

6. **Call the inbound number (DID)** and ask about that campaign. The AI should
   greet you with the vendor's scripted greeting, in the tone you wrote, mirroring
   your language. (This is the final acceptance — only your real call proves the
   live mic + voice.)

---

## Good to know
- **New campaigns:** you can paste a script right when you create a campaign (there's
  a script box in the create form). Leave it blank and the campaign behaves exactly
  as before.
- **Safe by design:** if a script tries to sneak in a hidden "ignore your rules"
  instruction, the AI treats it as plain reference data — it will NOT obey it. Your
  three top-priority safety rules always win.
- **Existing campaigns are untouched** until you add a script — they render exactly
  as they did yesterday (proven byte-for-byte).
- **Outbound (the live earner) is deliberately left on the old behaviour** for now —
  it will only adopt scripts after you sign off and we test it on a real ring. Inbound
  is live today.

---

## If something looks off
- Preview shows "base render" (no persona): the campaign has no script yet — paste one
  on the left and Save, then Refresh.
- Dry-run says "LLM unavailable": that's a temporary Groq hiccup, retry; the Preview
  still shows the adopted persona.
- Tell me the campaign name and what you saw and I'll check the box.
