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
