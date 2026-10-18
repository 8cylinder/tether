"""Commands for enabling shell completion for ``tether``."""

from __future__ import annotations

import os
import shlex
from pathlib import Path

SUPPORTED_SHELLS = ("bash", "zsh", "fish")

_COMPLETION_COMMAND = {
    "bash": 'eval "$(_TETHER_COMPLETE=bash_source tether)"',
    "zsh": 'eval "$(_TETHER_COMPLETE=zsh_source tether)"',
    "fish": "_TETHER_COMPLETE=fish_source tether | source",
}

_STARTUP_FILE = {
    "bash": "~/.bashrc",
    "zsh": "~/.zshrc",
    "fish": "~/.config/fish/config.fish",
}

_GLOBAL_COMPLETION_PATH = {
    "bash": "/usr/share/bash-completion/completions/tether",
    "zsh": "/usr/local/share/zsh/site-functions/_tether",
    "fish": "/usr/share/fish/vendor_completions.d/tether.fish",
}


class CompletionError(RuntimeError):
    """Raised when shell completion cannot be configured."""


def detect_shell(shell: str | None = None) -> str:
    """Return a supported shell name, detecting it from ``$SHELL`` if needed."""
    if shell is None:
        shell = os.environ.get("SHELL", "")
    shell = Path(shell).name
    if shell not in SUPPORTED_SHELLS:
        supported = ", ".join(SUPPORTED_SHELLS)
        raise CompletionError(
            f"Could not detect a supported shell (got {shell or 'nothing'!r}). "
            f"Supported shells: {supported}."
        )
    return shell


def completion_command(shell: str | None = None) -> str:
    """Return a command that appends completion setup to the shell startup file."""
    shell = detect_shell(shell)
    line = shlex.quote(_COMPLETION_COMMAND[shell])
    path = _STARTUP_FILE[shell]
    command = f"echo {line} >> {path}"
    if shell == "fish":
        return f"mkdir -p ~/.config/fish && {command}"
    return command


def global_completion_command(shell: str | None = None) -> str:
    """Return commands that install completion for all users and load it now."""
    shell = detect_shell(shell)
    path = _GLOBAL_COMPLETION_PATH[shell]
    return f"_TETHER_COMPLETE={shell}_source tether | sudo tee {path} >/dev/null\nsource {path}"
