from __future__ import annotations

import io

import pytest

from tether import ui


def test_console_disables_color_when_not_a_terminal() -> None:
    stream = io.StringIO()

    ui.console(file=stream).print("[green]ok[/green]")

    assert stream.getvalue() == "ok\n"


def test_console_uses_color_on_a_terminal() -> None:
    stream = io.StringIO()

    ui.console(file=stream, force_terminal=True, color_system="standard").print(
        "[green]ok[/green]"
    )

    assert "\x1b[32m" in stream.getvalue()


def test_color_always_emits_ansi() -> None:
    stream = io.StringIO()

    ui.console(mode="always", file=stream, color_system="standard").print(
        "[green]ok[/green]"
    )

    assert "\x1b[32m" in stream.getvalue()


def test_color_never_emits_no_ansi() -> None:
    stream = io.StringIO()

    ui.console(
        mode="never",
        file=stream,
        force_terminal=True,
        color_system="standard",
    ).print("[green]ok[/green]")

    assert "\x1b[" not in stream.getvalue()


def test_no_color_env_disables_ansi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    stream = io.StringIO()

    ui.console(file=stream, force_terminal=True, color_system="standard").print(
        "[green]ok[/green]"
    )

    assert "\x1b[" not in stream.getvalue()


def test_force_color_env_emits_ansi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")
    stream = io.StringIO()

    ui.console(file=stream, color_system="standard").print("[green]ok[/green]")

    assert "\x1b[32m" in stream.getvalue()


def test_force_color_zero_disables_ansi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FORCE_COLOR", "0")
    stream = io.StringIO()

    ui.console(file=stream, force_terminal=True, color_system="standard").print(
        "[green]ok[/green]"
    )

    assert "\x1b[" not in stream.getvalue()


def test_term_dumb_disables_ansi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TERM", "dumb")
    stream = io.StringIO()

    ui.console(file=stream, force_terminal=True, color_system="standard").print(
        "[green]ok[/green]"
    )

    assert "\x1b[" not in stream.getvalue()


def test_always_overrides_no_color(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    stream = io.StringIO()

    ui.console(mode="always", file=stream, color_system="standard").print(
        "[green]ok[/green]"
    )

    assert "\x1b[32m" in stream.getvalue()


def test_error_console_uses_stderr() -> None:
    console = ui.error_console(mode="never")

    assert console.stderr is True


def test_color_setting() -> None:
    assert ui.color_setting("always") is True
    assert ui.color_setting("never") is False
    assert ui.color_setting("auto") is None
