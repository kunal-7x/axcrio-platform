"""voice_ops.deploy.closure — the md5 truth of a deploy.

A DEPLOY CLOSURE is the exact set of files a deploy will land on the box, each
pinned to a CRLF-normalized md5. Two ideas live here:

  1. DeployClosure — a manifest {relpath -> md5}. Comparing two closures yields
     a precise drift report (added / removed / changed). This is what the box
     <-> local drift check and the post-deploy "landed == intended" assertion
     both stand on.

  2. compute_intended_md5 — BEFORE uploading anything, take the *frozen golden*
     bytes of a file plus a unified-diff patch, apply the patch locally, run a
     py_compile syntax gate, and record the resulting md5. That number is the
     INTENDED-NEW-CLOSURE: the deploy asserts the file that lands on the box
     hashes to EXACTLY this, so no accidental edit / truncated SCP can survive.

Pure-python, no box, no heavy imports. `apply_unified_diff` is a minimal,
well-tested unified-diff applier (we do not import the `patch` library to keep
the closure droplet-free and dependency-free).
"""
from __future__ import annotations

import py_compile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .transport import md5_norm


# --------------------------------------------------------------------------- #
# DeployClosure — the manifest
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ClosureDiff:
    added: dict[str, str]            # relpath -> new md5
    removed: dict[str, str]          # relpath -> old md5
    changed: dict[str, tuple[str, str]]  # relpath -> (old md5, new md5)

    @property
    def clean(self) -> bool:
        return not (self.added or self.removed or self.changed)

    def summary(self) -> str:
        if self.clean:
            return "closures identical (no drift)"
        parts = []
        for p, m in sorted(self.added.items()):
            parts.append(f"  + {p}  {m}")
        for p, m in sorted(self.removed.items()):
            parts.append(f"  - {p}  {m}")
        for p, (o, n) in sorted(self.changed.items()):
            parts.append(f"  ~ {p}  {o} -> {n}")
        return "DRIFT:\n" + "\n".join(parts)


@dataclass(frozen=True)
class DeployClosure:
    """{relpath -> md5} manifest of the files a deploy lands. Immutable."""

    manifest: dict[str, str] = field(default_factory=dict)

    # -- constructors ------------------------------------------------------ #
    @classmethod
    def from_local_files(cls, root: str | Path, relpaths: list[str]) -> "DeployClosure":
        root = Path(root)
        m: dict[str, str] = {}
        for rel in relpaths:
            m[rel] = md5_norm((root / rel).read_bytes())
        return cls(dict(sorted(m.items())))

    @classmethod
    def from_transport(cls, transport, root: str, relpaths: list[str]) -> "DeployClosure":
        """Build a closure of the files as they currently exist on the box."""
        m: dict[str, str] = {}
        for rel in relpaths:
            full = f"{root.rstrip('/')}/{rel}"
            m[rel] = transport.md5(full)
        return cls(dict(sorted(m.items())))

    @classmethod
    def from_manifest(cls, manifest: dict[str, str]) -> "DeployClosure":
        return cls(dict(sorted(manifest.items())))

    # -- comparison -------------------------------------------------------- #
    def diff(self, other: "DeployClosure") -> ClosureDiff:
        """Drift of `other` relative to `self` (self = expected, other = actual)."""
        added, removed, changed = {}, {}, {}
        for p, m in other.manifest.items():
            if p not in self.manifest:
                added[p] = m
            elif self.manifest[p] != m:
                changed[p] = (self.manifest[p], m)
        for p, m in self.manifest.items():
            if p not in other.manifest:
                removed[p] = m
        return ClosureDiff(added, removed, changed)

    def matches(self, other: "DeployClosure") -> bool:
        return self.manifest == other.manifest

    def fingerprint(self) -> str:
        """A single md5 over the whole sorted manifest — one number for the closure."""
        blob = "\n".join(f"{p}={m}" for p, m in sorted(self.manifest.items()))
        return md5_norm(blob.encode())


# --------------------------------------------------------------------------- #
# Intended-new-closure — golden + patch -> md5
# --------------------------------------------------------------------------- #
class PatchError(ValueError):
    """The unified diff did not apply cleanly against the golden bytes."""


