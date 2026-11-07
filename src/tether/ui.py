"""Rich console helpers for consistent, color-aware output."""

from __future__ import annotations

import os
from typing import Any

from rich.console import Console

ColorMode = str


def color_setting(mode: str) -> bool | None:
    """Return the Click ``ctx.color`` value for a color mode."""
    if mode == "always":
        return True
    if mode == "never":
        return False
    return None


def _console_options(mode: str) -> dict[str, bool]:
    if mode == "always":
        return {"force_terminal": True, "no_color": False}
    if mode == "never":
        return {"force_terminal": False, "no_color": True}

    force = os.environ.get("FORCE_COLOR")
    if force is not None:
        if force in ("0", "false", "no"):
            return {"force_terminal": False, "no_color": True}
        return {"force_terminal": True, "no_color": False}

    no_color = os.environ.get("NO_COLOR")
    if no_color:
        return {"no_color": True}
    if os.environ.get("TERM") == "dumb":
        return {"force_terminal": False, "no_color": True}
    return {}


def console(
    *,
    mode: str = "auto",
    stderr: bool = False,
    **kwargs: Any,  # noqa: ANN401
) -> Console:
    """Return a console that writes to the current standard output.

    Rich disables color automatically when the output is not a terminal, so
    piped output stays plain. ``--color``, ``NO_COLOR``, ``FORCE_COLOR`` and
    ``TERM=dumb`` are applied before the console is created. Soft wrapping
    keeps long paths and commands on one line so they stay copy-pasteable.
    """
    options = _console_options(mode)
    for key, value in options.items():
        kwargs.setdefault(key, value)
    kwargs.setdefault("stderr", stderr)
    kwargs.setdefault("highlight", False)
    kwargs.setdefault("soft_wrap", True)
    return Console(**kwargs)


def error_console(
    *,
    mode: str = "auto",
    **kwargs: Any,  # noqa: ANN401
) -> Console:
    """Return a console that writes to the current standard error."""
    return console(mode=mode, stderr=True, **kwargs)
