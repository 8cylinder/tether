"""Mount policy: which host paths are exposed inside the jail."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tether.config import Mount

WORKSPACE = "/workspace"
GIT_DIR = ".git"


class MountError(ValueError):
    """Raised when a mount cannot be constructed."""


@dataclass(frozen=True, slots=True)
class ContainerMount:
    """A host path bound into the container."""

    source: Path
    target: str
    mode: str

    def as_docker_arg(self) -> str:
        """Return the ``--volume`` value for this mount."""
        return f"{self.source}:{self.target}:{self.mode}"


def resolve_project(path: Path) -> Path:
    """Resolve *path* to an existing project directory.

    Raises:
        MountError: when the path is missing or not a directory.
    """
    project = path.expanduser().resolve()
    if not project.exists():
        raise MountError(f"project directory does not exist: {project}")
    if not project.is_dir():
        raise MountError(f"project path is not a directory: {project}")
    return project


def has_git(project: Path) -> bool:
    """Return whether *project* contains a ``.git`` directory."""
    return (project / GIT_DIR).is_dir()


def build_mounts(project: Path, *, extra: list[Mount] | None = None) -> list[ContainerMount]:
    """Build the mount policy for *project*.

    The project is mounted read-write at ``/workspace``. Its ``.git`` directory
    is mounted read-only on top, so the agent cannot rewrite history or delete
    the repository.

    Raises:
        MountError: when an extra mount source does not exist.
    """
    mounts = [ContainerMount(source=project, target=WORKSPACE, mode="rw")]

    if has_git(project):
        mounts.append(
            ContainerMount(
                source=project / GIT_DIR,
                target=f"{WORKSPACE}/{GIT_DIR}",
                mode="ro",
            )
        )

    for mount in extra or []:
        source = Path(mount.source).expanduser().resolve()
        if not source.exists():
            raise MountError(f"mount source does not exist: {source}")
        mounts.append(ContainerMount(source=source, target=mount.target, mode=mount.mode))

    return mounts