def apply_unified_diff(golden: str, diff_text: str) -> str:
    """Apply a single-file unified diff (the @@ hunks) to `golden`.

    Minimal, strict applier: every context/removed line MUST match the source
    exactly at the hunk offset, or PatchError is raised (a wrong golden, or a
    stale patch, fails closed — which is the whole point of the gate)."""
    src = golden.split("\n")
    # If the golden ended with a newline, splitting leaves a trailing "" we keep.
    out: list[str] = []
    si = 0  # index into src
    lines = diff_text.split("\n")
    li = 0
    saw_hunk = False
    while li < len(lines):
        line = lines[li]
        if line.startswith("--- ") or line.startswith("+++ "):
            li += 1
            continue
        if line.startswith("@@"):
            saw_hunk = True
            # @@ -l,s +l,s @@  -> source start (1-based)
            try:
                old_part = line.split(" ")[1]            # -l,s
                old_start = int(old_part[1:].split(",")[0])
            except (IndexError, ValueError) as e:  # pragma: no cover - malformed header
                raise PatchError(f"bad hunk header: {line!r}") from e
            # copy unchanged src up to the hunk start
            hunk_src0 = old_start - 1
            if hunk_src0 < si:
                raise PatchError("overlapping / out-of-order hunks")
            out.extend(src[si:hunk_src0])
            si = hunk_src0
            li += 1
            # consume hunk body
            while li < len(lines):
                bl = lines[li]
                if bl.startswith("@@") or bl.startswith("--- ") or bl.startswith("+++ "):
                    break
                if bl == "" and li == len(lines) - 1:
                    # trailing empty line of the diff text itself
                    li += 1
                    continue
                tag, content = (bl[:1], bl[1:]) if bl else (" ", "")
                if tag == " ":
                    if si >= len(src) or src[si] != content:
                        raise PatchError(
                            f"context mismatch at src line {si + 1}: "
                            f"expected {content!r} got "
                            f"{src[si] if si < len(src) else '<EOF>'!r}"
                        )
                    out.append(src[si])
                    si += 1
                elif tag == "-":
                    if si >= len(src) or src[si] != content:
                        raise PatchError(
                            f"removed-line mismatch at src line {si + 1}: "
                            f"expected {content!r} got "
                            f"{src[si] if si < len(src) else '<EOF>'!r}"
                        )
                    si += 1
                elif tag == "+":
                    out.append(content)
                elif tag == "\\":
                    # "\ No newline at end of file" — ignore
                    pass
                else:  # pragma: no cover - unknown tag
                    raise PatchError(f"unknown diff line: {bl!r}")
                li += 1
        else:
            li += 1
    if not saw_hunk:
        raise PatchError("diff contained no @@ hunks")
    # copy the remaining unchanged tail
    out.extend(src[si:])
    return "\n".join(out)


@dataclass(frozen=True)
class IntendedClosure:
    """The result of computing the intended-new file locally."""

    new_text: str
    md5: str

    def as_bytes(self) -> bytes:
        return self.new_text.encode()


def compute_intended_md5(
    golden_bytes: bytes,
    diff_text: str,
    *,
    syntax_check: bool = True,
    filename_hint: str = "agent_intended.py",
) -> IntendedClosure:
    """Golden bytes + unified diff -> (new_text, intended-new md5).

    Steps (this is the gate the box later asserts against):
      1. CRLF-normalize golden so the patch matches regardless of line endings.
      2. apply_unified_diff (fails closed on any context/removed mismatch).
      3. (optional) py_compile the result — a syntactically broken patch can
         never become an intended closure.
      4. md5_norm the new text.
    NOTE: this NEVER imports / executes the target module. py_compile only parses
    + byte-compiles to a temp .pyc; it does not run module top-level code... but
    we still write to a temp file with a neutral name so even an importable
    side-effect is impossible.
    """
    golden = golden_bytes.replace(b"\r\n", b"\n").decode()
    new_text = apply_unified_diff(golden, diff_text)
    if syntax_check:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / filename_hint
            p.write_text(new_text, encoding="utf-8")
            try:
                py_compile.compile(str(p), doraise=True)
            except py_compile.PyCompileError as e:
                raise PatchError(f"patched file fails py_compile: {e}") from e
    return IntendedClosure(new_text=new_text, md5=md5_norm(new_text.encode()))
