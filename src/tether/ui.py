"""Rich console helpers for consistent, color-aware output."""

from __future__ import annotations

from typing import Any

from rich.console import Console


def console(**kwargs: Any) -> Console:
    """Return a console that writes to the current standard output.

    Rich disables color automatically when the output is not a terminal, so
    piped output stays plain. ``NO_COLOR`` is honored as well. Soft wrapping
    keeps long paths and commands on one line so they stay copy-pasteable.
    """
    kwargs.setdefault("highlight", False)
    kwargs.setdefault("soft_wrap", True)
    return Console(**kwargs)


def error_console(**kwargs: Any) -> Console:
    """Return a console that writes to the current standard error."""
    kwargs.setdefault("stderr", True)
    kwargs.setdefault("highlight", False)
    kwargs.setdefault("soft_wrap", True)
    return Console(**kwargs)
