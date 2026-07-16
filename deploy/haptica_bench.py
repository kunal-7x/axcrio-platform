#!/usr/bin/env python3
"""
haptica_bench.py — COMPLETE advanced benchmark for the Haptica voice LLM (v2: Groq key-POOL).

Compares, apples-to-apples through ONE OpenAI-compatible harness, on OUR use case
(Hinglish real-estate telecalling, the riya/Joyville brain), and picks a WINNER:

    groq-70b          Groq llama-3.3-70b-versatile, over a KEY POOL (429 failover)  GROQ_API_KEYS
    sarvam-30b        Sarvam conversational/voice SKU                               SARVAM_API_KEY / voice_keys.json
    sarvam-30b-strict same model, temp 0.2 / max_tok 140 (probe 30b's ceiling)
    sarvam-105b       Sarvam reasoning SKU

WHY v2: the first run disqualified Groq because a SINGLE key hit its daily cap (20/20 429s, 12.4s).
This version rotates a POOL of Groq keys and fails over on 429 — so Groq gets a FAIR, uncapped shot.
It also adds a low-temp "strict" 30b arm to see if sarvam-30b, tuned to its max, can outperform all.

FOUR parts:
  A) LATENCY      single-turn suite -> p50/p90/p99 TTFT, thinking-leak check
  B) CONVERSATION 8 fixed multi-turn scenarios -> transcripts + objective repetition/loop score
  C) STRESS       concurrency p50/p95/p99 + rate-cap burst probe (now pool-aware: counts key failovers)
  D) JUDGE+RANK   optional frontier judge (OpenRouter) -> composite = 0.5*quality+0.3*latency+0.2*reliability

Each model TUNED to its best (reasoning OFF for Sarvam via extra_body reasoning_effort=None). Same
brain (set BRAIN_FILE=/tmp/brain.txt -> v10 guardrail brain) for all so the MODEL is the only variable.

RUN FROM THE INDIA BOX inside the worker (deploy/run-haptica-bench.sh does it):
    docker exec -e BRAIN_FILE=/tmp/brain.txt -e GROQ_API_KEYS="gsk_a,gsk_b,..." \
        [-e OPENROUTER_API_KEY=sk-or-...] haptica-ai-worker-1 python /tmp/haptica_bench.py

OUTPUT: console scorecard + /tmp/haptica_bench_results.{json,md}. No judge key -> transcripts handed
back for external frontier judging (ranking then uses latency+reliability only).

Tunables (env): BENCH_REPEATS(3) BENCH_WARMUP(1) STRESS_CONCURRENCY(8) STRESS_ROUNDS(2)
  CAP_PROBE_N(24) JUDGE_MODEL(google/gemini-2.0-flash-001) W_QUALITY(0.5) W_LATENCY(0.3) W_RELIABILITY(0.2)
"""
import concurrent.futures
import json
import os
import re
import statistics
import time

from openai import OpenAI

REPEATS = int(os.getenv("BENCH_REPEATS", "3"))
WARMUP = int(os.getenv("BENCH_WARMUP", "1"))
SLEEP = float(os.getenv("BENCH_SLEEP", "0.35"))
STRESS_CONCURRENCY = int(os.getenv("STRESS_CONCURRENCY", "8"))
STRESS_ROUNDS = int(os.getenv("STRESS_ROUNDS", "2"))
CAP_PROBE_N = int(os.getenv("CAP_PROBE_N", "24"))
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "google/gemini-2.0-flash-001")
W_QUALITY = float(os.getenv("W_QUALITY", "0.5"))
W_LATENCY = float(os.getenv("W_LATENCY", "0.3"))
W_RELIABILITY = float(os.getenv("W_RELIABILITY", "0.2"))
BENCH_ONLY = [x.strip() for x in os.getenv("BENCH_ONLY", "").split(",") if x.strip()]  # e.g. "sarvam-105b,groq-70b"


