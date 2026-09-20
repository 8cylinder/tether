from __future__ import annotations

import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from tether import cli
from tether.auth import AwsCredentials
from tether.cli import _container_name
from tether.config import AwsCredentialExport, Config, Profile
from tether.docker import DockerError

_VALID_CONTAINER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _aws_config() -> Config:
    return Config(
        profiles={
            "linux": Profile(aws_credential_export=AwsCredentialExport(profile="bedrock")),
        }
    )


def _creds() -> AwsCredentials:
    return AwsCredentials(
        access_key_id="AKIA",
        secret_access_key="secret",
        session_token="tok",
        region="us-west-2",
    )


@pytest.mark.parametrize("name", ["my project", "weird:name*", "café", "-leading", ".hidden"])
def test_container_name_is_valid_docker_name(tmp_path: Path, name: str) -> None:
    project = tmp_path / name
    project.mkdir()
    result = _container_name(project)
    assert _VALID_CONTAINER_NAME.match(result)
    assert result.startswith("tether-")


def test_container_name_preserves_simple_name(tmp_path: Path) -> None:
    project = tmp_path / "my-app"
    project.mkdir()
    assert _container_name(project).startswith("tether-my-app-")


def test_container_name_distinguishes_projects(tmp_path: Path) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    assert _container_name(first) != _container_name(second)


def test_refresh_reports_docker_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> list[str]:
        raise DockerError("docker CLI not found on PATH")

    monkeypatch.setattr(cli, "_load_config", _aws_config)
    monkeypatch.setattr(cli, "list_tether_containers", boom)

    result = CliRunner().invoke(cli.app, ["refresh", "--profile", "linux"])

    assert result.exit_code == 1
    assert "docker CLI not found on PATH" in result.output


def test_launch_survives_container_lookup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_name: str) -> bool:
        raise DockerError("docker CLI not found on PATH")

    monkeypatch.setattr(cli, "_load_config", _aws_config)
    monkeypatch.setattr(cli, "resolve_aws_credentials", lambda _config: _creds())
    monkeypatch.setattr(cli, "container_running", boom)
    monkeypatch.setattr(cli, "opencode_config_mounts", lambda: ([], [], {}))
    monkeypatch.setattr(cli, "opencode_state_mounts", lambda _project: [])
    monkeypatch.setattr(cli, "opencode_auth_env", dict)

    result = CliRunner().invoke(cli.app, ["run", "--dry-run", "-C", str(tmp_path)])

    assert result.exit_code == 0
    assert "docker command:" in result.output


def test_run_continue_passes_flag_to_opencode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_load_config", Config)
    monkeypatch.setattr(cli, "opencode_config_mounts", lambda: ([], [], {}))
    monkeypatch.setattr(cli, "opencode_state_mounts", lambda _project: [])
    monkeypatch.setattr(cli, "opencode_auth_env", dict)

    result = CliRunner().invoke(
        cli.app,
        ["run", "--agent", "opencode", "--continue", "--dry-run", "-C", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert "--continue" in result.output


def test_run_continue_rejects_unsupported_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_load_config", Config)

    result = CliRunner().invoke(
        cli.app,
        ["run", "--agent", "gemini", "--continue", "--dry-run", "-C", str(tmp_path)],
    )

    assert result.exit_code == 1
    assert "does not support --continue" in result.output
