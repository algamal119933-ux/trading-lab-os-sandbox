"""The one way to touch an evidence lane.

Filesystem safety used to be a call-site convention: `Ledger` and `EvidenceLock`
opened files carefully, and anything that did not go through them did not. The
consequence was reproducible — `write_runtime_state` followed a symlink named
`capture_runtime.json` and wrote outside the lane, and pointing that link at the
cohort registry truncated the registry. Fixing that one call site would have left
the convention in place for the next file added to the lane.

So the lane owns its I/O. A ``LaneHandle`` opens the evidence directory once and
keeps the descriptor; every later operation is directory-relative against that
descriptor, never by pathname. Two invariants follow, and they are different
things:

CONTAINMENT
    No operation can be redirected to a target outside the lane. The held
    descriptor cannot be re-pointed by renaming a directory afterwards, and every
    child open is ``O_NOFOLLOW`` and single-component, so a linked or nested name
    cannot lead anywhere else.

IDENTITY
    The lane a component believes it is writing must be the lane the others see.
    A pathname substitution cannot redirect this handle — but it could leave
    capture writing the original directory while preflight reads a substitute. So
    the handle pins ``(st_dev, st_ino)`` at open time and
    :meth:`LaneHandle.assert_identity_unchanged` compares the pathname's current
    identity to it at cycle boundaries. That is deliberately not done per
    operation: re-resolving the path before every write would reintroduce exactly
    the race the descriptor removes. A substitution therefore produces a
    fail-closed mismatch, never a second authoritative lane.

Callers do not choose a safety policy. There is no general ``open(name, mode)``:
the operations are typed — read a regular file, append a ledger line, hold the
lock, replace the runtime state atomically, create a child directory, inspect an
entry — and each one enforces the policy the lane requires.

Threat boundary, stated plainly rather than implied:

* ``O_NOFOLLOW`` refuses a symlinked final component; the pinned descriptor
  removes parent-component substitution for this handle. Both are enforced here.
* Hard links are not prevented by ``O_NOFOLLOW``. The policy is metadata on the
  *open* object: a mutable evidence entry must have ``st_nlink == 1``, so an
  entry that is already aliased is refused. A link created after the descriptor
  is open cannot be detected through that descriptor, and the write would then
  appear under both names.
* A concurrent process running as the same user can write the lane directly.
  Nothing here prevents that, and P1 does not attempt to: separate users, mount
  namespaces and immutable storage are outside this stage.
"""

from __future__ import annotations

import errno
import os
import stat
from dataclasses import dataclass
from pathlib import Path

# Opening for inspection must never block: a FIFO opened O_RDONLY without a
# writer waits forever, and a gate that hangs is worse than one that refuses.
_COMMON_FLAGS = os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)


class LaneIOError(Exception):
    """A lane operation was refused. Always fatal, never advisory."""


@dataclass(frozen=True)
class LaneIdentity:
    """What the kernel says this directory is, independent of its name."""

    dev: int
    ino: int

    @classmethod
    def of_fd(cls, fd: int) -> "LaneIdentity":
        info = os.fstat(fd)
        return cls(info.st_dev, info.st_ino)

    @classmethod
    def of_path(cls, path: Path) -> "LaneIdentity":
        info = os.stat(path, follow_symlinks=False)
        return cls(info.st_dev, info.st_ino)


def _validate_child_name(name: str) -> str:
    """A child is one plain component of this directory, and nothing else.

    Accepting ``a/b`` or ``..`` would hand pathname traversal back to the caller
    and make the held descriptor decorative.
    """
    if not name or name in (".", ".."):
        raise LaneIOError(f"{name!r} is not a usable entry name")
    if "/" in name or "\0" in name:
        raise LaneIOError(f"{name!r} must be a single path component within the lane")
    return name