# ------------------------------------------------------------------ keys (env + voice_keys.json)
def load_keys():
    k = {}
    pool = os.getenv("GROQ_API_KEYS", "")
    if not pool:
        pf = os.getenv("GROQ_POOL_FILE", "/tmp/groq_pool.txt")
        if os.path.exists(pf):
            pool = ",".join(line.strip() for line in open(pf) if line.strip())
    if not pool:
        pool = os.getenv("GROQ_API_KEY", "")
    k["groq"] = [x.strip() for x in pool.split(",") if x.strip()]
    sv = os.getenv("SARVAM_API_KEY", "")
    if not sv:
        try:
            d = json.load(open(os.getenv("VOICE_KEYS", "/data/voice_keys.json")))
            sv = d.get("sarvam_llm_api_key") or d.get("sarvam_api_key") or ""
        except Exception as e:
            print(f"[keys] could not read voice_keys.json for Sarvam key: {e}")
    k["sarvam"] = [sv] if sv else []
    k["judge"] = os.getenv("OPENROUTER_API_KEY", "") or os.getenv("JUDGE_API_KEY", "")
    return k


KEYS = load_keys()
print(f"[keys] groq pool size={len(KEYS['groq'])}  sarvam={'yes' if KEYS['sarvam'] else 'NO'}  judge={'yes' if KEYS['judge'] else 'no'}")

# ------------------------------------------------------------------ brain (system prompt)
_bf = os.getenv("BRAIN_FILE", "")
if _bf and os.path.exists(_bf):
    BRAIN = open(_bf).read()
else:
    BRAIN = ("तुम रिया हो — Joyville Sensorium (Shapoorji Pallonji, Hinjawadi Pune) की senior sales consultant। "
             "हमेशा 'आप' + नाम के साथ 'जी'; कभी तू/तुम नहीं। हर जवाब छोटा, गर्मजोशी से, मकसद के साथ। "
             "2 BHK चौरासी point नौ-नौ लाख से, 3 BHK एक करोड़ बत्तीस लाख। बातचीत करो, पूछताछ नहीं।")
    print("[brain] BRAIN_FILE not set/found -> tiny fallback brain (set BRAIN_FILE=/tmp/brain.txt)")

# ------------------------------------------------------------------ models under test (tuned per model)
MODELS = [
    {"name": "groq-70b", "base": "https://api.groq.com/openai/v1",
     "model": os.getenv("GROQ_BENCH_MODEL", "llama-3.3-70b-versatile"),
     "keys": KEYS["groq"], "think": "none", "temp": 0.4, "max_tok": 160},
    {"name": "sarvam-30b", "base": "https://api.sarvam.ai/v1",
     "model": "sarvam-30b", "keys": KEYS["sarvam"], "think": "effort_none", "temp": 0.35, "max_tok": 150},
    {"name": "sarvam-30b-strict", "base": "https://api.sarvam.ai/v1",
     "model": "sarvam-30b", "keys": KEYS["sarvam"], "think": "effort_none", "temp": 0.2, "max_tok": 140},
    {"name": "sarvam-105b", "base": "https://api.sarvam.ai/v1",
     "model": "sarvam-105b", "keys": KEYS["sarvam"], "think": "effort_none", "temp": 0.3, "max_tok": 160},
]


def _params(m):
    kw, extra = {}, {}
    if m["think"] == "effort_low":
        kw["reasoning_effort"] = "low"
    elif m["think"] == "effort_none":
        extra["reasoning_effort"] = None     # Sarvam default ON; send null via extra_body to disable
    return kw, extra


def run_turn(client, m, messages):
    """One streaming chat call. -> (ttft_s, total_s, n_tok, text, thinking_leaked)."""
    kw, extra = _params(m)
    req = dict(model=m["model"], messages=messages, temperature=m["temp"],
               max_tokens=m["max_tok"], stream=True, **kw)
    if extra:
        req["extra_body"] = extra
    t0 = time.time()
    ttft = None
    out, ntok, leaked = [], 0, False
    stream = client.chat.completions.create(**req)
    for ch in stream:
        if not ch.choices:
            continue
        delta = ch.choices[0].delta
        if getattr(delta, "reasoning_content", None):
            leaked = True
        d = delta.content
        if d:
            if ttft is None:
                ttft = time.time() - t0
            out.append(d)
            ntok += 1
    return (ttft or (time.time() - t0)), (time.time() - t0), ntok, "".join(out), leaked


class Caller:
    """Wraps one or more API keys; round-robins and FAILS OVER to the next key on 429 (Groq pool)."""
    def __init__(self, m):
        self.m = m
        self.clients = [OpenAI(base_url=m["base"], api_key=k, timeout=90) for k in m["keys"]]
        self.i = 0
        self.failovers = 0   # how many times a 429 forced a key switch (reliability signal)

    def run(self, messages):
        n = max(1, len(self.clients))
        last = None
        for _ in range(n):
            c = self.clients[self.i % n]
            self.i += 1
            try:
                return run_turn(c, self.m, messages)
            except Exception as e:
                last = e
                msg = str(e)
                if "429" in msg or "rate" in msg.lower() or "quota" in msg.lower():
                    self.failovers += 1
                    continue   # try next key in the pool
                raise
        raise last


