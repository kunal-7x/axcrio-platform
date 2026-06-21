#!/usr/bin/env python3
# FINAL-FIX patch: wire frequency_penalty/presence_penalty into the hot-path groq.LLM
# via the OpenAI plugin's _opts.extra_body forwarding (groq.LLM extends OpenAILLM; its
# __init__ does NOT accept frequency_penalty/extra_body, but chat() forwards
# self._opts.extra_body into chat.completions.create(**extra_kwargs) -> Groq API).
# Mechanism verified on box: openai/llm.py chat() lines 958-959 + _LLMOptions.extra_body.
import io, sys, re

PATH = "/opt/famit-agent/agent.py"
with io.open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

# --- Anchor 1: the exact inline construction block (must be present, exactly once) ---
old_block = (
    "        llm=groq.LLM(\n"
    "            model=os.getenv(\"GROQ_LLM_MODEL\", \"meta-llama/llama-4-scout-17b-16e-instruct\"),\n"
    "            api_key=_call_groq_key,\n"
    "            temperature=float(os.getenv(\"GROQ_LLM_TEMPERATURE\", \"0.3\")),\n"
)
if src.count(old_block) != 1:
    sys.exit("ABORT: llm=groq.LLM( anchor not found exactly once (count=%d)" % src.count(old_block))

# --- Anchor 2: the closing of the groq.LLM(...) call inside AgentSession ---
# the block ends with the max_completion_tokens line then a line "        ),"
close_anchor = (
    "            max_completion_tokens=int(os.getenv(\"GROQ_MAX_TOKENS\", \"90\")),\n"
    "        ),\n"
)
if src.count(close_anchor) != 1:
    sys.exit("ABORT: max_completion_tokens close anchor not found exactly once (count=%d)" % src.count(close_anchor))

# --- Anchor 3: where to insert the pre-built LLM (just before session = AgentSession() ---
sess_anchor = "    session = AgentSession(\n"
if src.count(sess_anchor) != 1:
    sys.exit("ABORT: 'session = AgentSession(' anchor not found exactly once (count=%d)" % src.count(sess_anchor))

# 1) Pre-build the hot LLM as a local var (same args), then attach extra_body penalties.
prebuild = (
    "    # FINAL-FIX (garbage/repetition cure): build the hot-path LLM first so we can\n"
    "    # attach a repetition penalty. groq.LLM extends the OpenAI plugin LLM; its __init__\n"
    "    # does NOT accept frequency_penalty/presence_penalty/extra_body, BUT the OpenAI\n"
    "    # plugin's chat() forwards self._opts.extra_body into chat.completions.create(...)\n"
    "    # (openai/llm.py: `extra[\"extra_body\"] = self._opts.extra_body`). Groq's API is\n"
    "    # OpenAI-compatible and honours frequency_penalty/presence_penalty as top-level\n"
    "    # request params. So we set _opts.extra_body AFTER construction = the only correct,\n"
    "    # non-crashing way to pass penalties through this plugin stack. The penalty stops the\n"
    "    # llama-4-scout repetition loop (\"yes yes yes\" / \"## Step 1\") at the source, which is\n"
    "    # what let GROQ_MAX_TOKENS=220 run to the cap. Env-overridable / fully reversible:\n"
    "    # GROQ_FREQ_PENALTY (default 0.5), GROQ_PRES_PENALTY (default 0.3); 0 disables either.\n"
    "    _hot_llm = groq.LLM(\n"
    "        model=os.getenv(\"GROQ_LLM_MODEL\", \"meta-llama/llama-4-scout-17b-16e-instruct\"),\n"
    "        api_key=_call_groq_key,\n"
    "        temperature=float(os.getenv(\"GROQ_LLM_TEMPERATURE\", \"0.3\")),\n"
    "        max_completion_tokens=int(os.getenv(\"GROQ_MAX_TOKENS\", \"90\")),\n"
    "    )\n"
    "    try:\n"
    "        _freq_pen = float(os.getenv(\"GROQ_FREQ_PENALTY\", \"0.5\") or 0.0)\n"
    "        _pres_pen = float(os.getenv(\"GROQ_PRES_PENALTY\", \"0.3\") or 0.0)\n"
    "        _pen_body = {}\n"
    "        if _freq_pen:\n"
    "            _pen_body[\"frequency_penalty\"] = _freq_pen\n"
    "        if _pres_pen:\n"
    "            _pen_body[\"presence_penalty\"] = _pres_pen\n"
    "        if _pen_body:\n"
    "            # merge with any existing extra_body the plugin may have set (NOT_GIVEN -> {})\n"
    "            _existing = getattr(_hot_llm._opts, \"extra_body\", None)\n"
    "            _merged = dict(_existing) if isinstance(_existing, dict) else {}\n"
    "            _merged.update(_pen_body)\n"
    "            _hot_llm._opts.extra_body = _merged\n"
    "            logger.info(\"FINAL-FIX repetition penalty wired: %s\", _pen_body)\n"
    "    except Exception as _pen_exc:  # noqa: BLE001 - never break a call over the penalty\n"
    "        logger.warning(\"FINAL-FIX penalty wiring skipped (non-fatal): %r\", _pen_exc)\n\n"
)

src = src.replace(sess_anchor, prebuild + sess_anchor, 1)

# 2) Replace the inline llm=groq.LLM(... full block ...) with llm=_hot_llm,
# Reconstruct the full inline block to remove (from old_block start through close_anchor).
start = src.index(old_block)
end = src.index(close_anchor, start) + len(close_anchor)
inline_full = src[start:end]
# sanity: the inline block must contain the construction + close
if "groq.LLM(" not in inline_full or "max_completion_tokens" not in inline_full:
    sys.exit("ABORT: inline block extraction failed")
src = src[:start] + "        llm=_hot_llm,\n" + src[end:]

with io.open(PATH, "w", encoding="utf-8", newline="\n") as f:
    f.write(src)

print("PATCH OK: pre-built _hot_llm + extra_body penalty wired; inline replaced with llm=_hot_llm")
