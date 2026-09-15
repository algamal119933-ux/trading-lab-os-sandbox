"""The one place that turns a registry role into runtime paths.

Four components used to derive the same facts independently — the launcher, the
capture loop, preflight and the compose guard — and each one drifted in its own
direction. An independent review found the consequence: preflight compared a
*host* evidence directory against a *container* path and rejected the real lane,
while the compose guard checked container targets and never looked at the host
sources behind them, so a closed instance's host directory could be mounted onto
the successor's container target and pass.

So the mapping lives here, once, and every component consumes it. Two namespaces
are kept explicitly apart rather than being hoped to coincide:

    container   /freqtrade/user_data/<instance_dir>/...   what the engine sees
    host        <repo>/freqtrade/user_data/<instance_dir>/...   what is on disk

``resolve_lane`` is also where status is judged. Structural selection (which row
is this role?) is separated from permission to run (may this row execute?),
because stop and recovery legitimately address rows that must never execute.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COHORT_REGISTRY = REPO_ROOT / "research" / "fp" / "records" / "forward_paper_cohort_registry.json"

CONTAINER_USER_DATA = PurePosixPath("/freqtrade/user_data")
HOST_USER_DATA = REPO_ROOT / "freqtrade" / "user_data"

# Every status the registry schema admits. Anything else — missing, empty,
# misspelled — is malformed and fails closed rather than being treated as benign.
VALID_STATUSES = ("NOT_STARTED", "RUNNING", "PAUSED", "CLOSED")

# May a runtime be started or capture be written for this row?
#   NOT_STARTED  pre-T0 qualification, the successor's current state
#   RUNNING      a live cohort resuming after a restart
# PAUSED is deliberately absent: a paused cohort is one a human stopped for a
# reason, and silently resuming it would erase that reason. CLOSED is absent
# because its evidence stream ended.
EXECUTABLE_STATUSES = ("NOT_STARTED", "RUNNING")

# Stopping or reading a lane is not executing it. A paused row must remain
# stoppable, or the only way out of PAUSED becomes editing the registry.
STOPPABLE_STATUSES = ("NOT_STARTED", "RUNNING", "PAUSED")

PATH_FIELDS = ("db_path", "log_path", "evidence_dir")


class LaneError(Exception):
    """Selection or path resolution failed. Always fatal, never advisory."""


@dataclass(frozen=True)
class Lane:
    """One instance's identity, in both namespaces, derived from the registry."""

    role: str
    status: str
    instance_dir: str
    bot_name: str
    container_instance_dir: PurePosixPath
    container_db_path: PurePosixPath
    container_log_path: PurePosixPath
    container_evidence_dir: PurePosixPath
    host_instance_dir: Path
    host_db_path: Path
    host_log_path: Path
    host_evidence_dir: Path

    def to_host(self, container_path: str | PurePosixPath) -> Path:
        """Map a container path into the host namespace, or refuse."""
        return container_to_host(container_path)

    def owns_host_path(self, candidate: Path) -> bool:
        """True when a real host path lies inside this lane, symlinks resolved.

        A lane whose own root resolves outside the canonical user_data directory
        owns nothing: comparing two paths that both follow the same escaping
        symlink makes them agree with each other while agreeing with nothing
        real, which is how an escaped lane passed every check.
        """
        if not self.root_is_canonical():
            return False
        resolved = _resolve(candidate)
        lane = _resolve(self.host_instance_dir)
        return resolved == lane or lane in resolved.parents

    def root_is_canonical(self) -> bool:
        """The lane root must really live under the project's user_data."""
        root = _resolve(HOST_USER_DATA)
        resolved = _resolve(self.host_instance_dir)
        return resolved == root or root in resolved.parents

    def assert_root_is_canonical(self) -> None:
        if not self.root_is_canonical():
            raise LaneError(
                f"{self.role}'s lane root {self.host_instance_dir} resolves to "
                f"{_resolve(self.host_instance_dir)}, outside {_resolve(HOST_USER_DATA)}"
            )

    def matches_evidence_dir(self, candidate: Path | str) -> bool:
        """The declared evidence directory, named in either namespace.

        A capture process inside the container names the container path; a host
        qualification names the host path. Both are the same lane, and refusing
        one of them is what made host-side qualification impossible.
        """
        text = str(candidate)
        if text == str(self.container_evidence_dir):
            return True
        return _resolve(Path(text)) == _resolve(self.host_evidence_dir)


def container_to_host(container_path: str | PurePosixPath) -> Path:
    """Map any container path under user_data into the host namespace.

    Module level because cross-instance containment has to ask the question
    about *other* lanes, which it may not be able to resolve into a Lane.
    """
    p = PurePosixPath(str(container_path))
    try:
        relative = p.relative_to(CONTAINER_USER_DATA)
    except ValueError as exc:
        raise LaneError(f"{p} is not under {CONTAINER_USER_DATA}; it has no host mapping") from exc
    return HOST_USER_DATA / relative