# ------------------------------------------------------------------ A) LATENCY (single-turn)
LAT_TESTS = [
    ("opener", "हाँ जी बताइए, क्या बात है?"),
    ("price", "2 BHK का price क्या है?"),
    ("emi-complex", "85 लाख का घर लूँ, 20% down, बाकी 8.5% पे 20 साल — monthly EMI लगभग कितनी?"),
    ("compare", "2 BHK और 3 BHK में investment के लिए rental yield किसका better और क्यों?"),
    ("objection", "भाई बहुत महँगा है, पास में सस्ता project मिल रहा है।"),
    ("lang-en", "Can you tell me the amenities and possession date in English?"),
    ("trust", "आप log genuine हो ना? पहले एक builder ने धोखा दिया था।"),
    ("book", "ठीक है, इस Saturday शाम site देखनी है।"),
]


def bench_latency(caller, m):
    rows = []
    for _ in range(WARMUP):
        try:
            caller.run([{"role": "system", "content": BRAIN}, {"role": "user", "content": "Hi"}])
        except Exception:
            pass
        time.sleep(SLEEP)
    for tag, user in LAT_TESTS:
        ttfts, totals, last_text, leaked = [], [], "", False
        for _ in range(REPEATS):
            try:
                ttft, total, ntok, text, lk = caller.run(
                    [{"role": "system", "content": BRAIN}, {"role": "user", "content": user}])
                ttfts.append(ttft * 1000)
                totals.append(total * 1000)
                last_text, leaked = text, leaked or lk
            except Exception as e:
                rows.append({"tag": tag, "error": f"{type(e).__name__}: {str(e)[:160]}", "q": user})
            time.sleep(SLEEP)
        if ttfts:
            rows.append({"tag": tag, "ttft_ms": round(statistics.median(ttfts)),
                         "total_ms": round(statistics.median(totals)), "leaked": leaked,
                         "q": user, "a": last_text.strip()})
    oks = [r for r in rows if "ttft_ms" in r]
    summ = None
    if oks:
        tt = sorted(r["ttft_ms"] for r in oks)
        summ = {"p50_ttft_ms": tt[len(tt) // 2],
                "p90_ttft_ms": tt[min(len(tt) - 1, int(len(tt) * 0.9))],
                "p99_ttft_ms": tt[-1],
                "median_total_ms": round(statistics.median(r["total_ms"] for r in oks)),
                "thinking_leaked": any(r.get("leaked") for r in oks),
                "errors": sum(1 for r in rows if "error" in r)}
    return {"summary": summ, "rows": rows}


# ------------------------------------------------------------------ B) CONVERSATION (multi-turn)
SCENARIOS = {
    "normal-flow": ["हाँ बताइए", "2 BHK में interest है", "खुद के रहने के लिए",
                    "price क्या रहेगा?", "ठीक है, एक बार देखना चाहूँगा"],
    "ambiguous-loop-trap": ["हाँ जी बोलिए", "बताइए", "आगे बोलिए", "हाँ हाँ आगे", "और बताओ"],
    "price-objection": ["price बताइए", "अरे बहुत महँगा है", "पास में दूसरा project सस्ता मिल रहा है",
                        "अच्छा फिर 2 BHK ही दिखाओ"],
    "code-switch": ["can you explain the project in English?", "अब Hindi में amenities बताओ",
                    "2 BHK की EMI कितनी बनेगी?", "ठीक है"],
    "adversarial-repeat": ["आपने क्यों call किया है?", "क्यों call किया?", "मतलब क्या?",
                           "हाँ पर असल में क्यों?", "ओके समझ गया"],
    "hello-recovery": ["Hello?", "आवाज़ नहीं आ रही थी", "हाँ अब बोलिए", "क्या project है ये?"],
    "trust-rapport": ["आप genuine हो ना? पहले एक builder ने पैसा लेके project लटका दिया था",
                      "ठीक है पर guarantee क्या है?", "अच्छा site कहाँ है?"],
    "complex-q": ["2 vs 3 BHK में rental income के लिए कौन better रहेगा और क्यों?",
                  "और resale value के हिसाब से?", "ठीक है weekend पे आता हूँ"],
}


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^ऀ-ॿa-zA-Z ]", "", s.lower())).strip()


