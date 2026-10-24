from __future__ import annotations

import io

from tether import ui


def test_console_disables_color_when_not_a_terminal() -> None:
    stream = io.StringIO()

    ui.console(file=stream).print("[green]ok[/green]")

    assert stream.getvalue() == "ok\n"


def test_console_uses_color_on_a_terminal() -> None:
    stream = io.StringIO()

    ui.console(file=stream, force_terminal=True, color_system="standard").print("[green]ok[/green]")

    assert "\x1b[32m" in stream.getvalue()
