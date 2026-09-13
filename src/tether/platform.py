"""Host platform and environment detection."""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class HostInfo:
    """Static description of the host machine running tether."""

    system: str
    machine: str
    uid: int
    gid: int
    home: Path


def host_info() -> HostInfo:
    """Return host information resolved from the current process environment."""
    return HostInfo(
        system=platform.system().lower(),
        machine=platform.machine().lower(),
        uid=os.getuid(),
        gid=os.getgid(),
        home=Path.home(),
    )


def default_profile_name() -> str:
    """Return the config profile name that matches the current platform."""
    return host_info().system


def find_docker() -> str | None:
    """Return the path to the docker CLI, or ``None`` when it is not installed."""
    return shutil.which("docker")


def config_dir() -> Path:
    """Return the tether configuration directory, honoring ``XDG_CONFIG_HOME``."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "tether"