def repetition_score(agent_turns):
    if len(agent_turns) < 2:
        return 0.0
    seen, dups = [], 0
    for t in agent_turns:
        p = _norm(t)[:50]
        if any(p and (p == s or (len(p) > 20 and p[:30] == s[:30])) for s in seen):
            dups += 1
        seen.append(p)
    return round(dups / len(agent_turns), 3)


def bench_conversation(caller, m):
    convos = {}
    for name, turns in SCENARIOS.items():
        msgs = [{"role": "system", "content": BRAIN}]
        transcript, ttfts, leaked, err = [], [], False, None
        for ut in turns:
            msgs.append({"role": "user", "content": ut})
            transcript.append({"role": "user", "text": ut})
            try:
                ttft, total, ntok, text, lk = caller.run(msgs)
            except Exception as e:
                err = f"{type(e).__name__}: {str(e)[:140]}"
                transcript.append({"role": "error", "text": err})
                break
            leaked = leaked or lk
            msgs.append({"role": "assistant", "content": text})
            transcript.append({"role": "agent", "text": text.strip()})
            ttfts.append(ttft * 1000)
            time.sleep(SLEEP)
        agent_turns = [t["text"] for t in transcript if t["role"] == "agent"]
        convos[name] = {"transcript": transcript, "median_ttft_ms": round(statistics.median(ttfts)) if ttfts else None,
                        "repetition_score": repetition_score(agent_turns), "leaked": leaked, "error": err}
    reps = [c["repetition_score"] for c in convos.values()]
    return {"scenarios": convos, "avg_repetition_score": round(statistics.mean(reps), 3) if reps else None,
            "errors": sum(1 for c in convos.values() if c["error"])}


# ------------------------------------------------------------------ C) STRESS (concurrency + cap probe)
def bench_stress(caller, m):
    msg = [{"role": "system", "content": BRAIN}, {"role": "user", "content": "2 BHK का price और location बताइए?"}]

    def one():
        t0 = time.time()
        try:
            caller.run(msg)
            return (time.time() - t0) * 1000, None
        except Exception as e:
            return None, f"{type(e).__name__}: {str(e)[:80]}"

    lat, errs = [], []
    for _ in range(STRESS_ROUNDS):
        with concurrent.futures.ThreadPoolExecutor(max_workers=STRESS_CONCURRENCY) as ex:
            for ms, er in ex.map(lambda _: one(), range(STRESS_CONCURRENCY)):
                (lat.append(ms) if ms is not None else errs.append(er))
        time.sleep(0.5)
    total = STRESS_CONCURRENCY * STRESS_ROUNDS
    conc = None
    if lat:
        s = sorted(lat)
        conc = {"p50_ms": round(s[len(s) // 2]), "p95_ms": round(s[min(len(s) - 1, int(len(s) * 0.95))]),
                "p99_ms": round(s[-1]), "ok": len(lat), "total": total,
                "error_rate": round(len(errs) / total, 3)}
    cap_429, cap_err = 0, 0
    for _ in range(CAP_PROBE_N):
        _, er = one()
        if er:
            cap_err += 1
            if "429" in er or "rate" in er.lower() or "quota" in er.lower():
                cap_429 += 1
    return {"concurrency": conc, "concurrency_errors": errs[:5],
            "cap_probe": {"n": CAP_PROBE_N, "rate_limit_hits": cap_429, "other_errors": cap_err - cap_429},
            "key_failovers": caller.failovers}


# ------------------------------------------------------------------ D) JUDGE (optional, frontier via OpenRouter)
JUDGE_RUBRIC = (
    "You are a veteran Hindi real-estate tele-sales trainer in Pune. Score this AI telecaller (Riya) "
    "across the multi-turn conversations below. Be CRITICAL and SPREAD scores 1-10. Penalize: looping/"
    "repeating, NOT progressing the pitch, informal register (तू/तुम, 'कैसे हो', bare first name, aimless "
    "chit-chat), robotic preamble, interrogation, markdown/stage-directions/writing the customer's lines, "
    "wrong price (the truth is 2BHK 84.99L, 3BHK 1.32cr, duplex 1.89cr), wrong language. Reward: natural warm "
    "spoken Hinglish, formal आप+जी, advancing the sale, varied rhythm, good objections. Return STRICT JSON only: "
    "{\"naturalness\":n,\"human_likeness\":n,\"register\":n,\"progression\":n,\"followup_quality\":n,"
    "\"objection_handling\":n,\"overall\":n,\"notes\":\"...\"}"
)


def judge_model(name, conv_result):
    if not KEYS["judge"]:
        return None
    blocks = []
    for sc, c in conv_result["scenarios"].items():
        lines = "\n".join(f"{t['role']}: {t['text']}" for t in c["transcript"])
        blocks.append(f"### scenario: {sc} (objective repetition_score={c['repetition_score']})\n{lines}")
    jc = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=KEYS["judge"], timeout=120)
    try:
        r = jc.chat.completions.create(
            model=JUDGE_MODEL, temperature=0.1, max_tokens=700,
            messages=[{"role": "system", "content": JUDGE_RUBRIC},
                      {"role": "user", "content": f"Telecaller model under review: {name}\n\n" + "\n\n".join(blocks)}])
        txt = r.choices[0].message.content
        mjson = re.search(r"\{.*\}", txt, re.S)
        return json.loads(mjson.group(0)) if mjson else {"error": "no json", "raw": txt[:300]}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:160]}"}


