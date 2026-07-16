"""Tests for voice_ops.flywheel.distill — B7 KTO/SimPO export + gated SHADOW challenger.

Runnable with pytest OR directly:
    python3 -m voice_ops.flywheel.tests.test_distill
Validates the PROPERTIES that keep the distillation path safe (KTO unpaired/binary; the anti-Goodhart
compliance hard-drop; the FROZEN-LIVE-LLM law), not magic numbers:
  * PreferencePair.to_kto_rows() DROPS a non-compliant 'chosen' (anti-Goodhart -- never emit a non-
    compliant line as a desirable example), keeps BOTH sides when compliant, and labels them
    True (chosen/desirable) / False (rejected/undesirable);
  * export_kto is DORMANT-SAFE: with no ClickHouse it returns {'ok': False} and never raises;
  * emit_shadow_challenger ALWAYS sets is_shadow=True and status='proposed' -- the frozen-live-LLM
    law: a distilled model may ONLY ever serve as a self-hosted shadow behind the unchanged gate.
NO network, NO ClickHouse, NO numpy, NO torch -- pure synthetic inputs.
"""
from __future__ import annotations

import asyncio
import os

from voice_ops.flywheel.distill import emit_shadow_challenger, export_kto, export_simpo
from voice_ops.flywheel.schema import Challenger, DistillRun, PreferencePair

# Env vars that could accidentally activate the package -- cleared so export asserts dormancy.
_ACTIVATION_ENV = (
    "FLYWHEEL_ENABLED", "FLYWHEEL_CLICKHOUSE_URL", "CLICKHOUSE_URL", "CLICKHOUSE_WRITE_URL",
    "FLYWHEEL_CLICKHOUSE_READ_URL", "CLICKHOUSE_READ_URL",
)


def _force_dormant():
    for k in _ACTIVATION_ENV:
        os.environ.pop(k, None)


def test_to_kto_rows_keeps_both_sides_and_labels_them():
    """A compliant pair yields TWO unpaired KTO rows: the chosen as a desirable (label True) and
    the rejected as an undesirable (label False). KTO keeps BOTH sides (DPO would force-pair and
    throw the imbalanced tail away). Both carry the same rendered state prompt."""
    pair = PreferencePair(
        tenant_id="t", chosen_text="Sir, RERA-approved project ki site visit kal arrange kar doon?",
        rejected_text="Haan book kar lo na.", compliant=True, objection_type="price",
        lead_temperature="hot",
    )
    rows = pair.to_kto_rows()
    assert len(rows) == 2, rows
    labels = {r["label"] for r in rows}
    assert labels == {True, False}, labels
    by_label = {r["label"]: r for r in rows}
    assert by_label[True]["completion"] == pair.chosen_text
    assert by_label[False]["completion"] == pair.rejected_text
    # both rows are conditioned on the same state preamble prompt.
    assert rows[0]["prompt"] == rows[1]["prompt"]
    assert "objection=price" in rows[0]["prompt"]


def test_to_kto_rows_drops_a_non_compliant_chosen():
    """ANTI-GOODHART HARD GATE: a non-compliant 'chosen' is NEVER emitted as a desirable example --
    we will not teach the model a line that failed the Tier-1 compliance gate. Only the rejected
    (undesirable) survives. A pair with no rejected text yields only the desirable."""
    bad = PreferencePair(tenant_id="t", chosen_text="(non-compliant pushy line)",
                         rejected_text="meh", compliant=False)
    rows = bad.to_kto_rows()
    assert len(rows) == 1, rows
    assert rows[0]["label"] is False, rows                    # only the undesirable survives
    assert rows[0]["completion"] == "meh"

    # a compliant chosen with no rejected -> only the desirable row.
    only_chosen = PreferencePair(tenant_id="t", chosen_text="compliant line", rejected_text="",
                                 compliant=True)
    rc = only_chosen.to_kto_rows()
    assert len(rc) == 1 and rc[0]["label"] is True and rc[0]["completion"] == "compliant line"

    # a fully empty pair -> no rows at all (nothing to learn), never raises.
    assert PreferencePair(tenant_id="t").to_kto_rows() == []


def test_export_kto_and_simpo_are_dormant_safe():
    """With no ClickHouse configured the exporters must return {'ok': False} (no pairs to read) and
    NEVER raise into the worker. An empty tenant id is also a clean no-go."""
    _force_dormant()
    r_kto = asyncio.new_event_loop().run_until_complete(export_kto("t_demo"))
    assert isinstance(r_kto, dict) and r_kto.get("ok") is False, r_kto
    r_simpo = asyncio.new_event_loop().run_until_complete(export_simpo("t_demo"))
    assert isinstance(r_simpo, dict) and r_simpo.get("ok") is False, r_simpo
    # empty tenant -> {'ok': False, 'reason': 'no_tenant'}, never raises.
    r_empty = asyncio.new_event_loop().run_until_complete(export_kto(""))
    assert r_empty.get("ok") is False and r_empty.get("reason") == "no_tenant"


def test_emit_shadow_challenger_always_sets_is_shadow_true():
    """THE FROZEN-LIVE-LLM LAW: a distilled artefact can ONLY ever serve as a self-hosted shadow
    behind the unchanged gate. emit_shadow_challenger MUST force is_shadow=True and status='proposed'
    -- on the happy path AND on the failure path (a None run still obeys the law)."""
    run = DistillRun(tenant_id="t_demo", run_id="run_abc", method="kto",
                     base_model="meta-llama/Llama-3.1-8B-Instruct")
    ch = emit_shadow_challenger(run, tenant_id="t_demo",
                                adapter_uri="s3://famit/adapters/run.tar",
                                serving_endpoint="http://vllm-shadow:8000/v1",
                                base_model="meta-llama/Llama-3.1-8B-Instruct", method="kto")
    assert isinstance(ch, Challenger)
    assert ch.is_shadow is True, "FROZEN-LIVE-LLM LAW: a distilled challenger MUST be is_shadow"
    assert ch.status == "proposed", ch.status
    assert ch.kind == "model"
    # the wire row encodes is_shadow as UInt8 1 (never a python bool).
    assert ch.to_row()["is_shadow"] == 1

    # the failure path (a None run) STILL obeys the law -- is_shadow True, proposed.
    ch_none = emit_shadow_challenger(None, tenant_id="t_demo", method="simpo")
    assert ch_none.is_shadow is True and ch_none.status == "proposed"


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed — test_distill OK")


if __name__ == "__main__":
    _run_all()
