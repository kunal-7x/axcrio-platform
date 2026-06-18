"""voice_ops.security.keys.runbook — per-PURPOSE key-rotation runbook (W23, TRACKED, secret-free).

WHY PER-PURPOSE ROTATION IS NOW CHEAP: once the keys are split (keyring.py derives each purpose from
the master via HKDF with the purpose label + version in `info`), rotating ONE family no longer logs
everyone out of the others. Bumping `JWT_ACCESS` version v1->v2 re-derives ONLY the access key; the
step-up / service / reveal keys are byte-identical across the bump. This is the containment dividend
of the split.

This module produces the operator-runnable, ORDERED rotation plan as plain data — it NEVER prints,
logs, returns-in-the-clear, or persists any secret/key bytes. Every step references a key by its
PURPOSE + version + fingerprint, never its material. The plan is safe to emit as an audit event.

ROTATION FLAVOURS:
  * rotate_purpose(p)   — bump ONE purpose's version (the common case; contained blast radius).
  * rotate_master()     — rotate the underlying master secret (the big hammer): re-derives ALL
    purposes at once = a full platform logout. Used on a suspected master compromise.

For the actual fresh-master generation we REUSE the W20 rotation primitive
(`voice_ops.security.rotation.rotate_hmac_signing_secret`) so there is ONE CSPRNG secret-gen path,
not two — its RotationResult already guarantees the plaintext stays behind `.reveal()` and never
hits a repr/log.

IMPORT ISOLATION: stdlib + keyring/purpose (stdlib-only) + a LAZY import of voice_ops.security.rotation
only inside rotate_master. ZERO droplet/caller/auth import.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .keyring import Keyring
from .purpose import COLLIDING_TODAY, KeyPurpose, all_purposes


@dataclass(frozen=True)
class RotationStep:
    """One ordered operator action. SAFE to log: purpose + version + fingerprints only, no bytes."""

    order: int
    purpose: str
    action: str
    old_version: int
    new_version: int
    old_fingerprint: str
    new_fingerprint: str
    note: str = ""


@dataclass(frozen=True)
class RotationPlan:
    """The full ordered plan + a human runbook. SAFE to log/emit — contains only fingerprints."""

    kind: str                                  # "purpose" | "master"
    steps: tuple[RotationStep, ...] = field(default_factory=tuple)
    invalidates_all: bool = False
    summary: str = ""

    def as_text(self) -> str:
        lines = [f"# Key rotation plan ({self.kind}) — {self.summary}"]
        if self.invalidates_all:
            lines.append("# WARNING: this rotation invalidates ALL tokens of the affected purpose(s) — a logout.")
        for s in self.steps:
            lines.append(
                f"{s.order}. [{s.purpose}] {s.action}: v{s.old_version}(fp {s.old_fingerprint}) "
                f"-> v{s.new_version}(fp {s.new_fingerprint}) — {s.note}"
            )
        return "\n".join(lines)


def rotate_purpose(
    keyring: Keyring,
    purpose: KeyPurpose,
    *,
    old_version: int = 1,
    new_version: Optional[int] = None,
) -> RotationPlan:
    """Plan to rotate a SINGLE purpose's key by bumping its version. Re-derives only that purpose;
    every other purpose is untouched (the containment win). Produces fingerprints for the before/after
    smoke — NEVER the bytes."""
    nv = int(new_version if new_version is not None else old_version + 1)
    old_fp = keyring.fingerprint(purpose, version=old_version)
    new_fp = keyring.fingerprint(purpose, version=nv)
    steps = (
        RotationStep(
            order=1, purpose=purpose.label, action="bump-version",
            old_version=old_version, new_version=nv,
            old_fingerprint=old_fp, new_fingerprint=new_fp,
            note=("set the active version for this purpose to the new value in the keyring config; "
                  "ONLY this purpose's tokens become invalid — all other purposes keep working."),
        ),
        RotationStep(
            order=2, purpose=purpose.label, action="verify-isolation",
            old_version=old_version, new_version=nv,
            old_fingerprint=old_fp, new_fingerprint=new_fp,
            note=("prove a token signed at v%d FAILS verify at v%d, and other purposes' fingerprints "
                  "are UNCHANGED across the bump (no collateral logout)." % (old_version, nv)),
        ),
    )
    return RotationPlan(
        kind="purpose",
        steps=steps,
        invalidates_all=False,
        summary=f"rotate {purpose.label} v{old_version} -> v{nv} (contained; privileged={purpose.is_privileged})",
    )


def rotate_master(old_master_fingerprint: str = "") -> RotationPlan:
    """Plan to rotate the underlying MASTER secret — the big hammer. Re-derives every purpose key at
    once = a full platform logout. Uses the W20 CSPRNG rotation primitive for the fresh master so
    there is ONE secret-gen path. The plan carries only fingerprints; the fresh master bytes live
    behind the RotationResult `.reveal()` the operator pipes into the secret store via the runbook."""
    from voice_ops.security.rotation import rotate_hmac_signing_secret  # LAZY, stdlib-only

    res = rotate_hmac_signing_secret(old_value=None)  # fresh master; reveal() only at the secret store
    steps = (
        RotationStep(
            order=1, purpose="ALL", action="replace-master",
            old_version=0, new_version=0,
            old_fingerprint=old_master_fingerprint, new_fingerprint=res.new_fingerprint,
            note=("write the new master to the keystore (KEYRING_MASTER_SECRET) via the secret store "
                  "ONLY — never echo it. Every purpose key re-derives -> all tokens invalid (logout)."),
        ),
        RotationStep(
            order=2, purpose="ALL", action="restart-signers",
            old_version=0, new_version=0,
            old_fingerprint=old_master_fingerprint, new_fingerprint=res.new_fingerprint,
            note="reload auth.py/firewall.py init so they pick up the new master (caller.py:1062/1085).",
        ),
    )
    return RotationPlan(
        kind="master",
        steps=steps,
        invalidates_all=True,
        summary="rotate MASTER (re-derives ALL purposes — full logout; use on suspected master compromise)",
    )


def split_migration_plan(keyring: Keyring) -> RotationPlan:
    """The ONE-TIME migration plan: move each family OFF the shared raw master ONTO its own derived
    key, one purpose at a time. Order: non-privileged first (lowest blast radius), privileged last.
    This is the plan the patch DOC (design/W-SEC-keys-SEAM.md) flips against."""
    shared_fp = keyring.legacy_compat_key_fingerprint()
    ordered = sorted(all_purposes(), key=lambda p: (p.is_privileged, p.label))
    steps = []
    for i, p in enumerate(ordered, start=1):
        derived_fp = keyring.fingerprint(p)
        colliding = p in COLLIDING_TODAY
        steps.append(RotationStep(
            order=i, purpose=p.label, action="split-from-shared-master",
            old_version=0, new_version=keyring.handle(p).version,
            old_fingerprint=shared_fp if colliding else "",
            new_fingerprint=derived_fp,
            note=(("was sharing the master fp %s; " % shared_fp if colliding else "")
                  + "flip its signer (%s) to keyring.sign(%s); "
                    "verify EXISTING tokens still validate during the transition window."
                    % (_seam_for(p), p.label)),
        ))
    return RotationPlan(
        kind="purpose",
        steps=tuple(steps),
        invalidates_all=False,
        summary=("split %d purposes off the shared master; %d collide today and gain containment"
                 % (len(ordered), len(COLLIDING_TODAY))),
    )


def _seam_for(p: KeyPurpose) -> str:
    from .purpose import LIVE_SEAM
    return LIVE_SEAM.get(p, "")