# ------------------------------------------------------------------ aggregate + rank + winner
def _norm_lower_better(vals):
    lo, hi = min(vals), max(vals)
    return [1.0 if hi == lo else (hi - v) / (hi - lo) for v in vals]


def rank(results):
    have_q = all(r.get("judge") and "overall" in (r["judge"] or {}) for r in results)
    lat = [r["latency"]["summary"]["p50_ttft_ms"] if r["latency"]["summary"] else 99999 for r in results]
    lat_n = _norm_lower_better(lat)
    for i, r in enumerate(results):
        cap = r["stress"]["cap_probe"]["rate_limit_hits"] / max(1, r["stress"]["cap_probe"]["n"])
        conc_err = r["stress"]["concurrency"]["error_rate"] if r["stress"]["concurrency"] else 1.0
        conv_err = r["conversation"]["errors"] / max(1, len(SCENARIOS))
        rep = r["conversation"]["avg_repetition_score"] or 0.0
        reliability = max(0.0, 1.0 - (0.45 * cap + 0.3 * conc_err + 0.15 * conv_err + 0.4 * rep))
        quality = ((r["judge"]["overall"] / 10.0) if have_q else 0.0)
        r["scores"] = {"quality": round(quality, 3), "latency": round(lat_n[i], 3), "reliability": round(reliability, 3)}
        if have_q:
            r["composite"] = round(W_QUALITY * quality + W_LATENCY * lat_n[i] + W_RELIABILITY * reliability, 4)
        else:
            r["composite"] = round((W_LATENCY * lat_n[i] + W_RELIABILITY * reliability) / (W_LATENCY + W_RELIABILITY), 4)
    results.sort(key=lambda r: r["composite"], reverse=True)
    return results, have_q


