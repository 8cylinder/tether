from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from tether import completions
from tether.cli import main


def test_completion_path_uses_bash_completion_user_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "BASH_COMPLETION_USER_DIR", f"{tmp_path / 'one'}:{tmp_path / 'two'}"
    )

    assert completions.completion_path() == (
        tmp_path / "one" / "bash-completion" / "completions" / "tether.bash"
    )


def test_completion_path_skips_empty_user_dir_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASH_COMPLETION_USER_DIR", f":{tmp_path / 'two'}:")

    assert completions.completion_path() == (
        tmp_path / "two" / "bash-completion" / "completions" / "tether.bash"
    )


def test_completion_path_uses_xdg_data_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    assert completions.completion_path() == (
        tmp_path / "data" / "bash-completion" / "completions" / "tether.bash"
    )


def test_completion_path_falls_back_to_local_share(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert completions.completion_path() == (
        tmp_path
        / ".local"
        / "share"
        / "bash-completion"
        / "completions"
        / "tether.bash"
    )


def test_completion_path_expands_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("BASH_COMPLETION_USER_DIR", "~/completions")

    assert completions.completion_path() == (
        tmp_path
        / "completions"
        / "bash-completion"
        / "completions"
        / "tether.bash"
    )


def test_completion_path_is_absolute_for_relative_user_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BASH_COMPLETION_USER_DIR", "relative")

    path = completions.completion_path()

    assert path.is_absolute()
    assert path == (
        tmp_path
        / "relative"
        / "bash-completion"
        / "completions"
        / "tether.bash"
    )


def test_install_bash_completion_writes_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASH_COMPLETION_USER_DIR", str(tmp_path))

    path = completions.install_bash_completion(main, "tether", "0.3.0")

    assert path == tmp_path / "bash-completion" / "completions" / "tether.bash"
    assert path.exists()
    assert path.stat().st_mode & 0o777 == 0o644
    assert path.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")


def test_install_bash_completion_overwrites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASH_COMPLETION_USER_DIR", str(tmp_path))
    path = tmp_path / "bash-completion" / "completions" / "tether.bash"
    path.parent.mkdir(parents=True)
    path.write_text("old", encoding="utf-8")

    completions.install_bash_completion(main, "tether", "0.3.0")

    assert "old" not in path.read_text(encoding="utf-8")


def test_generated_script_is_static() -> None:
    script = completions.generate_bash(main, "tether", "0.3.0")

    assert "_TETHER_COMPLETE" not in script
    assert "bash_complete" not in script
    assert "_tether_complete" in script
    assert "_tether_cmd_0" in script
    assert "complete -o nosort -o bashdefault -o default" in script
    assert "version 0.3.0" in script
    assert "tether.bash" not in script


def test_generated_script_passes_bash_syntax_check(
    tmp_path: Path,
) -> None:
    script = tmp_path / "completion.bash"
    script.write_text(
        completions.generate_bash(main, "tether", "0.3.0"),
        encoding="utf-8",
    )

    result = subprocess.run(
        ["bash", "-n", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def _run_completion(tmp_path: Path, words: list[str], cword: int) -> list[str]:
    script = tmp_path / "completion.bash"
    script.write_text(
        completions.generate_bash(main, "tether", "0.3.0"),
        encoding="utf-8",
    )
    word_list = " ".join(shlex.quote(word) for word in words)
    code = (
        f"source {shlex.quote(str(script))}\n"
        f"COMP_WORDS=({word_list})\n"
        f"COMP_CWORD={cword}\n"
        "_tether_complete\n"
        "printf '%s\\n' \"${COMPREPLY[@]}\"\n"
    )
    result = subprocess.run(
        ["bash", "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return [line for line in result.stdout.splitlines() if line]


def test_completes_subcommands(tmp_path: Path) -> None:
    replies = _run_completion(tmp_path, ["tether", ""], 1)

    assert "run" in replies
    assert "build" in replies
    assert "info" in replies
    assert "shell" in replies
    assert "clean" in replies


def test_completes_root_options(tmp_path: Path) -> None:
    replies = _run_completion(tmp_path, ["tether", "-"], 1)

    assert "-h" in replies
    assert "--help" in replies
    assert "--version" in replies
    assert "--config" in replies
    assert "--completions" in replies
    assert "--color" in replies


def test_completes_subcommand_options(tmp_path: Path) -> None:
    replies = _run_completion(tmp_path, ["tether", "run", "-"], 2)

    assert "--agent" in replies
    assert "--workdir" in replies
    assert "-h" in replies
    assert "--help" in replies
    assert "--config" not in replies


def test_completes_choice_values(tmp_path: Path) -> None:
    replies = _run_completion(tmp_path, ["tether", "run", "--agent", ""], 3)

    assert replies == ["opencode", "claude", "antigravity"]


def test_completes_color_choice(tmp_path: Path) -> None:
    replies = _run_completion(tmp_path, ["tether", "--color", ""], 2)

    assert replies == ["auto", "always", "never"]


def test_completes_option_equals_value(tmp_path: Path) -> None:
    replies = _run_completion(tmp_path, ["tether", "run", "--agent=o"], 2)

    assert replies == ["--agent=opencode"]


def test_completes_directory_values(tmp_path: Path) -> None:
    replies = _run_completion(tmp_path, ["tether", "run", "--workdir", ""], 3)

    assert "src" in replies


def test_does_not_complete_options_after_double_dash(
    tmp_path: Path,
) -> None:
    replies = _run_completion(tmp_path, ["tether", "run", "--", "-"], 3)

    assert replies == []


def test_hidden_commands_and_options_are_excluded() -> None:
    @click.group()
    def root() -> None:
        pass

    @root.command()
    @click.option("--visible")
    @click.option("--hidden-opt", hidden=True)
    def shown(visible: str | None, hidden_opt: str | None) -> None:
        pass

    @root.command(hidden=True)
    def secret() -> None:
        pass

    script = completions.generate_bash(root, "root", "1.0")

    assert "secret" not in script
    assert "--hidden-opt" not in script
    assert "--visible" in script


def test_options_with_multiple_count_and_nargs() -> None:
    @click.group()
    def root() -> None:
        pass

    @root.command()
    @click.option("--tag", multiple=True)
    @click.option("-v", "--verbose", count=True)
    @click.option("--pair", nargs=2, type=(str, int))
    @click.option("--nums", nargs=2, type=int)
    @click.argument("paths", nargs=-1, type=click.Path())
    def cmd(
        tag: tuple[str, ...],
        verbose: int,
        pair: tuple[str, int],
        nums: tuple[int, int],
        paths: tuple[str, ...],
    ) -> None:
        pass

    script = completions.generate_bash(root, "root", "1.0")

    assert "--tag|1|none" in script
    assert "-v|0" in script
    assert "--verbose|0" in script
    assert "--pair|2|none|none" in script
    assert "--nums|2|none|none" in script
    assert "path:any" in script


def test_bash_version_parses_bash_versinfo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(completions.shutil, "which", lambda _: "/bin/bash")
    monkeypatch.setattr(
        completions.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="5.2"),
    )

    assert completions.bash_version() == (5, 2)


def test_bash_version_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(completions.shutil, "which", lambda _: None)

    assert completions.bash_version() is None


def test_bash_version_subprocess_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(completions.shutil, "which", lambda _: "/bin/bash")

    def fail(*args: object, **kwargs: object) -> object:
        raise OSError("boom")

    monkeypatch.setattr(completions.subprocess, "run", fail)

    assert completions.bash_version() is None


def test_bash_version_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(completions.shutil, "which", lambda _: "/bin/bash")
    monkeypatch.setattr(
        completions.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="5.2"),
    )

    assert completions.bash_version() is None


def test_bash_version_bad_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(completions.shutil, "which", lambda _: "/bin/bash")
    monkeypatch.setattr(
        completions.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="nope"),
    )

    assert completions.bash_version() is None


def test_completion_warning() -> None:
    assert completions.completion_warning((4, 3)) is not None
    assert completions.completion_warning((4, 4)) is None
    assert completions.completion_warning((5, 2)) is None
    assert completions.completion_warning(None) is not None


def test_cli_completions_writes_file_and_uses_stdout_for_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASH_COMPLETION_USER_DIR", str(tmp_path))
    monkeypatch.setattr(completions, "bash_version", lambda: (5, 2))

    result = CliRunner().invoke(main, ["--completions"])

    path = tmp_path / "bash-completion" / "completions" / "tether.bash"
    assert result.exit_code == 0
    assert path.exists()
    assert result.stdout.strip() == str(path)
    assert "source" in result.stderr
    assert "warning" not in result.stderr


def test_cli_completions_warns_on_old_bash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASH_COMPLETION_USER_DIR", str(tmp_path))
    monkeypatch.setattr(completions, "bash_version", lambda: (3, 2))

    result = CliRunner().invoke(main, ["--completions"])

    assert result.exit_code == 0
    assert "bash 3.2 is older than 4.4" in result.stderr
