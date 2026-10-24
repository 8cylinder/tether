from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from tether import completion
from tether.cli import main


def test_completion_path_uses_xdg_data_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    assert completion.completion_path() == (
        tmp_path / "data" / "bash-completion" / "completions" / "tether"
    )


def test_completion_path_falls_back_to_local_share(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert completion.completion_path() == (
        tmp_path / ".local" / "share" / "bash-completion" / "completions" / "tether"
    )


def test_write_bash_completion(tmp_path: Path) -> None:
    path = tmp_path / "bash-completion" / "completions" / "tether"

    written = completion.write_bash_completion(main, path)

    assert written == path
    script = path.read_text(encoding="utf-8")
    assert "_tether_completion" in script
    assert "complete -o nosort -F _tether_completion tether" in script
    assert "compopt" in script
    assert "zsh" not in script
    assert "fish" not in script


def test_bash_version_parses_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(completion.shutil, "which", lambda _: "/bin/bash")
    monkeypatch.setattr(
        completion.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="GNU bash, version 5.2.15(1)-release (x86_64-pc-linux-gnu)",
            returncode=0,
        ),
    )

    assert completion.bash_version() == (5, 2)


def test_bash_version_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(completion.shutil, "which", lambda _: None)

    assert completion.bash_version() is None


def test_completion_warning() -> None:
    assert completion.completion_warning((4, 3)) is not None
    assert completion.completion_warning((4, 4)) is None
    assert completion.completion_warning((5, 2)) is None
    assert completion.completion_warning(None) is not None


def test_cli_completions_writes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(completion, "bash_version", lambda: (5, 2))

    result = CliRunner().invoke(main, ["--completions"])

    path = tmp_path / "bash-completion" / "completions" / "tether"
    assert result.exit_code == 0
    assert path.exists()
    assert str(path) in result.output
    assert f"source {path}" in result.output
    assert "warning" not in result.output


def test_cli_completions_warns_on_old_bash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(completion, "bash_version", lambda: (3, 2))

    result = CliRunner().invoke(main, ["--completions"])

    assert result.exit_code == 0
    assert "bash 3.2 is older than 4.4" in result.output
