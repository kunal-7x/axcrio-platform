# 🗣️ Test the AI on a call in BOTH languages (dead-simple)

**What changed (2026-06-14):** your inbound AI now **mirrors whatever language YOU speak**, every
turn. Speak English → it answers in English. Speak Hindi → it answers in Hindi. Switch in the
*middle* of the call → it switches with you on its very next sentence. It will never lecture you
about language or ask "shall I speak English?" — it just follows you. The opener is also cleaned up
(no more "Hello/Haan" stutter).

---

## ✅ Do this (takes 2 minutes)

1. **Call this number from your phone:** **+91 80715 83488**
2. Wait for the greeting — you'll hear: *"Namaste, this is Riya from Famit. Thanks for calling —
   how can I help you today?"*
3. **Speak in ENGLISH first.** Say something like:
   > "Hi, tell me about your 2BHK flats and the price."
   - ✅ **Expected:** the AI replies **in English.**
4. **Now switch to HINDI mid-call.** Say:
   > "Achha, Hindi mein baat karein. Location kahan hai?"
   - ✅ **Expected:** the AI **switches to Hindi** on its next reply and stays there.
5. **Switch back to English** if you like:
   > "Okay, back to English — is financing available?"
   - ✅ **Expected:** the AI **switches back to English.**

That's it. If the language follows you each time, the fix is working.

---

## 🔁 The other direction (start in Hindi)

You can also start the call in Hindi:
> "Namaste, 2BHK flat ke baare mein bataiye."
- ✅ **Expected:** the AI answers **in Hindi**, and will switch to English the moment you do.

---

## ℹ️ Good to know
- It's normal for the AI to sprinkle a tiny bit of Hinglish ("Haan ji", "theek hai") — that's how
  real Indian salespeople talk on the phone. The *substance* of the reply will be in your language.
- The AI will **never** announce that it's switching languages — it just does it.
- If anything feels off (it stays stuck in one language, or the greeting sounds wrong), tell us the
  rough time of your call — we can read the exact transcript from the server and fix it.

---

## 🧪 What we already proved (without spending your call minutes)
We ran the **real** AI brain (same model the live call uses) through scripted English/Hindi/switch
turns and confirmed it mirrors correctly — Hindi→Hindi, English→English, and the mid-call switch
(the exact thing that was broken). The **only** thing a scripted test can't prove is the live
microphone (speech-to-text) and the live voice (text-to-speech) on a real phone line — **that's why
your real call above is the final check.**