# ------------------------------------------------------------------ main
def main():
    print(f"Haptica advanced bench v2 | repeats={REPEATS} stress={STRESS_CONCURRENCY}x{STRESS_ROUNDS} "
          f"cap_probe={CAP_PROBE_N} | brain={len(BRAIN)}ch | judge={'ON ('+JUDGE_MODEL+')' if KEYS['judge'] else 'OFF'}")
    results = []
    for m in MODELS:
        if BENCH_ONLY and m["name"] not in BENCH_ONLY:
            continue
        if not m["keys"]:
            print(f"\n##### SKIP {m['name']} (no key) #####")
            continue
        print(f"\n{'='*84}\n### {m['name']}  model={m['model']}  temp={m['temp']}  pool={len(m['keys'])}\n{'='*84}")
        caller = Caller(m)
        print("  A) latency ...", flush=True)
        lat = bench_latency(caller, m)
        print("  B) conversation ...", flush=True)
        conv = bench_conversation(caller, m)
        print("  C) stress ...", flush=True)
        stress = bench_stress(caller, m)
        print("  D) judge ...", flush=True)
        jr = judge_model(m["name"], conv)
        s = lat["summary"]
        print(f"   -> p50 TTFT={s['p50_ttft_ms'] if s else 'ERR'}ms  avg_repetition={conv['avg_repetition_score']}  "
              f"cap_429={stress['cap_probe']['rate_limit_hits']}/{stress['cap_probe']['n']}  "
              f"key_failovers={stress['key_failovers']}  "
              f"{'thinking-LEAKED ' if (s and s['thinking_leaked']) else ''}"
              f"judge={jr.get('overall') if isinstance(jr, dict) else '-'}")
        results.append({"name": m["name"], "model": m["model"], "temp": m["temp"], "latency": lat,
                        "conversation": conv, "stress": stress, "judge": jr})

    ranked, have_q = rank(results)

    print(f"\n\n{'#'*92}\n# SCORECARD  (composite = {W_QUALITY}*quality + {W_LATENCY}*latency + {W_RELIABILITY}*reliability"
          f"{'' if have_q else '  — QUALITY UNSCORED (no judge): latency+reliability only'})\n{'#'*92}")
    hdr = (f"{'rank':<5}{'model':<19}{'composite':<11}{'quality':<9}{'p50TTFT':<9}{'repetition':<11}"
           f"{'cap429':<8}{'failovr':<8}{'reliab':<8}")
    print(hdr + "\n" + "-" * len(hdr))
    for i, r in enumerate(ranked, 1):
        s = r["latency"]["summary"]
        q = (str(r["judge"]["overall"]) + "/10") if (have_q and isinstance(r["judge"], dict) and "overall" in r["judge"]) else "-"
        print(f"{i:<5}{r['name']:<19}{r['composite']:<11}{q:<9}"
              f"{(str(s['p50_ttft_ms'])+'ms') if s else 'ERR':<9}"
              f"{str(r['conversation']['avg_repetition_score']):<11}"
              f"{str(r['stress']['cap_probe']['rate_limit_hits'])+'/'+str(r['stress']['cap_probe']['n']):<8}"
              f"{str(r['stress']['key_failovers']):<8}{r['scores']['reliability']:<8}")
    if ranked:
        w = ranked[0]
        print(f"\n>>> WINNER: {w['name']} ({w['model']}, temp={w['temp']})  composite={w['composite']}")
        if not have_q:
            print(">>> NOTE: no judge key -> naturalness/register UNSCORED. Hand haptica_bench_results.json "
                  "back for frontier judging to finalize quality.")

    out = {"params": {"repeats": REPEATS, "stress": [STRESS_CONCURRENCY, STRESS_ROUNDS], "cap_probe": CAP_PROBE_N,
                      "weights": [W_QUALITY, W_LATENCY, W_RELIABILITY], "brain_chars": len(BRAIN),
                      "groq_pool": len(KEYS["groq"]), "judge": JUDGE_MODEL if KEYS["judge"] else None},
           "ranked": ranked}
    with open("/tmp/haptica_bench_results.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    with open("/tmp/haptica_bench_results.md", "w") as f:
        f.write("# Haptica advanced LLM benchmark (v2, Groq pool)\n\n")
        for i, r in enumerate(ranked, 1):
            s = r["latency"]["summary"]
            f.write(f"## #{i} {r['name']} ({r['model']}, temp {r['temp']}) — composite {r['composite']}\n")
            f.write((f"- p50/p90/p99 TTFT: {s['p50_ttft_ms']}/{s['p90_ttft_ms']}/{s['p99_ttft_ms']}ms\n") if s else "- latency: ERROR\n")
            f.write(f"- avg repetition (loop) score: {r['conversation']['avg_repetition_score']}\n")
            f.write(f"- stress p95: {r['stress']['concurrency']['p95_ms'] if r['stress']['concurrency'] else 'ERR'}ms, "
                    f"cap-429: {r['stress']['cap_probe']['rate_limit_hits']}/{r['stress']['cap_probe']['n']}, "
                    f"key-failovers: {r['stress']['key_failovers']}\n")
            if isinstance(r["judge"], dict) and "overall" in r["judge"]:
                f.write(f"- judge: {json.dumps(r['judge'], ensure_ascii=False)}\n")
            f.write("\n### conversations\n")
            for sc, c in r["conversation"]["scenarios"].items():
                f.write(f"\n**{sc}** (rep={c['repetition_score']}{', ERROR='+c['error'] if c['error'] else ''})\n\n")
                for t in c["transcript"]:
                    f.write(f"- {t['role']}: {t['text']}\n")
            f.write("\n---\n\n")
    print("\nSaved: /tmp/haptica_bench_results.json  +  /tmp/haptica_bench_results.md")


if __name__ == "__main__":
    main()
