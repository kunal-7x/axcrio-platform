"""ConcurrencyConfig — default-OFF master flag + env knobs + derived caps."""
from __future__ import annotations

import os
from unittest import mock

from voice_ops.concurrency.config import ConcurrencyConfig


def test_default_is_off_and_safe():
    c = ConcurrencyConfig()
    assert c.enabled is False          # master flag OFF by default (earner-safe)
    assert c.worker_slot_cap == 20
    assert c.worker_count == 1
    assert c.tenant_call_cap == 3


def test_effective_global_cap_derives_from_fleet():
    c = ConcurrencyConfig(worker_slot_cap=25, worker_count=4, global_call_cap=0)
    assert c.effective_global_cap() == 100   # 25 * 4
    c2 = ConcurrencyConfig(worker_slot_cap=25, worker_count=4, global_call_cap=70)
    assert c2.effective_global_cap() == 70   # explicit override wins


def test_from_env_reads_flags():
    env = {
        "CONCURRENCY_ENABLED": "1",
        "CONCURRENCY_WORKER_SLOT_CAP": "30",
        "CONCURRENCY_WORKER_COUNT": "5",
        "CONCURRENCY_LLM_RPM": "60",
        "CONCURRENCY_TTS_SLOTS_PER_KEY": "8",
    }
    with mock.patch.dict(os.environ, env, clear=False):
        c = ConcurrencyConfig.from_env()
    assert c.enabled is True
    assert c.worker_slot_cap == 30
    assert c.worker_count == 5
    assert c.effective_global_cap() == 150
    assert c.llm_rpm == 60
    assert c.tts_slots_per_key == 8


def test_from_env_bad_values_fall_back():
    with mock.patch.dict(os.environ, {"CONCURRENCY_WORKER_SLOT_CAP": "notanint"}, clear=False):
        c = ConcurrencyConfig.from_env()
    assert c.worker_slot_cap == 20  # safe default, never raises
