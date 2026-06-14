"""Offline test for trunk_registry.rotation + livekit_sync (T2, NEW).

Spec acceptance (TELEPHONY-INDEPENDENCE-PLAN §2.5 + §2.3 + §3 red-team B-rel/B3/D/E):
  ROTATION:
   * DID rotation strategies round_robin / least_used / sticky pick correctly + skip `avoid` DIDs;
   * RED-TEAM B-rel: a BURST of ZERO-DURATION RING-OUTS on a DID QUARANTINES the trunk (the
     fireable signal — caller.py never captures the 486); a connected/answered call does NOT;
   * RED-TEAM B3: >= K quarantines on one trunk -> the trunk is DISABLED + a loud alert fires
     (stop pool-burn), not silent rotation;
   * RED-TEAM E: the manual kill switch quarantines on demand.
  LIVEKIT_SYNC:
   * the request BUILDERS produce the right shape from a registry row (SDK-absent dict mirror);
   * the SIP password is never echoed (only auth_password_present);
   * RED-TEAM D: delete REFUSES the env-protected live trunk id + any protected id (no force).

No network, no real PG, no LiveKit SDK. A fake store records the writes; a fake clock + alert sink
make the quarantine/escalation deterministic.

Run: python -m trunk_registry.tests.test_rotation_livekit_offline
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import os
import sys


def run() -> int:
    results = []

    def check(name, fn):
        try:
            fn()
            results.append((name, True, ""))
        except AssertionError as e:
            results.append((name, False, str(e)))
        except Exception as e:  # noqa: BLE001
            results.append((name, False, f"UNEXPECTED {type(e).__name__}: {e}"))

    os.environ["TRUNK_REGISTRY_ENABLED"] = "1"
    os.environ["TRUNK_RINGOUT_BURST_THRESHOLD"] = "3"
    os.environ["TRUNK_RINGOUT_BURST_WINDOW_S"] = "600"
    os.environ["TRUNK_DISABLE_QUARANTINES"] = "2"
    os.environ["TRUNK_QUARANTINE_MINUTES"] = "60"

    from trunk_registry import rotation, livekit_sync
    from trunk_registry.schema import SipTrunk, RotationStrategy, Transport

    # ---- a fake store that records writes + replays counts deterministically ----
    class FakeStore:
        def __init__(self):
            self.health_rows = []
            self.quarantines = []      # (trunk_id, until)
            self.disabled = []         # trunk_id
            self.ringout_count = 0     # what recent_did_ringouts returns
            self.quarantine_count = 0  # what count_trunk_quarantines returns

        def write_health_row(self, tenant_id, trunk_id, *, event="probe", did="",
                             is_healthy=None, sip_code=None, latency_ms=0, error_code="",
                             is_admin=False):
            self.health_rows.append({"trunk_id": trunk_id, "event": event, "did": did,
                                     "is_healthy": is_healthy, "error_code": error_code})

        def recent_did_ringouts(self, tenant_id, trunk_id, did, window_s):
            return self.ringout_count

        def count_trunk_quarantines(self, tenant_id, trunk_id, window_s):
            return self.quarantine_count

        def set_quarantine(self, tenant_id, trunk_id, until, *, is_admin=False):
            self.quarantines.append((trunk_id, until))
            return {"id": trunk_id, "quarantined_until": until}

        def soft_disable_trunk(self, tenant_id, trunk_id, *, is_admin=False):
            self.disabled.append(trunk_id)
            return {"id": trunk_id, "is_enabled": False}

    def _trunk(slug="a-140", *, strategy="round_robin", dids=None, lk="ST_a140"):
        return SipTrunk(id="00000000-0000-0000-0000-0000000000aa", tenant_id="tenant-A", slug=slug,
                        display_name=slug, sip_host="h.example.com", sip_port=5060,
                        did_pool=dids if dids is not None else
                        ["+91801", "+91802", "+91803"], caller_id="+91801",
                        rotation_strategy=strategy, livekit_trunk_id=lk, transport="tcp")

    now = _dt.datetime(2026, 6, 14, 12, 0, 0, tzinfo=_dt.timezone.utc)
    nowf = lambda: now

    # ===================== DID rotation: round_robin cycles =====================
    def t_round_robin():
        rotation.reset_state()
        tr = _trunk(strategy="round_robin", dids=["+91A", "+91B", "+91C"])
        picks = [rotation.pick_did(tr) for _ in range(6)]
        assert picks == ["+91A", "+91B", "+91C", "+91A", "+91B", "+91C"], picks
    check("did_round_robin_cycles", t_round_robin)

    def t_rr_skips_avoid():
        rotation.reset_state()
        tr = _trunk(strategy="round_robin", dids=["+91A", "+91B", "+91C"])
        # avoid +91B (reputation-aware) -> only A and C are ever returned
        picks = {rotation.pick_did(tr, avoid=["+91B"]) for _ in range(10)}
        assert picks == {"+91A", "+91C"}, picks
    check("did_rotation_skips_avoided", t_rr_skips_avoid)

    def t_least_used():
        rotation.reset_state()
        tr = _trunk(strategy="least_used", dids=["+91A", "+91B"])
        # least_used always picks the lowest-count DID, balancing the two
        picks = [rotation.pick_did(tr) for _ in range(4)]
        assert picks.count("+91A") == 2 and picks.count("+91B") == 2, picks
    check("did_least_used_balances", t_least_used)

    def t_sticky():
        rotation.reset_state()
        tr = _trunk(strategy="sticky", dids=["+91A", "+91B"])
        assert all(p == "+91A" for p in [rotation.pick_did(tr) for _ in range(3)])
    check("did_sticky_pins_first", t_sticky)

    def t_empty_or_all_avoided():
        rotation.reset_state()
        tr = _trunk(dids=["+91A"])
        assert rotation.pick_did(tr, avoid=["+91A"]) is None, "all-avoided pool -> None"
        tr2 = _trunk(dids=[])
        # empty did_pool falls back to caller_id
        assert rotation.pick_did(tr2) == "+91801"
    check("did_empty_or_all_avoided", t_empty_or_all_avoided)

    # ===================== B-rel: a connected call does NOT quarantine =====================
    def t_connected_no_quarantine():
        rotation.reset_state()
        fs = FakeStore()
        fs.ringout_count = 99  # even if there were ring-outs, a CONNECTED call must not quarantine
        tr = _trunk()
        res = rotation.note_call_outcome("tenant-A", tr, "+91801", duration_s=42.0, answered=True,
                                         now_fn=nowf, store=fs)
        assert res.logged and not res.quarantined and not res.disabled, res
        assert not fs.quarantines, "a connected call must never quarantine"
        # the logged event is 'connected'
        assert fs.health_rows[-1]["event"] == "connected", fs.health_rows[-1]
    check("b_rel_connected_call_no_quarantine", t_connected_no_quarantine)

    # ===================== B-rel: below threshold ring-out does NOT quarantine =====================
    def t_below_threshold_no_quarantine():
        rotation.reset_state()
        fs = FakeStore()
        fs.ringout_count = 2  # threshold is 3
        tr = _trunk()
        res = rotation.note_call_outcome("tenant-A", tr, "+91801", duration_s=0.0, answered=False,
                                         now_fn=nowf, store=fs)
        assert res.logged and not res.quarantined, res.reason
        assert not fs.quarantines, "below the burst threshold must not quarantine"
        assert fs.health_rows[-1]["event"] == "ring_out", fs.health_rows[-1]
    check("b_rel_below_threshold_no_quarantine", t_below_threshold_no_quarantine)

    # ===================== B-rel: a ring-out BURST quarantines the trunk =====================
    def t_ringout_burst_quarantines():
        rotation.reset_state()
        fs = FakeStore()
        fs.ringout_count = 3   # == threshold -> quarantine
        fs.quarantine_count = 1  # below the disable threshold (2) -> NOT disabled yet
        alerts = []
        tr = _trunk()
        res = rotation.note_call_outcome("tenant-A", tr, "+91801", duration_s=0.0, answered=False,
                                         now_fn=nowf, alert=lambda k, d: alerts.append((k, d)),
                                         store=fs)
        assert res.quarantined and not res.disabled, res.reason
        assert fs.quarantines, "a ring-out burst MUST quarantine the trunk"
        until = fs.quarantines[-1][1]
        assert until == now + _dt.timedelta(minutes=60), until
        assert any(k == "trunk_quarantined" for k, _ in alerts), alerts
    check("b_rel_ringout_burst_quarantines_trunk", t_ringout_burst_quarantines)

    # ===================== B3: K quarantines -> DISABLE the trunk + loud alert =====================
    def t_b3_escalation_disables():
        rotation.reset_state()
        fs = FakeStore()
        fs.ringout_count = 5
        fs.quarantine_count = 2  # >= disable threshold (2) -> DISABLE + alert (stop pool-burn)
        alerts = []
        tr = _trunk()
        res = rotation.note_call_outcome("tenant-A", tr, "+91801", duration_s=0.0, answered=False,
                                         now_fn=nowf, alert=lambda k, d: alerts.append((k, d)),
                                         store=fs)
        assert res.quarantined and res.disabled, res.reason
        assert tr.id in fs.disabled, "B3: the trunk must be DISABLED after K quarantines"
        assert any(k == "trunk_disabled_pool_burn_guard" for k, _ in alerts), alerts
        # the loud alert names the +918071583488 pattern (the founder's exact failure)
        burn = next(d for k, d in alerts if k == "trunk_disabled_pool_burn_guard")
        assert "918071583488" in str(burn), "the alert must name the pool-burn pattern"
    check("b3_escalation_disables_trunk_and_alerts", t_b3_escalation_disables)

    # ===================== E: the manual kill switch =====================
    def t_manual_kill_switch():
        rotation.reset_state()
        fs = FakeStore()
        tr = _trunk()
        ok = rotation.manual_quarantine_did("tenant-A", tr, "+91801", minutes=30,
                                            now_fn=nowf, store=fs)
        assert ok and fs.quarantines, "manual kill switch must quarantine"
        assert fs.quarantines[-1][1] == now + _dt.timedelta(minutes=30)
        assert fs.health_rows[-1]["error_code"] == "manual_kill_switch", fs.health_rows[-1]
    check("e_manual_kill_switch_quarantines", t_manual_kill_switch)

    # ===================== livekit_sync: outbound request shape, no password echo =====================
    def t_lk_outbound_shape():
        tr = _trunk()
        req = livekit_sync.build_outbound_trunk_request(tr, sip_password="s3cr3t-sip-pw")
        # SDK absent on the build box -> dict mirror
        assert isinstance(req, dict) and req["_kind"] == "outbound_trunk", req
        assert req["address"] == "h.example.com", req
        assert req["transport"] == "tcp", req
        assert req["numbers"] == ["+91801", "+91802", "+91803"], req
        # the SIP password is NEVER echoed — only presence
        assert req.get("auth_password_present") is True
        assert "s3cr3t-sip-pw" not in str(req), "the SIP password must never appear in the request mirror"
    check("livekit_outbound_request_shape_no_pw_echo", t_lk_outbound_shape)

    def t_lk_dispatch_metadata():
        tr = _trunk()
        req = livekit_sync.build_dispatch_rule_request(tr, "tenant-A")
        assert isinstance(req, dict) and req["_kind"] == "dispatch_rule", req
        assert '"tenant_id": "tenant-A"' in req["metadata"], req["metadata"]
        assert req["trunk_ids"] == ["ST_a140"], req
    check("livekit_dispatch_rule_carries_tenant_metadata", t_lk_dispatch_metadata)

    # ===================== RED-TEAM D: delete REFUSES the protected live trunk =====================
    def t_d_delete_refuses_protected():
        os.environ["LIVEKIT_SIP_TRUNK_ID"] = "ST_fmtVmNJmpzKa"  # the live earner trunk
        try:
            # is_protected_trunk_id: env-bound id, an explicit protected id, and an EMPTY id are protected
            assert livekit_sync.is_protected_trunk_id("ST_fmtVmNJmpzKa") is True
            assert livekit_sync.is_protected_trunk_id("ST_other", protected_ids=["ST_other"]) is True
            assert livekit_sync.is_protected_trunk_id("") is True
            assert livekit_sync.is_protected_trunk_id("ST_brandnew") is False

            class FakeLK:
                class sip:
                    @staticmethod
                    async def delete_sip_trunk(req):
                        return {"deleted": True}

            # delete of the live env trunk WITHOUT force -> refused (no API call made)
            res = asyncio.run(livekit_sync.delete_trunk(FakeLK(), "ST_fmtVmNJmpzKa"))
            assert not res.ok and res.reason == "refused_protected_live_trunk", res.reason
            # a brand-new (unprotected) trunk deletes fine
            res2 = asyncio.run(livekit_sync.delete_trunk(FakeLK(), "ST_brandnew"))
            assert res2.ok, res2.reason
            # force_protected=True (PIN-gated path) allows even a protected id
            res3 = asyncio.run(livekit_sync.delete_trunk(FakeLK(), "ST_fmtVmNJmpzKa",
                                                         force_protected=True))
            assert res3.ok, res3.reason
        finally:
            os.environ.pop("LIVEKIT_SIP_TRUNK_ID", None)
    check("red_team_d_delete_refuses_protected_live_trunk", t_d_delete_refuses_protected)

    # ===================== livekit_sync create wires the injected client =====================
    def t_lk_create_outbound():
        tr = _trunk(lk="")  # no existing ST yet; create returns the new id

        class FakeResp:
            sip_trunk_id = "ST_newlycreated"

        class FakeLK:
            class sip:
                @staticmethod
                async def create_sip_outbound_trunk(req):
                    return FakeResp()

        res = asyncio.run(livekit_sync.create_outbound_trunk(FakeLK(), tr, "pw"))
        assert res.ok and res.livekit_trunk_id == "ST_newlycreated", res
    check("livekit_create_outbound_returns_new_id", t_lk_create_outbound)

    return _report("TRUNK-ROTATION-LIVEKIT", results)


def _report(suite, results):
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for name, ok, msg in results:
        if not ok:
            print(f"[{suite}] FAIL {name}: {msg}")
    print(f"[{suite}] {passed}/{total} PASS")
    return 0 if passed == total else 1


def test_trunk_rotation_livekit_suite():
    assert run() == 0


if __name__ == "__main__":
    sys.exit(run())
