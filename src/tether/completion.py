"""Generate bash completion for ``tether``."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from click import Command
from click.shell_completion import BashComplete

APP_NAME = "tether"
MIN_BASH = (4, 4)


def completion_path() -> Path:
    """Return where the bash completion script should be written.

    Uses ``$XDG_DATA_HOME/bash-completion/completions/tether`` and falls back
    to ``~/.local/share/bash-completion/completions/tether`` when
    ``XDG_DATA_HOME`` is unset.
    """
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(os.path.expanduser(data_home)) if data_home else Path.home() / ".local" / "share"
    return base / "bash-completion" / "completions" / APP_NAME


def write_bash_completion(command: Command, path: Path | None = None) -> Path:
    """Write the bash completion script for ``command`` and return its path."""
    destination = Path(path) if path is not None else completion_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    script = BashComplete(command, {}, APP_NAME, "_TETHER_COMPLETE").source()
    destination.write_text(script, encoding="utf-8")
    return destination


def bash_version() -> tuple[int, int] | None:
    """Return the ``(major, minor)`` version of the bash on PATH, if any."""
    executable = shutil.which("bash")
    if executable is None:
        return None
    try:
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    match = re.search(r"version (\d+)\.(\d+)", result.stdout)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def completion_warning(version: tuple[int, int] | None) -> str | None:
    """Return a warning when bash cannot run the generated completion script."""
    if version is None:
        return "bash was not found on PATH; completions require bash 4.4 or newer."
    if version < MIN_BASH:
        major, minor = version
        return (
            f"bash {major}.{minor} is older than 4.4; "
            "the completion script requires bash 4.4 or newer."
        )
    return None
