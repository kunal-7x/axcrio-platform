"""voice_kernel.speech.normalize — Indian-telephony spoken-form normalizer.

Pure, deterministic, stdlib-only. Renders numbers / currency / phone numbers /
dates / times / units / percentages to SPOKEN words in the target register
(EN or casual Hinglish), using the Indian 3:2:2 (lakh/crore) grouping — NOT
Western thousands/millions.

Why we own this (research DECISION 1):
  - ElevenLabs disables normalization by default on Flash v2.5 / Turbo v2.5 (the
    realtime telephony models) to preserve latency — phone numbers, dates,
    currency come out wrong.
  - Sarvam bulbul exposes no controls/guarantees for phone/date/acronym and
    bulbul:v3 has no `enable_preprocessing`.
So we render already-spoken text and feed each provider the same string. Output
is identical across providers; the founder can hot-swap TTS without the call
sounding different.

Everything here is SYNC and never raises out of `normalize_text` — on any
internal failure the caller (planner) falls back to the raw text.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# number words
# --------------------------------------------------------------------------- #
_EN_ONES = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
)
_EN_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")

# casual Hinglish digit words (digit-by-digit, e.g. phone/OTP)
_HI_DIGITS = ("zero", "ek", "do", "teen", "char", "paanch", "chhe", "saat", "aath", "nau")
_EN_DIGITS = _EN_ONES[:10]

# Hinglish cardinals for small money/qty amounts (1..100 common cases + units)
_HI_CARDINAL = {
    1: "ek", 2: "do", 3: "teen", 4: "char", 5: "paanch", 6: "chhe", 7: "saat",
    8: "aath", 9: "nau", 10: "das", 11: "gyaarah", 12: "baarah", 15: "pandrah",
    20: "bees", 21: "ikkees", 25: "pachees", 30: "tees", 40: "chaalees",
    50: "pachaas", 58: "athaavan", 60: "saath", 70: "sattar", 75: "pichhattar",
    80: "assi", 85: "pachaasi", 90: "nabbe", 100: "sau",
}
_HI_UNIT_WORD = {"lakh": "lakh", "crore": "crore", "hazaar": "hazaar", "thousand": "hazaar"}

_MONTHS = (
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_MONTHS_HI = (
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_ORD_HI = {
    1: "pehli", 2: "doosri", 3: "teesri", 4: "chauthi", 5: "paanchvi",
}

# acronyms that must be SPELLED (letter-by-letter), not said as a word.
# Versioned dictionary (research DECISION 2). Lowercased keys.
_SPELL_ACRONYMS = {
    "bhk": "B H K", "emi": "E M I", "otp": "O T P", "id": "I D",
    "kyc": "K Y C", "cibil": "CIBIL", "rera": "RERA", "nri": "N R I",
    "gst": "G S T", "ac": "A C", "sms": "S M S", "url": "U R L",
}

# unit symbols -> spoken full word
_UNITS = {
    "sq ft": "square feet", "sqft": "square feet", "sq.ft": "square feet",
    "km": "kilometers", "kg": "kilograms", "cm": "centimeters", "mm": "millimeters",
    "ft": "feet", "hrs": "hours", "hr": "hour", "min": "minutes",
}


def _en_two_digit(n: int) -> str:
    if n < 20:
        return _EN_ONES[n]
    t, o = divmod(n, 10)
    return _EN_TENS[t] + ("" if o == 0 else "-" + _EN_ONES[o])


def _en_three_digit(n: int) -> str:
    h, rest = divmod(n, 100)
    out = []
    if h:
        out.append(_EN_ONES[h] + " hundred")
    if rest:
        out.append(_en_two_digit(rest))
    return " ".join(out)


def _int_to_words_en(n: int) -> str:
    """English cardinal using INDIAN grouping (lakh/crore)."""
    if n == 0:
        return "zero"
    if n < 0:
        return "minus " + _int_to_words_en(-n)
    parts: list[str] = []
    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thousand, n = divmod(n, 1_000)
    if crore:
        parts.append(_int_to_words_en(crore) + " crore")
    if lakh:
        parts.append(_en_two_digit(lakh) + " lakh")
    if thousand:
        parts.append(_en_three_digit(thousand) + " thousand")
    if n:
        parts.append(_en_three_digit(n))
    return " ".join(parts)


def _hi_cardinal(n: int) -> str:
    """Best-effort casual Hinglish cardinal for the COMMON amounts; falls back to
    English words (Latin) for the uncommon long-tail (those are read fine in a
    code-mix register)."""
    if n in _HI_CARDINAL:
        return _HI_CARDINAL[n]
    return _int_to_words_en(n)


# --------------------------------------------------------------------------- #
# currency  (₹ / Rs / INR), lakh/crore aware
# --------------------------------------------------------------------------- #
_CUR_RE = re.compile(
    r"(?:₹|\bRs\.?\b|\bINR\b)\s*"
    r"([\d,]+(?:\.\d+)?)\s*"
    r"(crore|cr|lakh|lac|lakhs|k|thousand|hazaar)?",
    re.IGNORECASE,
)
# bare "<num> lakh/crore" without a currency symbol (e.g. "58 lakh")
_BARE_UNIT_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(crore|cr|lakh|lac|lakhs)\b",
    re.IGNORECASE,
)
_HALF_WORDS = {0.5: "aadha", 2.5: "dhaai", 1.5: "dedh", 4.5: "saade char"}


def _strip_commas(s: str) -> str:
    return s.replace(",", "")


def _money_unit(num_str: str, unit: str, hinglish: bool) -> str:
    """Render '<num> lakh/crore' to spoken words, keeping the Indian unit word."""
    unit = (unit or "").lower()
    unit = {"cr": "crore", "lac": "lakh", "lakhs": "lakh", "k": "thousand"}.get(unit, unit)
    raw = _strip_commas(num_str)
    val = float(raw)
    # nice half-words in Hinglish (dhaai/dedh/saade)
    if hinglish and val in _HALF_WORDS and unit in ("crore", "lakh"):
        return f"{_HALF_WORDS[val]} {unit}"
    if val == int(val):
        head = _hi_cardinal(int(val)) if hinglish else _int_to_words_en(int(val))
    else:
        whole, frac = str(val).split(".")
        head = (_hi_cardinal(int(whole)) if hinglish else _int_to_words_en(int(whole))) + " point " + " ".join(
            (_HI_DIGITS[int(d)] if hinglish else _EN_DIGITS[int(d)]) for d in frac
        )
    return f"{head} {unit}".strip()


def _paise_words(frac: str, hinglish: bool) -> str:
    """Render the fractional rupee part as PAISE (1-2 significant digits).
    '99' -> 99 paise, '5' -> 50 paise, '50' -> 50 paise."""
    frac = (frac + "00")[:2]          # pad/truncate to exactly 2 paise digits
    val = int(frac)
    if val == 0:
        return ""
    head = _hi_cardinal(val) if hinglish else _int_to_words_en(val)
    return f" and {head} paise"


def _normalize_currency(text: str, hinglish: bool) -> str:
    def repl(m: re.Match) -> str:
        num, unit = m.group(1), m.group(2)
        rupees = "rupaye" if hinglish else "rupees"
        # the regex eats trailing whitespace after the (optional) unit; re-add a
        # space so the following word never fuses ('rupayeper month').
        tail = " " if (m.end() < len(m.string) and m.string[m.end() - 1:m.end()] == " ") else ""
        if unit:
            return _money_unit(num, unit, hinglish) + " " + rupees + tail
        raw = _strip_commas(num)
        if "." in raw:
            whole_str, frac = raw.split(".", 1)
            whole = int(whole_str or "0")
            wword = _hi_cardinal(whole) if hinglish else _int_to_words_en(whole)
            return f"{wword} {rupees}{_paise_words(frac, hinglish)}{tail}"
        return (f"{_hi_cardinal(int(raw)) if hinglish else _int_to_words_en(int(raw))} {rupees}{tail}")

    out = _CUR_RE.sub(repl, text)

    def bare(m: re.Match) -> str:
        return _money_unit(m.group(1), m.group(2), hinglish)

    return _BARE_UNIT_RE.sub(bare, out)


# --------------------------------------------------------------------------- #
# phone numbers — HIGHEST-risk drop in telephony. digit-by-digit, grouped.
# --------------------------------------------------------------------------- #
_PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\s\-]{7,14}\d)(?!\d)")


def _speak_digits(digits: str, hinglish: bool) -> str:
    table = _HI_DIGITS if hinglish else _EN_DIGITS
    return " ".join(table[int(d)] for d in digits if d.isdigit())


def _normalize_phone(text: str, hinglish: bool) -> str:
    def repl(m: re.Match) -> str:
        raw = m.group(1)
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 6:  # too short to be a phone; leave to the number pass
            return raw
        cc = ""
        if raw.strip().startswith("+") and len(digits) > 10:
            cc, digits = digits[:-10], digits[-10:]
        # group 5+5 for a 10-digit Indian mobile, with a comma beat between groups
        groups = [digits[i:i + 5] for i in range(0, len(digits), 5)] if len(digits) == 10 else [
            digits[i:i + 4] for i in range(0, len(digits), 4)
        ]
        spoken = " , ".join(_speak_digits(g, hinglish) for g in groups)
        if cc:
            spoken = _speak_digits(cc, hinglish) + " , " + spoken
        return spoken

    return _PHONE_RE.sub(repl, text)


# --------------------------------------------------------------------------- #
# dates & times
# --------------------------------------------------------------------------- #
_TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?\b")
_DATE_NUM_RE = re.compile(r"\b(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?\b")


def _normalize_time(text: str, hinglish: bool) -> str:
    def repl(m: re.Match) -> str:
        h, mn, ap = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower()
        if hinglish:
            # "<hour> baje" / saade for :30
            hw = _hi_cardinal(h)
            if mn == 30:
                half = {1: "dedh", 2: "dhaai"}.get(h, f"saade {hw}")
                return f"{half} baje"
            if mn == 0:
                return f"{hw} baje"
            return f"{hw} baj ke {_hi_cardinal(mn)} minute"
        hw = _en_two_digit(h)
        if mn == 0:
            tail = "o'clock"
        else:
            tail = _en_two_digit(mn)
        suffix = ""
        if ap == "am":
            suffix = " in the morning"
        elif ap == "pm":
            suffix = " in the afternoon" if h < 5 else " in the evening"
        return f"{hw} {tail}{suffix}".replace(" o'clock", " o'clock")

    return _TIME_RE.sub(repl, text)


_ORD_EN_ONES = (
    "zeroth", "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
    "eighth", "ninth", "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth",
    "fifteenth", "sixteenth", "seventeenth", "eighteenth", "nineteenth",
)
_ORD_EN_TENS = (
    "", "", "twentieth", "thirtieth", "fortieth", "fiftieth", "sixtieth",
    "seventieth", "eightieth", "ninetieth",
)


def _ordinal_en(n: int) -> str:
    """English ordinal word for a day-of-month (1..31)."""
    if n < 20:
        return _ORD_EN_ONES[n]
    t, o = divmod(n, 10)
    if o == 0:
        return _ORD_EN_TENS[t]
    return _EN_TENS[t] + "-" + _ORD_EN_ONES[o]


def _normalize_date(text: str, hinglish: bool) -> str:
    def repl(m: re.Match) -> str:
        d, mo = int(m.group(1)), int(m.group(2))
        if not (1 <= d <= 31 and 1 <= mo <= 12):
            return m.group(0)
        if hinglish:
            dayw = _hi_cardinal(d)
            return f"{dayw} {_MONTHS_HI[mo]}"
        return f"the {_ordinal_en(d)} of {_MONTHS[mo]}"

    return _DATE_NUM_RE.sub(repl, text)


# --------------------------------------------------------------------------- #
# percent, units, acronyms, bare integers
# --------------------------------------------------------------------------- #
_PCT_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*%")
# 1-3 digit bare integers -> a cardinal word (do, teen / forty-two).
# Trailing guard: reject a following word-char OR a decimal point (period+digit),
# but ALLOW a sentence-final period ('Total 100.' must still normalize). The old
# `(?![\w.\d])` blocked EVERY number before a full-stop -> end-of-sentence leak.
_BARE_INT_RE = re.compile(r"(?<![\w.])(\d{1,3})(?!\w|\.\d)")
# 4+ digit bare numbers with NO currency/phone/date/percent context survived the
# earlier passes (year, area, pincode, account/code). A normalizer-OFF TTS reads
# raw digits wrong, so we MUST render them. With no semantic context a bare long
# run is safest read digit-by-digit (a real telecaller spells a code/pincode/
# account), never a giant cardinal ("five thousand and twenty-four" for a year).
_BARE_LONG_RE = re.compile(r"(?<![\w.])(\d{4,})(?!\w|\.\d)")


def _normalize_percent(text: str, hinglish: bool) -> str:
    def repl(m: re.Match) -> str:
        raw = m.group(1)
        word = "percent"
        if "." in raw:
            whole, frac = raw.split(".")
            head = (_hi_cardinal(int(whole)) if hinglish else _int_to_words_en(int(whole)))
            head += " point " + " ".join(
                (_HI_DIGITS[int(d)] if hinglish else _EN_DIGITS[int(d)]) for d in frac
            )
        else:
            head = _hi_cardinal(int(raw)) if hinglish else _int_to_words_en(int(raw))
        return f"{head} {word}"

    return _PCT_RE.sub(repl, text)


def _normalize_units(text: str) -> str:
    out = text
    # longest-first so 'sq ft' wins over 'ft'
    for sym in sorted(_UNITS, key=len, reverse=True):
        out = re.sub(rf"(\d)\s*{re.escape(sym)}\b", rf"\1 {_UNITS[sym]}", out, flags=re.IGNORECASE)
    return out


def _split_digit_acronym(text: str) -> str:
    """Split a number glued to an acronym so each is read right, e.g. '2BHK' ->
    '2 BHK' (the bare-int pass then says 'do', the acronym pass spells 'B H K')."""
    keys = "|".join(re.escape(k) for k in _SPELL_ACRONYMS)
    return re.sub(rf"(\d)({keys})\b", r"\1 \2", text, flags=re.IGNORECASE)


def _normalize_acronyms(text: str) -> str:
    def repl(m: re.Match) -> str:
        w = m.group(0)
        return _SPELL_ACRONYMS.get(w.lower(), w)

    return re.sub(r"\b[A-Za-z]{2,5}\b", repl, text)


def _normalize_bare_long(text: str, hinglish: bool) -> str:
    """4+ digit bare runs with no semantic context -> digit-by-digit spoken words
    (years/pincodes/codes/account numbers). Must run BEFORE the 1-3 digit pass so
    its digits aren't half-consumed."""
    def repl(m: re.Match) -> str:
        return _speak_digits(m.group(1), hinglish)

    return _BARE_LONG_RE.sub(repl, text)


