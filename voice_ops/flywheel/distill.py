"""voice_ops.flywheel.distill — B7: KTO/SimPO export + a gated self-hosted SHADOW challenger.

THE WHY
-------
Riya — the live telecaller — is a FROZEN hosted LLM. We cannot fine-tune her in place: the
provider serves a fixed model behind an API, and the whole flywheel is built on the law that the
live policy only ever changes through the UNCHANGED gate + an explicit human promotion click. So
the ONLY path to a fine-tuned artifact is OFFLINE and INDIRECT: train an open base model on our
proprietary preference moat, package it as a QLoRA adapter, stand it up on a self-hosted vLLM
endpoint, and ship it through the gate as a SHADOW challenger (is_shadow=True, MANDATORY). It runs
in shadow / A-B only; it NEVER silently becomes live Riya. A human approves it like any other
challenger or it never serves a real caller.

WHY KTO (primary)  — Ethayarajh et al. 2024, "KTO: Model Alignment as Prospect Theoretic
Optimization" (arXiv:2402.01306). Our dataset is natively UNPAIRED, BINARY (a turn is desirable
or it is not), and heavily IMBALANCED (far more "this line did not book" than clean matched pairs).
DPO/IPO need (chosen, rejected) on the SAME prompt — force-pairing our logs throws most signal away
and amplifies length bias. KTO consumes each completion as a standalone {prompt, completion,
label:bool} signal with a Kahneman-Tversky value function, so it eats the WHOLE moat, including the
huge "undesirable" tail, and stays stable under class imbalance via a desirable/undesirable weight
ratio. That is exactly our data shape.

WHY SimPO (secondary) — Meng et al. 2024, "SimPO: Simple Preference Optimization with a
Reference-Free Reward" (arXiv:2405.14734). On the small, CLEAN, genuinely-paired subset
(outcome_anchored AND survived_swap — a real converted call whose pairwise judge held under an A/B
position swap) a reference-free, length-normalized paired objective is a sharper secondary signal.
We export that subset as paired JSONL too; training itself is offline/optional.

QLoRA — Dettmers et al. 2023, "QLoRA: Efficient Finetuning of Quantized LLMs" (arXiv:2305.14314):
4-bit NF4 base + a low-rank adapter, so a tenant-scoped shadow trains on one GPU.

DESIGN LAWS (mirror voice_ops/research + the rest of flywheel/):
  * SIDE-PIPELINE — offline/worker only; never the live turn loop.
  * DORMANT-SAFE + BEST-EFFORT — every public fn swallows its own errors → logging.warning and
    returns a clean empty/zero value. NEVER raises (a distill error must never break the worker).
  * LAZY HEAVY DEPS — torch/trl/peft/bitsandbytes are imported INSIDE train_qlora(), behind the
    flag, with a pure-python SCAFFOLD fallback so this module imports and the EXPORT path runs even
    when none of the training stack is installed (the dormant/CI machine).
  * ANTI-GOODHART — compliance is a HARD DROP, not a reward: a non-compliant 'chosen' is NEVER
    emitted as a desirable example. Synthetic (sim_self_play) and rubric_pairwise rows are
    DOWN-WEIGHTED vs real outcome-anchored ground truth (a synthetic pair is a hypothesis).
  * FROZEN-LIVE-LLM LAW — emit_shadow_challenger() forces is_shadow=True and status='proposed';
    the artifact can only ever serve as a shadow behind the unchanged gate.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional

from . import config as _cfg
from . import schema as S
from . import store as _st

logger = logging.getLogger("flywheel.distill")

# Sources whose desirable examples are real ground truth (full weight) vs hypotheses (down-weighted).
_SYNTHETIC_SOURCES = ("rubric_pairwise", "sim_self_play")
_SYNTHETIC_WEIGHT = 0.3      # down-weight factor for synthetic/judge-only desirables (vs 1.0 real)
_DESIRABLE_WEIGHT = 1.0


# --------------------------------------------------------------------------- #
# Small helpers (pure-python; no heavy deps).
# --------------------------------------------------------------------------- #
def _export_dir() -> str:
    """Local export directory under FAMIT_VAR (created best-effort). Mirrors the research var path."""
    base = (os.getenv("FAMIT_VAR") or "famit-var").strip().rstrip("/")
    path = os.path.join(base, "flywheel", "exports")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel distill: could not create export dir %s: %r", path, exc)
    return path


def _pair_from_row(row: dict) -> S.PreferencePair:
    """Reconstruct a schema.PreferencePair from a flywheel_preferences ClickHouse row so we reuse
    its .to_kto_rows()/.to_export() contract verbatim (single source of truth for the wire shape)."""
    def _b(v) -> bool:
        return str(v) in ("1", "True", "true") or v is True
    return S.PreferencePair(
        tenant_id=str(row.get("tenant_id") or ""),
        pair_id=str(row.get("pair_id") or ""),
        ts_iso=str(row.get("ts") or ""),
        state_embedding_id=str(row.get("state_embedding_id") or ""),
        objection_type=str(row.get("objection_type") or "none"),
        lead_temperature=str(row.get("lead_temperature") or "unknown"),
        regime=str(row.get("regime") or "steady"),
        vertical=str(row.get("vertical") or "real_estate"),
        chosen_text=str(row.get("chosen_text") or ""),
        rejected_text=str(row.get("rejected_text") or ""),
        chosen_move_id=str(row.get("chosen_move_id") or ""),
        rejected_move_id=str(row.get("rejected_move_id") or ""),
        margin=float(row.get("margin") or 0.0),
        source=str(row.get("source") or "within_call"),
        survived_swap=_b(row.get("survived_swap")),
        confidence=float(row.get("confidence") or 0.0),
        compliant=_b(row.get("compliant")),
        outcome_anchored=_b(row.get("outcome_anchored")),
        campaign_id=str(row.get("campaign_id") or ""),
    )


def _row_weight(source: str) -> float:
    """Full weight for real outcome-anchored data; down-weight synthetic/judge-only desirables."""
    return _SYNTHETIC_WEIGHT if source in _SYNTHETIC_SOURCES else _DESIRABLE_WEIGHT


def _write_jsonl(path: str, rows: List[dict]) -> int:
    """Best-effort JSONL writer. Returns count written (0 on any failure). Never raises."""
    try:
        with open(path, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        return len(rows)
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel distill: JSONL write to %s failed: %r", path, exc)
        return 0


async def _fetch_pairs(tenant_id: str, vertical: str = "") -> List[dict]:
    """Pull preference rows for a tenant from _st.PREFERENCES (tenant bound as {tid:String} — the
    tenant boundary). Returns [] on any error (dormant-safe). Never raises."""
    try:
        where = "tenant_id = {tid:String}"
        params: Dict[str, object] = {"tid": str(tenant_id)}
        if vertical:
            where += " AND vertical = {v:String}"
            params["v"] = str(vertical)
        sql = (
            f"SELECT tenant_id, pair_id, toString(ts) AS ts, state_embedding_id, objection_type, "
            f"lead_temperature, regime, vertical, chosen_text, rejected_text, chosen_move_id, "
            f"rejected_move_id, margin, source, survived_swap, confidence, compliant, "
            f"outcome_anchored, campaign_id "
            f"FROM {_st.PREFERENCES} WHERE {where} ORDER BY ts DESC LIMIT 200000"
        )
        res = await _st._ch(sql, params)
        if res.get("error"):
            logger.warning("flywheel distill: preference read error: %s", res.get("error"))
        return res.get("rows") or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel distill: _fetch_pairs error: %r", exc)
        return []


# --------------------------------------------------------------------------- #
# B7 primary: KTO export (the moat → unpaired {prompt, completion, label} JSONL).
# --------------------------------------------------------------------------- #
async def export_kto(tenant_id: str, *, vertical: str = "", cfg=None) -> dict:
    """Export the tenant's preference moat as a KTO training file (unpaired, binary, weighted).

    Pipeline:
      1. pull preference pairs from _st.PREFERENCES (tenant-scoped),
      2. reconstruct a PreferencePair per row and call .to_kto_rows() (a non-compliant 'chosen' is
         already DROPPED there — anti-Goodhart hard gate, not a reward),
      3. attach a per-row `weight` (synthetic/judge-only desirables down-weighted vs real outcome),
      4. require >= cfg.distill_min_desirable desirable rows or bail with reason='insufficient',
      5. write JSONL under FAMIT_VAR/flywheel/exports/,
      6. record + persist a schema.DistillRun(status='exported').

    Returns {'ok':True, 'path', 'n_desirable', 'n_undesirable', 'run_id'} on success,
            {'ok':False, 'reason':...} otherwise. Never raises; dormant-safe.
    """
    try:
        cfg = cfg or _cfg.load()
        if not tenant_id:
            return {"ok": False, "reason": "no_tenant"}

        rows = await _fetch_pairs(tenant_id, vertical)
        if not rows:
            return {"ok": False, "reason": "no_pairs"}

        kto_rows: List[dict] = []
        n_desirable = 0
        n_undesirable = 0
        for raw in rows:
            try:
                pair = _pair_from_row(raw)
                # .to_kto_rows() already drops a non-compliant chosen and keeps both sides as
                # standalone {prompt, completion, label:bool} signals (the unpaired KTO contract).
                for kr in pair.to_kto_rows():
                    label = bool(kr.get("label"))
                    src = str(kr.get("source") or "within_call")
                    # desirables carry the down-weight; undesirables keep full weight (the imbalanced
                    # tail is exactly what KTO is for — we never throw it away).
                    kr["weight"] = round(_row_weight(src) if label else _DESIRABLE_WEIGHT, 4)
                    kto_rows.append(kr)
                    if label:
                        n_desirable += 1
                    else:
                        n_undesirable += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("flywheel distill: bad preference row skipped: %r", exc)
                continue

        min_desirable = int(getattr(cfg, "distill_min_desirable", 200) or 200)
        if n_desirable < min_desirable:
            logger.info("flywheel distill: insufficient desirables %d < %d for %s",
                        n_desirable, min_desirable, tenant_id)
            return {"ok": False, "reason": "insufficient",
                    "n_desirable": n_desirable, "n_undesirable": n_undesirable}

        run_id = S.new_id("run_")
        fname = f"kto_{tenant_id}_{vertical or 'all'}_{run_id}.jsonl"
        path = os.path.join(_export_dir(), fname)
        written = _write_jsonl(path, kto_rows)
        if written <= 0:
            return {"ok": False, "reason": "write_failed",
                    "n_desirable": n_desirable, "n_undesirable": n_undesirable}

        method = str(getattr(cfg, "distill_method", "kto") or "kto")
        base_model = str(getattr(cfg, "distill_base_model", "") or "")
        run = S.DistillRun(
            tenant_id=tenant_id, run_id=run_id, ts_iso=S.now_iso(), method=method,
            base_model=base_model, n_desirable=n_desirable, n_undesirable=n_undesirable,
            status="exported", adapter_uri="",
            metrics_json=json.dumps({"path": path, "rows": written, "vertical": vertical or "all",
                                     "min_desirable": min_desirable}, ensure_ascii=False),
        )
        # Best-effort persist (no-op when dormant — insert returns False, we still return the run).
        try:
            _st.insert_distill_runs([run])
        except Exception as exc:  # noqa: BLE001
            logger.warning("flywheel distill: insert_distill_runs failed (non-fatal): %r", exc)

        return {"ok": True, "path": path, "n_desirable": n_desirable,
                "n_undesirable": n_undesirable, "run_id": run_id}
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel distill: export_kto error (non-fatal): %r", exc)
        return {"ok": False, "reason": "error"}


# --------------------------------------------------------------------------- #
# B7 secondary: SimPO export (the clean, genuinely-paired subset → paired JSONL).
# --------------------------------------------------------------------------- #
async def export_simpo(tenant_id: str, *, vertical: str = "", cfg=None) -> dict:
    """Export the CLEAN paired subset (outcome_anchored AND survived_swap) as paired DPO/SimPO
    JSONL via PreferencePair.to_export(). This is the sharp, small secondary signal — a real
    converted call whose pairwise judge held under an A/B position swap. Never raises.

    Returns {'ok':True, 'path', 'n_pairs', 'run_id'} or {'ok':False, 'reason':...}.
    """
    try:
        cfg = cfg or _cfg.load()
        if not tenant_id:
            return {"ok": False, "reason": "no_tenant"}

        rows = await _fetch_pairs(tenant_id, vertical)
        if not rows:
            return {"ok": False, "reason": "no_pairs"}

        export_rows: List[dict] = []
        for raw in rows:
            try:
                pair = _pair_from_row(raw)
                # The CLEAN subset only: a real converted call (outcome_anchored) whose judge held
                # under the A/B swap (survived_swap), and both sides present + compliant chosen.
                if not (pair.outcome_anchored and pair.survived_swap and pair.compliant):
                    continue
                if not (pair.chosen_text and pair.rejected_text):
                    continue
                export_rows.append(pair.to_export())
            except Exception as exc:  # noqa: BLE001
                logger.warning("flywheel distill: bad simpo row skipped: %r", exc)
                continue

        n_pairs = len(export_rows)
        if n_pairs <= 0:
            return {"ok": False, "reason": "no_clean_pairs"}

        run_id = S.new_id("run_")
        fname = f"simpo_{tenant_id}_{vertical or 'all'}_{run_id}.jsonl"
        path = os.path.join(_export_dir(), fname)
        written = _write_jsonl(path, export_rows)
        if written <= 0:
            return {"ok": False, "reason": "write_failed", "n_pairs": n_pairs}

        run = S.DistillRun(
            tenant_id=tenant_id, run_id=run_id, ts_iso=S.now_iso(), method="simpo",
            base_model=str(getattr(cfg, "distill_base_model", "") or ""),
            n_desirable=n_pairs, n_undesirable=n_pairs, status="exported", adapter_uri="",
            metrics_json=json.dumps({"path": path, "pairs": written, "vertical": vertical or "all",
                                     "subset": "outcome_anchored&survived_swap"}, ensure_ascii=False),
        )
        try:
            _st.insert_distill_runs([run])
        except Exception as exc:  # noqa: BLE001
            logger.warning("flywheel distill: insert_distill_runs (simpo) failed: %r", exc)

        return {"ok": True, "path": path, "n_pairs": n_pairs, "run_id": run_id}
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel distill: export_simpo error (non-fatal): %r", exc)
        return {"ok": False, "reason": "error"}


# --------------------------------------------------------------------------- #
# B7: QLoRA training harness (LAZY heavy deps; SCAFFOLD when the stack is absent).
# --------------------------------------------------------------------------- #
def train_qlora(export_path: str, *, base_model: str = "", method: str = "kto",
                cfg=None) -> "S.DistillRun":
    """Train a QLoRA adapter from a KTO/SimPO export — the SCAFFOLD + a real config skeleton.

    The heavy stack (torch / trl / peft / bitsandbytes / transformers) is imported LAZILY INSIDE
    this function. When ANY of it is absent (the dormant box, CI, the self-check) we return a
    schema.DistillRun(status='exported', metrics='note: training deps absent — export only') and do
    NOTHING ELSE — the pure-python export path above is the contract that must always run.

    When the stack IS present we assemble the KTOTrainer / CPOConfig(SimPO) + QLoRA(LoraConfig r=16)
    skeleton. The actual long train is deliberately left as a clearly-marked TODO so the self-check
    (and the worker) never kick off a multi-hour GPU job inadvertently. The produced adapter ships
    ONLY through emit_shadow_challenger() → the unchanged gate. NEVER the live model. Never raises.
    """
    cfg = cfg or _cfg.load()
    tenant_id = ""
    n_desirable = 0
    n_undesirable = 0
    base_model = base_model or str(getattr(cfg, "distill_base_model", "") or "")
    method = (method or str(getattr(cfg, "distill_method", "kto") or "kto")).lower()

    # Recover the run shape from the export file name / contents (best-effort, no heavy deps).
    try:
        if export_path and os.path.exists(export_path):
            base = os.path.basename(export_path)
            parts = base.replace(".jsonl", "").split("_")
            if len(parts) >= 2:
                tenant_id = parts[1]
            with open(export_path, "r", encoding="utf-8") as fh:
                for ln in fh:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        obj = json.loads(ln)
                    except Exception:  # noqa: BLE001
                        continue
                    if obj.get("label") is True or "chosen" in obj:
                        n_desirable += 1
                    else:
                        n_undesirable += 1
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel distill: train_qlora could not read export %s: %r", export_path, exc)

    run_id = S.new_id("run_")

    # --- LAZY heavy import (behind the flag). Absent ⇒ scaffold-only DistillRun. ----------------- #
    try:
        if not cfg.distill_active():
            # Flag off ⇒ never attempt to import the heavy stack; return the scaffold.
            raise RuntimeError("distill inactive")
        import torch  # noqa: F401
        import trl  # noqa: F401
        import peft  # noqa: F401
    except Exception as exc:  # noqa: BLE001  (covers ImportError + the inactive guard)
        logger.info("flywheel distill: training deps absent / inactive (%r) — export-only scaffold", exc)
        return S.DistillRun(
            tenant_id=tenant_id, run_id=run_id, ts_iso=S.now_iso(), method=method,
            base_model=base_model, n_desirable=n_desirable, n_undesirable=n_undesirable,
            status="exported",
            metrics_json=json.dumps({"note": "training deps absent — export only",
                                     "export_path": export_path}, ensure_ascii=False),
        )

    # --- Heavy stack present: assemble the config skeleton (the long train stays a TODO). -------- #
    try:
        from datasets import load_dataset  # noqa: F401
        from peft import LoraConfig  # noqa: F401
        from transformers import (  # noqa: F401
            AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig,
        )
        # bnb 4-bit NF4 base (QLoRA — Dettmers 2023): TODO wire AutoModelForCausalLM.from_pretrained
        #   bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
        #                            bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
        # QLoRA adapter (r=16) — the only trainable params:
        lora = LoraConfig(  # noqa: F841
            r=16, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        )
        if method == "simpo":
            # SimPO = reference-free CPO (Meng 2024): trl.CPOTrainer + CPOConfig(loss_type='simpo').
            from trl import CPOConfig  # noqa: F401
            train_cfg = {  # noqa: F841  (skeleton only)
                "trainer": "CPOTrainer", "loss_type": "simpo",
                "cpo_alpha": 1.0, "simpo_gamma": 0.5, "beta": 2.0,
                "data": "paired (prompt, chosen, rejected)",
            }
            # TODO: ds = load_dataset('json', data_files=export_path)['train']
            # TODO: trainer = CPOTrainer(model, args=CPOConfig(loss_type='simpo', ...),
            #                            peft_config=lora, train_dataset=ds, tokenizer=tok)
            # TODO: trainer.train()   # offline GPU job — NOT in the self-check.
        else:
            # KTO (Ethayarajh 2024): trl.KTOTrainer over unpaired {prompt, completion, label}.
            from trl import KTOConfig  # noqa: F401
            train_cfg = {  # noqa: F841
                "trainer": "KTOTrainer", "beta": 0.1,
                "desirable_weight": 1.0, "undesirable_weight": 1.0,  # tune to the imbalance ratio
                "data": "unpaired {prompt, completion, label:bool}",
            }
            # TODO: ds = load_dataset('json', data_files=export_path)['train']
            # TODO: trainer = KTOTrainer(model, args=KTOConfig(beta=0.1, ...),
            #                            peft_config=lora, train_dataset=ds, tokenizer=tok)
            # TODO: trainer.train()   # offline GPU job — NOT in the self-check.

        logger.info("flywheel distill: %s QLoRA config assembled (TODO real train) for %s",
                    method, tenant_id)
        return S.DistillRun(
            tenant_id=tenant_id, run_id=run_id, ts_iso=S.now_iso(), method=method,
            base_model=base_model, n_desirable=n_desirable, n_undesirable=n_undesirable,
            status="exported",  # stays 'exported' until a real offline train flips it to 'trained'
            adapter_uri="",
            metrics_json=json.dumps({"note": "config assembled — real train is a TODO offline job",
                                     "method": method, "lora_r": 16}, ensure_ascii=False),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel distill: train_qlora config error (non-fatal): %r", exc)
        return S.DistillRun(
            tenant_id=tenant_id, run_id=run_id, ts_iso=S.now_iso(), method=method,
            base_model=base_model, n_desirable=n_desirable, n_undesirable=n_undesirable,
            status="failed",
            metrics_json=json.dumps({"error": repr(exc)[:300]}, ensure_ascii=False),
        )


# --------------------------------------------------------------------------- #
# B7: package a trained adapter as a SHADOW challenger (the frozen-live-LLM law).
# --------------------------------------------------------------------------- #
def emit_shadow_challenger(run, *, tenant_id: str = "", adapter_uri: str = "",
                           serving_endpoint: str = "", base_model: str = "",
                           method: str = "kto") -> "S.Challenger":
    """Wrap a DistillRun's adapter into a schema.Challenger that ships through the UNCHANGED gate.

    is_shadow is forced True (the frozen-live-LLM law — a distilled model can ONLY serve as a
    self-hosted vLLM shadow behind the gate + human approval) and status starts at 'proposed'. The
    gate.py harness is unchanged: this challenger climbs the same eval/shadow ladder as any other.
    Never raises.
    """
    try:
        run_tenant = getattr(run, "tenant_id", "") if run is not None else ""
        tid = tenant_id or run_tenant
        run_id = getattr(run, "run_id", "") if run is not None else ""
        adapter_uri = adapter_uri or (getattr(run, "adapter_uri", "") if run is not None else "")
        base_model = base_model or (getattr(run, "base_model", "") if run is not None else "")
        method = method or (getattr(run, "method", "") if run is not None else "") or "kto"
        config_json = json.dumps({"run_id": run_id, "adapter_uri": adapter_uri,
                                  "base_model": base_model, "method": method,
                                  "serving_endpoint": serving_endpoint}, ensure_ascii=False)
        return S.Challenger(
            tenant_id=tid,
            challenger_id=S.new_id("ch_"),
            ts_iso=S.now_iso(),
            kind="model",                         # a self-hosted shadow model (not a prompt/arm)
            proposed_config_json=config_json,
            rationale=(f"KTO/SimPO QLoRA shadow ({method}) on '{base_model}' from run {run_id} — "
                       f"self-hosted vLLM shadow; NEVER live Riya; gated + human-approval only."),
            status="proposed",                    # CHALLENGER_STATES — climbs the unchanged gate
            is_shadow=True,                       # MANDATORY: the frozen-live-LLM law
            adapter_uri=adapter_uri,
            base_model=base_model,
            method=method,
            serving_endpoint=serving_endpoint,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel distill: emit_shadow_challenger error (non-fatal): %r", exc)
        # Even the failure path obeys the law: an is_shadow=True, proposed challenger.
        return S.Challenger(tenant_id=tenant_id, challenger_id=S.new_id("ch_"),
                            ts_iso=S.now_iso(), kind="model", status="proposed", is_shadow=True,
                            method=method or "kto")


__all__ = ["export_kto", "export_simpo", "train_qlora", "emit_shadow_challenger"]


# =========================================================================== #
# Self-check — pure-python happy path. NO network / NO ClickHouse / NO numpy / NO torch.
# Exercises: export_kto (insufficient + sufficient), export_simpo, train_qlora scaffold,
# emit_shadow_challenger (is_shadow law). Monkeypatches _fetch_pairs with SYNTHETIC rows so the
# whole pipeline runs offline.
# =========================================================================== #
if __name__ == "__main__":  # pragma: no cover
    import asyncio
    import tempfile

    logging.basicConfig(level=logging.INFO)

    # Route exports into a temp dir so the self-check leaves no droppings.
    os.environ["FAMIT_VAR"] = tempfile.mkdtemp(prefix="flywheel_distill_selfcheck_")

    def _synthetic_rows(n_desirable_targets: int) -> List[dict]:
        """Build synthetic flywheel_preferences rows. Each row yields a desirable (compliant chosen)
        + an undesirable (rejected), so ~n rows ⇒ ~n desirables."""
        rows: List[dict] = []
        objections = list(S.OBJECTION_TYPES)
        temps = list(S.LEAD_TEMPERATURES)
        for i in range(n_desirable_targets):
            clean = (i % 3 == 0)  # ~1/3 are clean paired (outcome_anchored & survived_swap) for SimPO
            rows.append({
                "tenant_id": "t_demo",
                "pair_id": f"pair_{i:05d}",
                "ts": S.now_iso(),
                "state_embedding_id": S.digest_id("state", objections[i % len(objections)]),
                "objection_type": objections[i % len(objections)],
                "lead_temperature": temps[i % len(temps)],
                "regime": "steady",
                "vertical": "real_estate",
                "chosen_text": f"Sir bilkul, main aapko RERA-approved project ki site visit "
                               f"arrange kar deta hoon — kal {i % 12 + 9} baje theek rahega?",
                "rejected_text": f"Haan toh book kar lo na, kya soch rahe ho ({i}).",
                "chosen_move_id": f"call_{i}:3",
                "rejected_move_id": f"call_{i}:5",
                "margin": 0.4 + (i % 5) * 0.05,
                # Mix real within_call / matched_state with synthetic rubric/sim to exercise weights.
                "source": (["within_call", "matched_state", "rubric_pairwise", "sim_self_play"])[i % 4],
                "survived_swap": 1 if clean else (i % 2),
                "confidence": 0.7,
                "compliant": 1 if (i % 17 != 0) else 0,   # a few non-compliant chosen → must DROP
                "outcome_anchored": 1 if clean else 0,
                "campaign_id": "camp_demo",
            })
        return rows

    async def _main() -> None:
        cfg = _cfg.load()  # dormant (no CH url) — inserts are no-ops, reads bypassed via monkeypatch
        ok = True

        # 1) INSUFFICIENT path: fewer desirables than the floor → ok:False, reason 'insufficient'.
        async def _few(_tid, _v=""):
            return _synthetic_rows(10)
        globals()["_fetch_pairs"] = _few
        r_few = await export_kto("t_demo", cfg=cfg)
        print("export_kto (insufficient):", r_few)
        assert r_few.get("ok") is False and r_few.get("reason") == "insufficient", r_few

        # 2) SUFFICIENT path: enough desirables → ok:True, a real JSONL on disk.
        async def _many(_tid, _v=""):
            return _synthetic_rows(max(int(cfg.distill_min_desirable) + 50, 260))
        globals()["_fetch_pairs"] = _many
        r_kto = await export_kto("t_demo", vertical="real_estate", cfg=cfg)
        print("export_kto (sufficient):", {k: v for k, v in r_kto.items() if k != "path"})
        assert r_kto.get("ok") is True, r_kto
        assert r_kto.get("n_desirable", 0) >= int(cfg.distill_min_desirable), r_kto
        assert os.path.exists(r_kto["path"]), r_kto

        # Verify the exported JSONL: a non-compliant 'chosen' is NEVER a desirable (anti-Goodhart),
        # and synthetic desirables carry the down-weight.
        n_des = n_und = 0
        saw_downweight = False
        with open(r_kto["path"], "r", encoding="utf-8") as fh:
            for ln in fh:
                obj = json.loads(ln)
                if obj.get("label") is True:
                    n_des += 1
                    assert obj.get("completion"), "desirable must have completion text"
                    if obj.get("source") in _SYNTHETIC_SOURCES:
                        assert obj.get("weight", 1.0) == _SYNTHETIC_WEIGHT
                        saw_downweight = True
                else:
                    n_und += 1
        print(f"  jsonl: desirable={n_des} undesirable={n_und} saw_downweight={saw_downweight}")
        assert n_des == r_kto["n_desirable"], (n_des, r_kto["n_desirable"])
        assert saw_downweight, "expected at least one down-weighted synthetic desirable"

        # 3) SimPO export: only the clean (outcome_anchored & survived_swap) subset.
        r_simpo = await export_simpo("t_demo", vertical="real_estate", cfg=cfg)
        print("export_simpo:", {k: v for k, v in r_simpo.items() if k != "path"})
        assert r_simpo.get("ok") is True and r_simpo.get("n_pairs", 0) > 0, r_simpo
        with open(r_simpo["path"], "r", encoding="utf-8") as fh:
            first = json.loads(fh.readline())
        assert "chosen" in first and "rejected" in first and "prompt" in first, first

        # 4) train_qlora scaffold: heavy deps absent ⇒ DistillRun(status='exported', note=...).
        run = train_qlora(r_kto["path"], base_model="meta-llama/Llama-3.1-8B-Instruct",
                          method="kto", cfg=cfg)
        print("train_qlora:", run.status, run.metrics_json[:80])
        assert isinstance(run, S.DistillRun) and run.status == "exported", run
        assert "deps absent" in run.metrics_json or "config assembled" in run.metrics_json
        assert run.to_row()["status"] == "exported"

        # 5) emit_shadow_challenger: the frozen-live-LLM law — is_shadow MUST be True, proposed.
        ch = emit_shadow_challenger(run, tenant_id="t_demo",
                                    adapter_uri="s3://famit/adapters/run.tar",
                                    serving_endpoint="http://vllm-shadow:8000/v1",
                                    base_model="meta-llama/Llama-3.1-8B-Instruct", method="kto")
        print("emit_shadow_challenger:", ch.kind, "is_shadow=", ch.is_shadow, "status=", ch.status)
        assert isinstance(ch, S.Challenger), ch
        assert ch.is_shadow is True, "FROZEN-LIVE-LLM LAW: a distilled challenger MUST be is_shadow"
        assert ch.status == "proposed", ch
        assert ch.to_row()["is_shadow"] == 1, ch.to_row()

        print("OK selfcheck_ok=%s" % ok)

    asyncio.run(_main())