class LaneHandle:
    """An open evidence directory, and the only way to read or write inside it."""

    def __init__(self, fd: int, path: Path) -> None:
        self._fd = fd
        self._path = Path(path)
        self._identity = LaneIdentity.of_fd(fd)

    # -- lifecycle -------------------------------------------------------

    @classmethod
    def open(cls, evidence_dir: str | os.PathLike[str], *, create: bool = False) -> "LaneHandle":
        """Open the lane, or refuse.

        ``create`` makes this the one governed owner of lane-directory creation;
        every other component asks the handle rather than calling ``mkdir``.
        """
        path = Path(evidence_dir)
        if create:
            # Parents are created by name — the lane does not exist yet, so there
            # is nothing to anchor to. From the moment it exists, every operation
            # goes through the descriptor below.
            path.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | _COMMON_FLAGS)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise LaneIOError(f"{path} is a symbolic link, not a directory this runtime owns") from exc
            if exc.errno == errno.ENOTDIR:
                raise LaneIOError(f"{path} exists but is not a directory") from exc
            raise LaneIOError(f"{path} cannot be opened as a lane: {exc}") from exc
        return cls(fd, path)

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def __enter__(self) -> "LaneHandle":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # -- identity --------------------------------------------------------

    @property
    def path(self) -> Path:
        """The name this lane was opened by. Never used to reach the lane again."""
        return self._path

    @property
    def identity(self) -> LaneIdentity:
        return self._identity

    def assert_identity_unchanged(self) -> None:
        """The pathname must still name the directory this handle holds.

        Called at cycle boundaries, not per operation. A mismatch means someone
        moved the lane out from under the name, and the honest response is to
        stop: the alternative is capture writing one directory while preflight
        reads another, each believing it is authoritative.
        """
        try:
            current = LaneIdentity.of_path(self._path)
        except OSError as exc:
            raise LaneIOError(
                f"the lane pathname {self._path} no longer resolves ({exc}); the open lane is "
                f"dev={self._identity.dev} ino={self._identity.ino}"
            ) from exc
        if current != self._identity:
            raise LaneIOError(
                f"the lane pathname {self._path} now names dev={current.dev} ino={current.ino}, "
                f"but this runtime holds dev={self._identity.dev} ino={self._identity.ino}: "
                "a substituted lane is refused rather than written to"
            )

    # -- typed operations ------------------------------------------------

    def stat_entry(self, name: str) -> os.stat_result | None:
        """Metadata of an entry, without following it. None when absent."""
        _validate_child_name(name)
        try:
            return os.stat(name, dir_fd=self._fd, follow_symlinks=False)
        except FileNotFoundError:
            return None

    def exists(self, name: str) -> bool:
        return self.stat_entry(name) is not None

    def _open_regular(self, name: str, flags: int, *, mutable: bool) -> int:
        """Open a child and prove it is a plain, unaliased regular file.

        The decision is made on the *opened* descriptor. Deciding from
        ``stat(path)`` and then opening the name again is the check-then-use
        pattern this boundary exists to remove.
        """
        _validate_child_name(name)
        try:
            fd = os.open(name, flags | _COMMON_FLAGS, 0o644, dir_fd=self._fd)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise LaneIOError(
                    f"{name} in {self._path} is a symbolic link; an evidence entry that leads "
                    "outside the lane is refused, for reads and writes alike"
                ) from exc
            if exc.errno in (errno.ENXIO, errno.EWOULDBLOCK, errno.EISDIR, errno.ENOTDIR):
                # A FIFO with no reader, a socket, a directory: the kernel
                # answers before any blocking read could start, and every such
                # answer is the same refusal rather than a stack trace from
                # whichever call site happened to reach it first.
                raise LaneIOError(
                    f"{name} in {self._path} is not a regular file ({exc.strerror})"
                ) from exc
            raise
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise LaneIOError(
                    f"{name} in {self._path} is a {stat.filemode(info.st_mode)} object, not a regular file"
                )
            if mutable and info.st_nlink != 1:
                raise LaneIOError(
                    f"{name} in {self._path} has {info.st_nlink} hard links; a mutable evidence entry "
                    "must have exactly one name, or a write appears under another"
                )
        except Exception:
            os.close(fd)
            raise
        return fd

    def read_text(self, name: str) -> str:
        """Read a regular evidence file. Refuses anything that is not one."""
        fd = self._open_regular(name, os.O_RDONLY, mutable=False)
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            return handle.read()

    def append_text(self, name: str, text: str, *, fsync: bool = True) -> None:
        """Append to a mutable evidence file, creating it if absent."""
        fd = self._open_regular(name, os.O_WRONLY | os.O_APPEND | os.O_CREAT, mutable=True)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            if fsync:
                os.fsync(handle.fileno())

    def open_lock_file(self, name: str):
        """A read/write handle on the lock entry, for flock. Caller closes it."""
        fd = self._open_regular(name, os.O_RDWR | os.O_CREAT, mutable=True)
        return os.fdopen(fd, "r+", encoding="utf-8")

    def replace_atomically(self, name: str, text: str) -> None:
        """Replace an entry with new content, in one step, inside this lane.

        ``os.replace`` acts on the *name*, so a symlinked destination is replaced
        rather than followed — the link's target is never touched. The temporary
        entry is created exclusively in the same directory and removed on any
        failure, so a crash leaves either the old content or the new, and no
        stray file.
        """
        _validate_child_name(name)
        existing = self.stat_entry(name)
        if existing is not None and not stat.S_ISREG(existing.st_mode):
            # Fail closed on a suspicious destination. The replacement below
            # would be safe anyway; refusing is the clearer answer, and it does
            # not gate the safety — it only reports it.
            raise LaneIOError(
                f"{name} in {self._path} is a {stat.filemode(existing.st_mode)} object; refusing to "
                "replace an entry that is not a regular file"
            )
        temporary = f".{name}.{os.getpid()}.tmp"
        _validate_child_name(temporary)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _COMMON_FLAGS, 0o644, dir_fd=self._fd)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, name, src_dir_fd=self._fd, dst_dir_fd=self._fd)
        except Exception:
            try:
                os.unlink(temporary, dir_fd=self._fd)
            except FileNotFoundError:
                pass
            raise

    def child_dir(self, name: str, *, create: bool = False) -> "LaneHandle":
        """A handle on a subdirectory of this lane — the governed way to nest."""
        _validate_child_name(name)
        if create:
            try:
                os.mkdir(name, 0o755, dir_fd=self._fd)
            except FileExistsError:
                pass
        try:
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | _COMMON_FLAGS, dir_fd=self._fd)
        except OSError as exc:
            raise LaneIOError(f"{name} in {self._path} is not a directory this runtime owns: {exc}") from exc
        return LaneHandle(fd, self._path / name)

    def entries(self) -> list[str]:
        return sorted(os.listdir(self._fd))