def _normalize_bare_ints(text: str, hinglish: bool) -> str:
    def repl(m: re.Match) -> str:
        n = int(m.group(1))
        return _hi_cardinal(n) if hinglish else _int_to_words_en(n)

    return _BARE_INT_RE.sub(repl, text)


# --------------------------------------------------------------------------- #
# public entry
# --------------------------------------------------------------------------- #
def normalize_text(text: str, lang: str = "en") -> str:
    """Render numbers/currency/phone/date/time/unit/percent/acronym to spoken
    words. `lang` selects the register: anything that looks Hindi/Hinglish gets
    the casual Hinglish words, else English. ORDER MATTERS — phone & currency &
    date & time consume their digits BEFORE the bare-integer pass, so a price or
    a phone number is never re-read as a cardinal."""
    if not text:
        return text
    low = (lang or "").lower()
    hinglish = any(k in low for k in ("hi", "hing", "hindi", "deva"))
    out = text
    out = _normalize_currency(out, hinglish)   # ₹/Rs/lakh/crore — before phone/int
    out = _normalize_phone(out, hinglish)      # consumes long digit runs
    out = _normalize_time(out, hinglish)       # HH:MM before bare ints
    out = _normalize_date(out, hinglish)       # DD/MM before bare ints
    out = _normalize_percent(out, hinglish)
    out = _normalize_units(out)
    out = _split_digit_acronym(out)            # '2BHK' -> '2 BHK' before both passes
    out = _normalize_acronyms(out)
    out = _normalize_bare_long(out, hinglish)  # 4+ digit codes/years -> digit-by-digit
    out = _normalize_bare_ints(out, hinglish)  # 1-3 digit remainder -> cardinal
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out