def _resolve(path: Path) -> Path:
    """Resolve symlinks as far as the path exists, then append the rest.

    ``Path.resolve()`` already does this on modern Python, but being explicit
    matters here: a symlink escape must be caught on a path whose leaf does not
    exist yet, which is the normal case for a lane that has never run.
    """
    return Path(path).expanduser().resolve()


def _load_registry(registry: dict | None) -> dict:
    if registry is not None:
        return registry
    try:
        return json.loads(COHORT_REGISTRY.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise LaneError(f"the cohort registry is unreadable: {exc}") from exc


def select_row(role: str, registry: dict | None = None) -> dict:
    """Structural selection: exactly one row for this role, or a hard failure.

    Status is validated for *shape* here — unknown or missing statuses are
    malformed and refused — but permission to execute is a separate question
    answered by ``resolve_lane(..., allowed_statuses=...)`` at the call site.
    """
    data = _load_registry(registry)
    instances = data.get("instances") or []
    matches = [item for item in instances if item.get("role") == role]
    if not matches:
        known = sorted({item.get("role") for item in instances if item.get("role")})
        raise LaneError(f"unknown instance role {role!r}; the registry declares {known}")
    if len(matches) > 1:
        raise LaneError(f"ambiguous selection: {len(matches)} instances declare role {role!r}")
    row = matches[0]
    status = row.get("status")
    if status not in VALID_STATUSES:
        raise LaneError(
            f"{role} declares status {status!r}, which is not one of {list(VALID_STATUSES)}; "
            "a row whose state cannot be read is never runnable"
        )
    return row


def resolve_lane(
    role: str,
    registry: dict | None = None,
    *,
    allowed_statuses: tuple[str, ...] | None = None,
) -> Lane:
    """The canonical lane for ``role``, in both namespaces.

    ``allowed_statuses`` is the call site's own contract: a launcher passes
    EXECUTABLE_STATUSES, a stop script passes STOPPABLE_STATUSES, and a reader
    passes nothing. One global rule would either let a paused cohort start or
    make a paused cohort unstoppable.
    """
    data = _load_registry(registry)
    row = select_row(role, data)
    status = row["status"]
    if allowed_statuses is not None and status not in allowed_statuses:
        raise LaneError(
            f"{role} is {status}; this operation allows only {list(allowed_statuses)}"
            + (
                f" (cohort {row.get('cohort_id')}, closed {row.get('closed_utc')})"
                if status == "CLOSED"
                else ""
            )
        )

    identity = row.get("runtime_identity") or {}
    bot_name = identity.get("bot_name")
    if not bot_name:
        raise LaneError(f"{role} declares no bot_name; a runtime identity must be bound before use")

    declared: dict[str, PurePosixPath] = {}
    for field in PATH_FIELDS:
        value = identity.get(field)
        if not value:
            raise LaneError(f"{role} declares no {field}")
        path = PurePosixPath(str(value))
        if not path.is_absolute() or CONTAINER_USER_DATA not in path.parents:
            raise LaneError(f"{role}.{field} ({value}) is not under {CONTAINER_USER_DATA}")
        declared[field] = path

    # The instance directory is the first component under user_data, taken from
    # the evidence path and then required of every other declared path. Deriving
    # it once and checking the rest against it is what stops a row from
    # declaring a database in one lane and evidence in another.
    instance_dir = declared["evidence_dir"].relative_to(CONTAINER_USER_DATA).parts[0]
    container_instance_dir = CONTAINER_USER_DATA / instance_dir
    for field, path in declared.items():
        if container_instance_dir not in path.parents:
            raise LaneError(
                f"{role}.{field} ({path}) is not inside its own lane {container_instance_dir}"
            )

    host_instance_dir = HOST_USER_DATA / instance_dir
    return Lane(
        role=role,
        status=status,
        instance_dir=instance_dir,
        bot_name=bot_name,
        container_instance_dir=container_instance_dir,
        container_db_path=declared["db_path"],
        container_log_path=declared["log_path"],
        container_evidence_dir=declared["evidence_dir"],
        host_instance_dir=host_instance_dir,
        host_db_path=HOST_USER_DATA / declared["db_path"].relative_to(CONTAINER_USER_DATA),
        host_log_path=HOST_USER_DATA / declared["log_path"].relative_to(CONTAINER_USER_DATA),
        host_evidence_dir=HOST_USER_DATA / declared["evidence_dir"].relative_to(CONTAINER_USER_DATA),
    )


def other_lanes(role: str, registry: dict | None = None) -> list[Lane]:
    """Every other resolvable lane, for cross-instance containment checks.

    A row that cannot be resolved is skipped rather than raising: the question
    being asked is "what else exists that I must not touch", and an unresolvable
    row is not a place anything can be written.
    """
    data = _load_registry(registry)
    lanes: list[Lane] = []
    for item in data.get("instances") or []:
        other = item.get("role")
        if not other or other == role:
            continue
        try:
            lanes.append(resolve_lane(other, data))
        except LaneError:
            continue
    return lanes
