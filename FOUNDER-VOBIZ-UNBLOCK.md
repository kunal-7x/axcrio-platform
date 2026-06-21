# ☎️ FOUNDER ACTION — get outbound calling working again (Vobiz)

## What's wrong (plain words)
Your outbound calling number **+91 80715 83488** got **flagged as spam by the phone carrier**.
Every outbound call now returns "486 Busy" **without ringing** — the carrier rejects it before it
reaches the person. This is **NOT a Famit bug**: we checked everything and it's 100% healthy —
- the voice engine is running fine,
- the calling trunk is connected,
- your Vobiz balance is **₹477.55** (plenty),
- the config is correct.

The ONLY thing wrong is the carrier's spam-flag on the number. **Only Vobiz / the carrier can clear it** —
no code change on our side can.

## What only YOU can do (2 minutes)
**Contact Vobiz support** (the channel + login are in your credentials doc) and say:

> "My DID **+918071583488** is returning **SIP 486 'Busy Here'** on every outbound call, with **no ring** —
> it looks carrier **spam-flagged**. Please either clear the flag, or **rotate me to a new outbound
> caller-ID / DID**. Outbound is completely blocked; inbound still works."

👉 **Fastest fix: ask for a NEW number (caller-ID rotation).** Clearing a spam-flag can take days;
a fresh DID works immediately.

## Until Vobiz fixes it — DON'T place outbound test calls
Every failed attempt **re-signals the spam pattern and extends the block**. I've stopped the automated
dialer that was quietly re-trying your leads (that's why 24h of "resting" didn't help — it never actually
rested). So: no manual outbound test calls until Vobiz confirms a cleared/new number.

## Once Vobiz confirms (cleared or new DID)
Place **exactly ONE** real outbound call. We'll read the SIP logs — if it shows a ring
(`inviteToRingingMs > 0`), the block is gone and **I immediately build the full outbound system**
(RAG grounding + provider-lock on the earner, each with a real ring-test). Inbound is unaffected and
keeps working throughout.
