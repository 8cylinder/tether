from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from tether import cli, docker
from tether.cli import main
from tether.config import Config


def test_info_lists_extra_installed_apps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = Config(
        path=tmp_path / "config.toml",
        default_agent="opencode",
        mounts={},
    )
    monkeypatch.setattr(cli, "_load_config", lambda: config)
    monkeypatch.setattr(docker, "docker_version", lambda: None)

    result = CliRunner().invoke(main, ["info"])

    assert result.exit_code == 0
    assert "extra installed apps:" in result.output
    for app in docker.EXTRA_APPS:
        assert app in result.output
    assert "uv" in docker.EXTRA_APPS


def test_config_flag_prints_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    expected = tmp_path / "tether" / "config.toml"
    monkeypatch.setattr(cli, "config_path", lambda: expected)

    result = CliRunner().invoke(main, ["--config"])

    assert result.exit_code == 0
    assert result.output.strip() == str(expected)
    assert not expected.exists()


def test_short_help_flag() -> None:
    result = CliRunner().invoke(main, ["-h"])

    assert result.exit_code == 0
    assert "Usage:" in result.output


def test_build_rejects_removed_completion_flags() -> None:
    result = CliRunner().invoke(main, ["build", "--install-completion"])

    assert result.exit_code != 0
    assert "No such option" in result.output


def _stub_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    config = Config(
        path=tmp_path / "config.toml",
        default_agent="opencode",
        mounts={"opencode": [], "claude": [], "antigravity": []},
    )
    monkeypatch.setattr(cli, "_load_config", lambda: config)
    monkeypatch.setattr(cli, "_require_docker", lambda: None)
    monkeypatch.setattr(cli, "_require_image", lambda: None)
    calls: list[list[str]] = []

    def fake_run_container(
        image: str,
        workdir: Path,
        mounts: list[tuple[str, str]],
        command: list[str],
    ) -> int:
        calls.append(command)
        return 0

    monkeypatch.setattr(docker, "run_container", fake_run_container)
    return calls


def test_bare_invocation_runs_default_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_run(tmp_path, monkeypatch)

    result = CliRunner().invoke(main, [])

    assert result.exit_code == 0
    assert calls == [["opencode", "--standalone", "--auto"]]


def test_bare_invocation_forwards_run_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_run(tmp_path, monkeypatch)

    result = CliRunner().invoke(main, ["--agent", "claude"])

    assert result.exit_code == 0
    assert calls == [["claude"]]
