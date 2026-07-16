"""grow.advisor — "Proper Recommendation for Our Goal" + Chat over the ads data.

Turns the cross-platform snapshot (grow.platforms) into ranked, plain-language
recommendations toward a stated GOAL (min cost per outcome / max conversions / max reach),
reusing the W5 optimizer's bounded allocation across platforms-as-arms + the cheapest/best
insights. And a CHAT that answers natural-language questions over the same data — fully
deterministic so it works with zero LLM, with an optional LLM narrative seam (dormant by
default). stdlib only; never raises."""
from __future__ import annotations

import logging
from typing import Optional

from .optimizer import Arm, Optimizer

log = logging.getLogger("grow.advisor")

GOALS = ("min_cost", "max_conversions", "max_reach")


def _money(minor: int, currency: str = "INR") -> str:
    if not minor:
        return "—"
    major = minor / 100.0
    sym = "₹" if currency == "INR" else ("$" if currency == "USD" else "")
    try:
        return f"{sym}{major:,.0f}"
    except Exception:  # noqa: BLE001
        return f"{sym}{major}"


def _pct(x: float) -> str:
    return f"{round((x or 0) * 100, 2)}%"


class Advisor:
    def __init__(self, optimizer: Optional[Optimizer] = None):
        self.optimizer = optimizer or Optimizer()

    # --------------------------------------------------------- recommend #
    def recommend(self, snapshot: dict, *, goal: str = "min_cost") -> dict:
        """Rank the platforms toward the goal + emit plain-language recommendations and a
        suggested budget reallocation (optimizer.allocate over platforms-as-arms)."""
        try:
            return self._recommend(snapshot, goal)
        except Exception as exc:  # noqa: BLE001
            log.info("grow.advisor.recommend failed: %r", exc)
            return {"goal": goal, "recommendations": [], "allocation": {},
                    "summary_text": "Could not compute recommendations yet."}

    def _recommend(self, snapshot: dict, goal: str) -> dict:
        goal = goal if goal in GOALS else "min_cost"
        summ = snapshot.get("summary", {}) or {}
        plats = [p for p in (snapshot.get("platforms") or [])
                 if p.get("status") in ("live", "demo") and p.get("spend_minor", 0) > 0]
        cur = summ.get("currency", "INR")
        recs: list = []

        # 1) shift budget to the cheapest cost-per-outcome platform (min_cost goal)
        cheapest = summ.get("cheapest_cpi")
        best_cvr = summ.get("best_cvr")
        best_ctr = summ.get("best_ctr")
        top = summ.get("top_spender")

        if goal == "min_cost" and cheapest:
            recs.append({
                "action": "shift_budget",
                "platform": cheapest["platform"],
                "text": f"Shift budget toward {cheapest['label']}: it has the lowest cost per "
                        f"outcome at {_money(cheapest['value'], cur)} — cheaper real customers.",
                "impact": "high"})
        if goal == "max_conversions" and best_cvr:
            recs.append({
                "action": "scale", "platform": best_cvr["platform"],
                "text": f"Scale {best_cvr['label']}: highest conversion rate "
                        f"({_pct(best_cvr['value'])}) — most outcomes per click.",
                "impact": "high"})
        if goal == "max_reach" and best_ctr:
            recs.append({
                "action": "scale", "platform": best_ctr["platform"],
                "text": f"Lean into {best_ctr['label']}: best CTR ({_pct(best_ctr['value'])}) — "
                        f"cheapest attention for reach.",
                "impact": "medium"})

        # 2) trim the most expensive-per-outcome platform (any goal)
        worst = max(plats, key=lambda p: p.get("cpi_minor", 0), default=None)
        if worst and worst.get("cpi_minor", 0) > 0 and (not cheapest or worst["platform"] != cheapest["platform"]):
            recs.append({
                "action": "trim", "platform": worst["platform"],
                "text": f"Trim {worst.get('label')}: highest cost per outcome "
                        f"({_money(worst['cpi_minor'], cur)}) — reallocate to cheaper channels.",
                "impact": "medium"})

        # 3) same-type ads -> diversify (Andromeda dedupe risk)
        same = summ.get("same_type_ads") or []
        if same:
            top_overlap = same[0]
            recs.append({
                "action": "diversify",
                "text": f"You're running the same '{top_overlap['concept']}' concept on "
                        f"{', '.join(top_overlap['platforms'])}. Diversify creative to dodge "
                        f"near-duplicate suppression and find new winners.",
                "impact": "medium"})

        # 4) optimizer-backed budget reallocation across platforms (bounded allocation)
        arms = [Arm(id=p["platform"], name=p.get("label", p["platform"]),
                    spend_minor=int(p.get("spend_minor", 0)),
                    qualified_leads=int(p.get("conversions", 0)),
                    leads=int(p.get("clicks", 0)))
                for p in plats]
        target = summ.get("avg_cpi_minor", 0) or 0
        allocation = self.optimizer.allocate(arms, target) if arms else {}
        alloc_named = [{"platform": k, "label": next((p.get("label") for p in plats if p["platform"] == k), k),
                        "share": v} for k, v in sorted(allocation.items(), key=lambda kv: -kv[1])]

        summary_text = self._summary_text(summ, goal, recs, cur)
        return {"goal": goal, "recommendations": recs, "allocation": alloc_named,
                "summary_text": summary_text}

    def _summary_text(self, summ: dict, goal: str, recs: list, cur: str) -> str:
        parts = []
        ap = summ.get("active_platforms", 0)
        parts.append(f"{ap} of {summ.get('total_platforms', 0)} platforms active.")
        if summ.get("total_spend_minor"):
            parts.append(f"Total spend {_money(summ['total_spend_minor'], cur)} "
                         f"→ {summ.get('total_conversions', 0)} outcomes "
                         f"(avg {_money(summ.get('avg_cpi_minor', 0), cur)}/outcome).")
        ch = summ.get("cheapest_cpi")
        if ch:
            parts.append(f"Cheapest outcomes: {ch['label']} ({_money(ch['value'], cur)}).")
        if recs:
            parts.append(recs[0]["text"])
        return " ".join(parts)

    # ----------------------------------------------------------------- chat #
    def chat(self, snapshot: dict, question: str) -> dict:
        """Answer a natural-language question over the ads data. Deterministic intent match
        (works with zero LLM); returns {answer, intent, used}."""
        try:
            return self._chat(snapshot, question)
        except Exception as exc:  # noqa: BLE001
            log.info("grow.advisor.chat failed: %r", exc)
            return {"answer": "I couldn't read the data just now — try again.",
                    "intent": "error", "used": "deterministic"}

    def _chat(self, snapshot: dict, question: str) -> dict:
        q = (question or "").lower().strip()
        summ = snapshot.get("summary", {}) or {}
        cur = summ.get("currency", "INR")
        if not q:
            return {"answer": "Ask me anything about your ads — cheapest platform, total spend, "
                              "best CTR, what to do next…", "intent": "empty", "used": "deterministic"}

        def has(*words):
            return any(w in q for w in words)

        # recommendation / what should I do
        if has("recommend", "should i", "what to do", "advice", "improve", "optimi"):
            goal = ("max_conversions" if has("conversion", "lead", "sale") else
                    "max_reach" if has("reach", "awareness") else "min_cost")
            rec = self.recommend(snapshot, goal=goal)
            tip = rec["recommendations"][0]["text"] if rec["recommendations"] else rec["summary_text"]
            return {"answer": tip, "intent": "recommend", "used": "deterministic"}
        # cheapest
        if has("cheapest", "lowest cost", "least expensive", "best value"):
            ch = summ.get("cheapest_cpi") or summ.get("cheapest_cpc")
            if ch:
                return {"answer": f"{ch['label']} is cheapest at {_money(ch['value'], cur)} per outcome.",
                        "intent": "cheapest", "used": "deterministic"}
        # best CTR / engagement
        if has("best ctr", "highest ctr", "engagement", "click rate", "click-through"):
            b = summ.get("best_ctr")
            if b:
                return {"answer": f"{b['label']} has the best CTR at {_pct(b['value'])}.",
                        "intent": "best_ctr", "used": "deterministic"}
        # best conversion
        if has("best conver", "highest conver", "convert best", "conversion rate"):
            b = summ.get("best_cvr")
            if b:
                return {"answer": f"{b['label']} converts best at {_pct(b['value'])}.",
                        "intent": "best_cvr", "used": "deterministic"}
        # total spend
        if has("total spend", "how much", "spent", "budget", "cost so far"):
            return {"answer": f"Total spend is {_money(summ.get('total_spend_minor', 0), cur)} across "
                              f"{summ.get('active_platforms', 0)} platforms, for "
                              f"{summ.get('total_conversions', 0)} outcomes "
                              f"(avg {_money(summ.get('avg_cpi_minor', 0), cur)}/outcome).",
                    "intent": "total_spend", "used": "deterministic"}
        # conversions / outcomes
        if has("how many", "conversion", "leads", "outcomes", "results"):
            return {"answer": f"{summ.get('total_conversions', 0)} outcomes from "
                              f"{summ.get('total_clicks', 0)} clicks "
                              f"(CTR {_pct(summ.get('avg_ctr', 0))}).",
                    "intent": "conversions", "used": "deterministic"}
        # same-type ads
        if has("same", "duplicate", "overlap", "repeat"):
            same = summ.get("same_type_ads") or []
            if same:
                s = same[0]
                return {"answer": f"You're running the same '{s['concept']}' concept on "
                                  f"{', '.join(s['platforms'])} — consider diversifying.",
                        "intent": "same_type", "used": "deterministic"}
            return {"answer": "No major same-type-ad overlap detected across platforms.",
                    "intent": "same_type", "used": "deterministic"}
        # which platforms active
        if has("which platform", "what platform", "active", "running"):
            keys = summ.get("active_platform_keys") or []
            return {"answer": f"Active platforms: {', '.join(keys) or 'none yet'}.",
                    "intent": "active", "used": "deterministic"}
        # fallback -> the summary line
        return {"answer": self._summary_text(summ, "min_cost", [], cur)
                or "Connect your ad platforms to see insights here.",
                "intent": "summary", "used": "deterministic"}


_ADVISOR = Advisor()


def recommend(snapshot: dict, *, goal: str = "min_cost") -> dict:
    return _ADVISOR.recommend(snapshot, goal=goal)


def chat(snapshot: dict, question: str) -> dict:
    return _ADVISOR.chat(snapshot, question)
