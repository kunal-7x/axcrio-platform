"""voice_ops.concurrency.admission — AdmissionController: the pre-dial gate (W24).

The single thing the live dial loop is missing: an ALL-OR-NOTHING reservation of
every scarce resource a call needs, taken BEFORE the SIP/LiveKit dial — so a call is
only placed when it can actually run end-to-end, and saturation PACES/QUEUES the lead
instead of failing it mid-stream.

`reserve(tenant_id, call_id, provider)` checks, in this order, releasing everything
already taken on the FIRST refusal (so a partial reservation never leaks a slot or a
token):

  1. GLOBAL call slot      — cross-tenant fleet ceiling (the guard the loop lacks).
  2. per-TENANT call slot  — the tenant's concurrency ceiling (mirrors ACTIVE_CALLS).
  3. WORKER slot           — a free active-call slot on the worker fleet (physical wall).
  4. LLM token (tenant)    — the tenant's LLM rate/burst budget (plan cap).
  5. LLM token (per key)   — the chosen provider key's RPM budget (denial-of-wallet).
  6. TTS slot (per key)    — a free concurrent synthesis channel on the chosen TTS key.

If every gate passes -> ADMITTED with a `Reservation` the caller stashes and passes
to `release(...)` on call end. If ANY gate refuses -> QUEUE (capacity-bound, retry
next tick) or PACE (rate-bound, back off), and EVERYTHING acquired so far is rolled
back. The decision (+ which gate refused) is emitted on the W8 EventBus so the
dashboard/autoscaler react in real time — emit is fire-and-forget and can NEVER block
or fail the admission path (W8 contract).

Provider KEY selection reuses W13 HealthScoredKeyPool.pick() (route to the healthiest
key); a None pick is the LOUD pool-exhausted signal and refuses admission (PACE) — we
never dial a call we cannot synthesize. The number-side admission (W12 NumberPool /
CapacityPlanner) is COMPLEMENTARY and already atomic; this controller owns the
provider+worker dimension the number pool does not model.

ASYNC surface (so emit() can await the bus) but the reservation math is the
synchronous, atomic SlotPool/TokenBucket core. Lazy heavy imports only. Zero
droplet_work / livekit / redis at module load.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from .budget import TokenBucket
from .config import ConcurrencyConfig
from .slots import SlotPool

log = logging.getLogger("voice_ops.concurrency.admission")

# decision outcomes
ADMITTED = "admitted"
QUEUE = "queue"      # capacity-bound: retry on the next dial tick (a slot will free)
PACE = "pace"        # rate-bound: back off (a token/key will refill/recover)


@dataclass(frozen=True)
class AdmissionDecision:
    """The verdict for one reserve() attempt."""

    outcome: str                 # ADMITTED | QUEUE | PACE
    reason: str = ""             # which gate refused (or "all gates clear")
    gate: str = ""               # the refusing resource name ("" when admitted)
    reservation: Optional["Reservation"] = None

    @property
    def admitted(self) -> bool:
        return self.outcome == ADMITTED


@dataclass
class Reservation:
    """The handle the caller stashes for the life of the call and hands back to
    `release()`. Records every resource taken so release frees EXACTLY those."""

    tenant_id: str
    call_id: str
    provider_tts: str = ""
    tts_key_fp: str = ""
    llm_key_fp: str = ""
    # which pools/buckets were taken (for an exact, idempotent rollback/release)
    _slots_taken: list = field(default_factory=list, repr=False)   # (SlotPool, lease_id)
    _tokens_taken: list = field(default_factory=list, repr=False)  # (TokenBucket, n)
    released: bool = False


class AdmissionController:
    """Owns the global/tenant/worker slot pools + the per-tenant/per-key budgets.
    Construct once per process. Tenant + key pools are created lazily on first use
    so an idle tenant costs nothing.

    Reuse seams (all injected, all optional so unit tests stay pure):
      - `tts_keypools[provider]` -> W13 HealthScoredKeyPool (route to healthiest TTS key)
      - `llm_keypools[provider]` -> W13 HealthScoredKeyPool (route to healthiest LLM key)
      - `event_bus`              -> W8 EventBus (fire-and-forget admission telemetry)
    """

    def __init__(
        self,
        cfg: Optional[ConcurrencyConfig] = None,
        *,
        tts_keypools: Optional[Dict[str, object]] = None,
        llm_keypools: Optional[Dict[str, object]] = None,
        event_bus: Optional[object] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.cfg = cfg or ConcurrencyConfig.from_env()
        self.tts_keypools = dict(tts_keypools or {})
        self.llm_keypools = dict(llm_keypools or {})
        self.event_bus = event_bus
        self._clock = clock

        c = self.cfg
        self._global = SlotPool("global", c.effective_global_cap(), ttl_s=c.reserve_ttl_s, clock=clock)
        self._worker = SlotPool(
            "worker", max(1, c.worker_slot_cap) * max(1, c.worker_count),
            ttl_s=c.reserve_ttl_s, clock=clock,
        )
        # lazily-created per-tenant / per-key pools + buckets
        self._tenant_slots: Dict[str, SlotPool] = {}
        self._tenant_llm: Dict[str, TokenBucket] = {}
        self._key_llm: Dict[str, TokenBucket] = {}     # f"{provider}:{fp}" -> bucket
        self._tts_slots: Dict[str, SlotPool] = {}      # f"{provider}:{fp}" -> slot pool

    # ----------------------------------------------------- lazy resource get #
    def _tenant_slot_pool(self, tenant_id: str) -> SlotPool:
        p = self._tenant_slots.get(tenant_id)
        if p is None:
            p = SlotPool(f"tenant:{tenant_id}", self.cfg.tenant_call_cap,
                         ttl_s=self.cfg.reserve_ttl_s, clock=self._clock)
            self._tenant_slots[tenant_id] = p
        return p

    def _tenant_llm_bucket(self, tenant_id: str) -> TokenBucket:
        b = self._tenant_llm.get(tenant_id)
        if b is None:
            b = TokenBucket.per_minute(self.cfg.llm_rpm, self.cfg.llm_burst, now=self._clock)
            self._tenant_llm[tenant_id] = b
        return b

    def _key_llm_bucket(self, provider: str, fp: str) -> TokenBucket:
        k = f"{provider}:{fp}"
        b = self._key_llm.get(k)
        if b is None:
            b = TokenBucket.per_minute(self.cfg.llm_rpm, self.cfg.llm_burst, now=self._clock)
            self._key_llm[k] = b
        return b

    def _tts_slot_pool(self, provider: str, fp: str) -> SlotPool:
        k = f"{provider}:{fp}"
        p = self._tts_slots.get(k)
        if p is None:
            p = SlotPool(f"tts:{k}", self.cfg.tts_slots_per_key,
                         ttl_s=self.cfg.reserve_ttl_s, clock=self._clock)
            self._tts_slots[k] = p
        return p

    @staticmethod
    def _pick_key(pool: Optional[object]) -> Optional[str]:
        """Route to the healthiest key (W13 .pick()); None = pool exhausted (LOUD)."""
        if pool is None:
            return None
        try:
            return pool.pick()  # HealthScoredKeyPool.pick() or KeyPool.pick()
        except Exception as exc:  # a pool bug must never crash admission
            log.warning("keypool.pick() raised (treating as exhausted): %r", exc)
            return None

    # ------------------------------------------------------------- reserve #
    async def reserve(
        self, tenant_id: str, call_id: str, *, provider_tts: str = "elevenlabs",
        provider_llm: str = "groq",
    ) -> AdmissionDecision:
        """Pre-dial admission. ALL-OR-NOTHING: a refusal at any gate rolls back every
        resource already taken (no slot/token leak), then returns QUEUE (capacity) or
        PACE (rate/key). Never raises; never blocks beyond the bus emit deadline."""
        tenant_id = (tenant_id or "").strip()
        call_id = (call_id or "").strip()
        if not tenant_id or not call_id:
            # fail-closed: an unidentified call is never admitted (mirrors KernelSession)
            return AdmissionDecision(PACE, reason="missing tenant_id/call_id (fail-closed)", gate="identity")

        res = Reservation(tenant_id=tenant_id, call_id=call_id, provider_tts=provider_tts)
        lease = call_id  # the call_id IS the lease id everywhere (idempotent retries)

        # 1) GLOBAL fleet ceiling
        if not self._global.acquire(lease):
            return await self._refuse(res, QUEUE, "global fleet at capacity", "global")
        res._slots_taken.append((self._global, lease))

        # 2) per-TENANT concurrency
        tslots = self._tenant_slot_pool(tenant_id)
        if not tslots.acquire(lease):
            return await self._refuse(res, QUEUE, "tenant at concurrency cap", "tenant")
        res._slots_taken.append((tslots, lease))

        # 3) WORKER slot (the physical single-worker wall)
        if not self._worker.acquire(lease):
            return await self._refuse(res, QUEUE, "worker fleet saturated", "worker")
        res._slots_taken.append((self._worker, lease))

        # 4) per-TENANT LLM budget (plan cap)
        tbucket = self._tenant_llm_bucket(tenant_id)
        if not tbucket.take(1):
            return await self._refuse(res, PACE, "tenant LLM budget exhausted", "llm_tenant")
        res._tokens_taken.append((tbucket, 1))

        # 5) per-KEY LLM budget (route to healthiest LLM key, then its RPM bucket)
        llm_fp = self._pick_key(self.llm_keypools.get(provider_llm))
        if self.llm_keypools.get(provider_llm) is not None and llm_fp is None:
            return await self._refuse(res, PACE, f"{provider_llm} LLM key pool exhausted", "llm_key")
        if llm_fp:
            res.llm_key_fp = llm_fp
            kbucket = self._key_llm_bucket(provider_llm, llm_fp)
            if not kbucket.take(1):
                return await self._refuse(res, PACE, f"{provider_llm} key {llm_fp} RPM exhausted", "llm_key_rpm")
            res._tokens_taken.append((kbucket, 1))

        # 6) per-KEY TTS slot (route to healthiest TTS key, then its channel pool)
        tts_fp = self._pick_key(self.tts_keypools.get(provider_tts))
        if self.tts_keypools.get(provider_tts) is not None and tts_fp is None:
            return await self._refuse(res, PACE, f"{provider_tts} TTS key pool exhausted", "tts_key")
        if tts_fp:
            res.tts_key_fp = tts_fp
            ttspool = self._tts_slot_pool(provider_tts, tts_fp)
            if not ttspool.acquire(lease):
                return await self._refuse(res, QUEUE, f"{provider_tts} key {tts_fp} TTS channels full", "tts_slot")
            res._slots_taken.append((ttspool, lease))

        await self._emit("call_admitted", tenant_id, call_id, {
            "tts": provider_tts, "tts_key": res.tts_key_fp or None,
            "llm": provider_llm, "llm_key": res.llm_key_fp or None,
        })
        return AdmissionDecision(ADMITTED, reason="all gates clear", reservation=res)

    async def _refuse(self, res: Reservation, outcome: str, reason: str, gate: str) -> AdmissionDecision:
        """Roll back everything taken so far (exact, idempotent) and emit the refusal."""
        self._rollback(res)
        await self._emit("call_paced", res.tenant_id, res.call_id,
                         {"outcome": outcome, "gate": gate, "reason": reason})
        log.info("admission %s [%s/%s]: %s (gate=%s)", outcome, res.tenant_id, res.call_id, reason, gate)
        return AdmissionDecision(outcome, reason=reason, gate=gate)

    @staticmethod
    def _rollback(res: Reservation) -> None:
        for pool, lease in res._slots_taken:
            pool.release(lease)
        for bucket, n in res._tokens_taken:
            bucket.give_back(n)
        res._slots_taken.clear()
        res._tokens_taken.clear()

    # -------------------------------------------------------------- renew #
    def renew(self, reservation: Optional[Reservation]) -> bool:
        """Heartbeat a LIVE reservation: extend the TTL of EVERY slot it holds so a
        call longer than `reserve_ttl_s` is never swept out from under itself.

        Red-team fold (W24): without a controller-level heartbeat, a call > 300s had
        its leases swept while still live, the freed slot re-admitted another call
        (oversubscription), and the original teardown then `release()`d the new
        occupant's lease. The seam must call this on a timer (< reserve_ttl_s) for the
        life of every admitted call. Synchronous + idempotent; never raises.

        Returns True iff the reservation is still live and at least one slot was
        renewed; False for a released/None reservation (the seam stops heartbeating)."""
        if reservation is None or reservation.released or not reservation._slots_taken:
            return False
        renewed = False
        for pool, lease in reservation._slots_taken:
            if pool.renew(lease):
                renewed = True
        return renewed

    # ------------------------------------------------------------- release #
    async def release(self, reservation: Optional[Reservation]) -> None:
        """Free every resource the reservation holds. Idempotent: a second release is
        a no-op (slot release + token give-back are both idempotent), so a
        double-fire on call teardown can never under-count. Called on call end."""
        if reservation is None or reservation.released:
            return
        # NOTE: tokens are NOT given back on a NORMAL release — a consumed LLM/TTS
        # request is spent; only SLOT capacity frees on call end. (Tokens refill by
        # time; giving them back here would defeat the rate budget.)
        for pool, lease in reservation._slots_taken:
            pool.release(lease)
        reservation._slots_taken.clear()
        reservation.released = True
        await self._emit("call_released", reservation.tenant_id, reservation.call_id, {})

    # --------------------------------------------------------------- emit #
    async def _emit(self, name: str, tenant_id: str, call_id: str, payload: dict) -> None:
        """Fire-and-forget W8 telemetry. NEVER blocks/raises into admission (the bus
        owns its own timeout; we add a catch-all). A dead bus = no telemetry, the
        admission decision is unaffected — the earner-safe rule."""
        bus = self.event_bus
        if bus is None:
            return
        try:
            from voice_kernel.contracts import Event  # lazy: keep import light
            from voice_kernel.events.timeutil import now_utc_iso
            ev = Event(name=name, call_id=call_id, tenant_id=tenant_id,
                       ts_iso=now_utc_iso(), payload=payload)
            await bus.emit(ev)
        except Exception as exc:
            log.debug("admission emit non-fatal: %r", exc)

    # ------------------------------------------------------------ snapshot #
    def snapshot(self) -> dict:
        """Live capacity view for the autoscale signal + the panel."""
        return {
            "global": self._global.snapshot(),
            "worker": self._worker.snapshot(),
            "tenants": {t: p.snapshot() for t, p in self._tenant_slots.items()},
            "tts_keys": {k: p.snapshot() for k, p in self._tts_slots.items()},
        }
