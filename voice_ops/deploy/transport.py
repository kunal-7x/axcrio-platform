"""voice_ops.deploy.transport — the ONE seam through which every box interaction
flows. Production wires a real SSH transport (paramiko / subprocess ssh) here;
tests inject `FakeTransport`. Because EVERY module in this package takes an
`ExecTransport` and never shells out itself, the entire suite runs with ZERO
real SSH, ZERO real filesystem mutation on the box, and ZERO real PSTN dials.

Design:
  - `ExecTransport` is a tiny Protocol: run(), read(), write(), exists(), md5().
  - The real impl is intentionally NOT imported at module load (no paramiko at
    import time — it's lazy inside `SubprocessSSHTransport`). CI never needs it.
  - `FakeTransport` is an in-memory fake: a dict-backed filesystem plus a queue
    of scripted command results keyed by a substring match on the command. It
    records an ordered command log so tests can assert ordering (e.g. backup
    BEFORE swap, drain BEFORE restart).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Callable, Protocol, runtime_checkable


@dataclass
class ExecResult:
    """Result of a single remote command."""

    rc: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.rc == 0


@runtime_checkable
class ExecTransport(Protocol):
    """The injected box interface. Real impl = SSH; tests = FakeTransport."""

    def run(self, cmd: str, *, check: bool = False, timeout: float | None = None) -> ExecResult:
        """Execute a shell command on the box, return its ExecResult.
        If check=True, a non-zero rc must raise TransportError."""
        ...

    def read(self, path: str) -> bytes:
        """Read a remote file's raw bytes (raises if absent)."""
        ...

    def write(self, path: str, data: bytes) -> None:
        """Write raw bytes to a remote path (creating parent dirs)."""
        ...

    def exists(self, path: str) -> bool:
        """True if the remote path exists."""
        ...

    def md5(self, path: str) -> str:
        """md5 hexdigest of a remote file (CRLF-normalized — see _md5_norm)."""
        ...


class TransportError(RuntimeError):
    """A checked remote command returned non-zero, or a required path is absent."""


def md5_norm(data: bytes) -> str:
    """CRLF-normalized md5: matches the box `_verifydeploy.py` idiom so a file
    edited on Windows (CRLF) hashes identically to the LF copy on the box. This
    is what makes 'intended-new-closure md5' stable across local<->box."""
    return hashlib.md5(data.replace(b"\r\n", b"\n")).hexdigest()


# --------------------------------------------------------------------------- #
# Fake transport — the test substrate. In-memory fs + scripted command results.
# --------------------------------------------------------------------------- #
@dataclass
class _ScriptedResult:
    pattern: str
    result: ExecResult
    consume: bool = True  # one-shot by default; set False to match repeatedly


@dataclass
class FakeTransport:
    """In-memory fake box. Dict filesystem + scripted command matcher.

    Usage in tests:
        t = FakeTransport(files={"/opt/famit-agent/agent.py": b"...golden..."})
        t.script("md5sum /opt/famit-agent/agent.py", stdout="<md5>  agent.py")
        t.on("systemctl restart famit-agent", rc=0)
    Any command with no scripted match returns rc=0 empty (a benign default) so
    tests only script what they assert on. Use `default_rc` to flip that.
    """

    files: dict[str, bytes] = field(default_factory=dict)
    default_rc: int = 0
    log: list[str] = field(default_factory=list)
    _scripts: list[_ScriptedResult] = field(default_factory=list)
    # optional hook a test sets to simulate side effects of a command on the fs
    on_run: Callable[["FakeTransport", str], None] | None = None

    # -- scripting helpers ------------------------------------------------- #
    def script(
        self,
        pattern: str,
        *,
        rc: int = 0,
        stdout: str = "",
        stderr: str = "",
        consume: bool = True,
    ) -> "FakeTransport":
        # one-shot consumable scripts append (FIFO) so a queue of [2,2,1,0]-style
        # sequential results fires in order.
        self._scripts.append(
            _ScriptedResult(pattern, ExecResult(rc, stdout, stderr), consume)
        )
        return self

    # convenience alias for a PERSISTENT (non-consuming) matcher. Latest-wins:
    # prepend so a later on() overrides an earlier registration for the same cmd.
    def on(self, pattern: str, *, rc: int = 0, stdout: str = "", stderr: str = "") -> "FakeTransport":
        self._scripts.insert(
            0, _ScriptedResult(pattern, ExecResult(rc, stdout, stderr), consume=False)
        )
        return self

    # -- ExecTransport impl ------------------------------------------------ #
    def run(self, cmd: str, *, check: bool = False, timeout: float | None = None) -> ExecResult:
        self.log.append(cmd)
        if self.on_run is not None:
            self.on_run(self, cmd)
        res: ExecResult | None = None
        for s in self._scripts:
            # patterns are LITERAL substrings (commands carry regex metachars like
            # '?' in URLs — treating them as regex would mis-match). Substring
            # containment is exactly what tests want.
            if s.pattern in cmd:
                res = s.result
                if s.consume:
                    self._scripts.remove(s)
                break
        if res is None:
            res = ExecResult(self.default_rc, "", "")
        if check and not res.ok:
            raise TransportError(f"cmd failed rc={res.rc}: {cmd}\n{res.stderr}")
        return res

    def read(self, path: str) -> bytes:
        if path not in self.files:
            raise TransportError(f"no such file: {path}")
        return self.files[path]

    def write(self, path: str, data: bytes) -> None:
        self.files[path] = data
        self.log.append(f"<write {path} {len(data)}B>")

    def exists(self, path: str) -> bool:
        return path in self.files

    def md5(self, path: str) -> str:
        return md5_norm(self.read(path))

    # -- test ergonomics --------------------------------------------------- #
    def commands(self) -> list[str]:
        """Only the real shell commands (excludes the synthetic <write ...> log lines)."""
        return [c for c in self.log if not c.startswith("<write ")]

    def index_of(self, substr: str) -> int:
        """First position in the command log whose command contains substr (-1 if none)."""
        for i, c in enumerate(self.log):
            if substr in c:
                return i
        return -1

    def ran_before(self, a: str, b: str) -> bool:
        """True iff a command containing `a` ran strictly before one containing `b`."""
        ia, ib = self.index_of(a), self.index_of(b)
        return ia != -1 and ib != -1 and ia < ib
