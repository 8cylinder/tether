from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from tether.cli import main
from tether.completion import (
    CompletionError,
    completion_command,
    detect_shell,
    global_completion_command,
)


def test_detect_shell_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")
    assert detect_shell() == "zsh"


def test_detect_shell_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/bash")
    assert detect_shell("fish") == "fish"


def test_detect_shell_rejects_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHELL", "/bin/dash")
    with pytest.raises(CompletionError):
        detect_shell()


def test_completion_commands() -> None:
    assert completion_command("bash") == (
        "echo 'eval \"$(_TETHER_COMPLETE=bash_source tether)\"' >> ~/.bashrc"
    )
    assert completion_command("zsh") == (
        "echo 'eval \"$(_TETHER_COMPLETE=zsh_source tether)\"' >> ~/.zshrc"
    )
    assert completion_command("fish") == (
        "mkdir -p ~/.config/fish && "
        "echo '_TETHER_COMPLETE=fish_source tether | source' >> "
        "~/.config/fish/config.fish"
    )


def test_global_completion_commands() -> None:
    assert global_completion_command("bash") == (
        "_TETHER_COMPLETE=bash_source tether | "
        "sudo tee /usr/share/bash-completion/completions/tether >/dev/null\n"
        "source /usr/share/bash-completion/completions/tether"
    )
    assert global_completion_command("zsh") == (
        "_TETHER_COMPLETE=zsh_source tether | "
        "sudo tee /usr/local/share/zsh/site-functions/_tether >/dev/null\n"
        "source /usr/local/share/zsh/site-functions/_tether"
    )
    assert global_completion_command("fish") == (
        "_TETHER_COMPLETE=fish_source tether | "
        "sudo tee /usr/share/fish/vendor_completions.d/tether.fish >/dev/null\n"
        "source /usr/share/fish/vendor_completions.d/tether.fish"
    )


def test_build_prints_completion_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELL", "/bin/bash")

    result = CliRunner().invoke(main, ["build", "--install-completion"], color=True)

    assert result.exit_code == 0
    assert "Copy and paste the following command:" in result.output
    assert "\x1b[36m" in result.output
    assert ">> ~/.bashrc" in result.output
    assert 'eval "$(_TETHER_COMPLETE=bash_source tether)"' in result.output
    assert not (tmp_path / ".bashrc").exists()


def test_build_prints_global_completion_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELL", "/bin/bash")

    result = CliRunner().invoke(main, ["build", "--install-global-completion"])

    assert result.exit_code == 0
    assert "Copy and paste the following command:" in result.output
    assert (
        "_TETHER_COMPLETE=bash_source tether | "
        "sudo tee /usr/share/bash-completion/completions/tether >/dev/null"
    ) in result.output
    assert "source /usr/share/bash-completion/completions/tether" in result.output
    assert not (tmp_path / ".bashrc").exists()


def test_build_rejects_both_completion_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHELL", "/bin/bash")

    result = CliRunner().invoke(
        main,
        ["build", "--install-completion", "--install-global-completion"],
    )

    assert result.exit_code != 0
