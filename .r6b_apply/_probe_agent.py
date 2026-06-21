import hashlib

PATH = "agent.py"  # the file under test (copied to /tmp by the runner)
src = open(PATH, encoding="utf-8").read()
lines = src.splitlines(keepends=True)


def span_md5(start_anchor, end_anchor):
    i = next(k for k, l in enumerate(lines) if start_anchor in l)
    j = next(k for k, l in enumerate(lines) if end_anchor in l and k >= i)
    blob = "".join(lines[i:j + 1])
    return hashlib.md5(blob.encode("utf-8")).hexdigest()


print("EL_SPAN_MD5", span_md5("tts = elevenlabs.TTS(", "auto_mode=True,"))
print("STTLLM_SPAN_MD5", span_md5("stt=sarvam.STT(", "max_completion_tokens=int(os.getenv"))

# import the module's pure helpers WITHOUT starting the agent (livekit import may pull plugins).
# We only need _closure_signal / _normalize_speech_units; import via importlib on a stripped copy
# is heavy, so test by exec-ing just the needed functions from source via a namespace that has
# the few module deps they touch (os, re). Simpler: import the real module; it's import-safe.
import importlib.util as _ilu
spec = _ilu.spec_from_file_location("agent_under_test", PATH)
mod = _ilu.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
    print("IMPORT_OK", True)
except Exception as e:
    print("IMPORT_OK", False, repr(e))
    raise SystemExit(0)

cs = mod._closure_signal
nz = mod._normalize_speech_units


def turns(*pairs):
    return [{"role": r, "content": c} for r, c in pairs]


# (1) CLOSURE FIX: a book-REQUEST turn must NOT close (the dead-air bug).
req = turns(
    ("assistant", "क्या मैं Riya बात कर रही हूँ?"),
    ("user", "haan"),
    ("assistant", "site visit के लिए कौन सा time अच्छा रहेगा?"),
    ("user", "haan site visit book kar do"),  # REQUEST, not confirmed
)
print("REQ_NO_CLOSE", cs(req) == "")  # expect True (no premature close)

# (2) CONFIRMED booking -> closes on 'book'.
conf = turns(
    ("assistant", "site visit के लिए कौन सा time?"),
    ("user", "kal sham 5 baje"),
    ("assistant", "booked=true the site visit is confirmed. कल शाम पाँच बजे मिलते हैं।"),
    ("user", "theek hai"),
)
print("CONFIRMED_CLOSE", cs(conf) == "book")  # expect True

# (3) opt-out still closes 'no'.
no = turns(
    ("assistant", "..."), ("user", "..."), ("assistant", "..."),
    ("user", "mujhe interest nahi hai, do not call"),
)
print("OPTOUT_CLOSE", cs(no) == "no")

# (4) NORMALIZER — assert exact expected spoken text
exact = {
    "₹85 लाख": "85 लाख rupees",
    "Rs 200 dena hai": "200 rupees dena hai",
    "850 sq. ft का flat": "850 square feet का flat",
    "6.13 Cr से शुरू": "6.13 crore से शुरू",
    "size 900 sqft है": "size 900 square feet है",
    "₹1.32 करोड़": "1.32 करोड़ rupees",
}
for inp, want in exact.items():
    out = nz(inp)
    print("NZ", repr(inp), "->", repr(out), "|", out == want)

# (5) normalizer must NOT add 'rupees' twice / when already present
print("NZ_NO_DOUBLE", nz("पचासी लाख rupees").count("rupees") == 1)
print("NZ_PLAIN_UNCHANGED", nz("कल शाम मिलते हैं") == "कल शाम मिलते हैं")
