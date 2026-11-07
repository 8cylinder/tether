from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from click.testing import CliRunner

from tether import cli, docker
from tether.cli import main
from tether.config import Config, ConfigError


def _config(
    tmp_path: Path,
    *,
    default_agent: str = "opencode",
    mounts: dict[str, list[str]] | None = None,
    args: dict[str, list[str]] | None = None,
) -> Config:
    return Config(
        path=tmp_path / "config.toml",
        default_agent=default_agent,
        mounts=(
            mounts
            if mounts is not None
            else {"opencode": [], "claude": [], "antigravity": []}
        ),
        args=args or {},
    )


def _stub_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> list[list[str]]:
    config = _config(tmp_path)
    monkeypatch.setattr(cli, "load_config", lambda: config)
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


def _info_stubs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: _config(tmp_path))
    monkeypatch.setattr(docker, "docker_version", lambda: None)


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


def test_bare_invocation_forwards_color_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_run(tmp_path, monkeypatch)

    result = CliRunner().invoke(main, ["--color", "never", "--agent", "claude"])

    assert result.exit_code == 0
    assert calls == [["claude"]]


def test_color_equals_form_forwards_run_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_run(tmp_path, monkeypatch)

    result = CliRunner().invoke(main, ["--color=never", "--agent", "claude"])

    assert result.exit_code == 0
    assert calls == [["claude"]]


def test_root_color_without_subcommand_runs_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_run(tmp_path, monkeypatch)

    result = CliRunner().invoke(main, ["--color", "never"])

    assert result.exit_code == 0
    assert calls == [["opencode", "--standalone", "--auto"]]


def test_shell_runs_bash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(cli, "load_config", lambda: _config(tmp_path))
    monkeypatch.setattr(cli, "_require_docker", lambda: None)
    monkeypatch.setattr(cli, "_require_image", lambda: None)

    def fake_run_container(
        image: str,
        workdir: Path,
        mounts: list[tuple[str, str]],
        command: list[str],
    ) -> int:
        calls.append(command)
        return 0

    monkeypatch.setattr(docker, "run_container", fake_run_container)

    result = CliRunner().invoke(main, ["shell"])

    assert result.exit_code == 0
    assert calls == [["bash"]]


def test_build_calls_docker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(cli, "load_config", lambda: _config(tmp_path))
    monkeypatch.setattr(cli, "_require_docker", lambda: None)
    monkeypatch.setattr(
        docker,
        "build_image",
        lambda image, *, uid, gid, update_software=False: calls.append(
            update_software
        ),
    )

    result = CliRunner().invoke(main, ["build"])

    assert result.exit_code == 0
    assert calls == [False]


def test_build_update_software(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(cli, "load_config", lambda: _config(tmp_path))
    monkeypatch.setattr(cli, "_require_docker", lambda: None)
    monkeypatch.setattr(
        docker,
        "build_image",
        lambda image, *, uid, gid, update_software=False: calls.append(
            update_software
        ),
    )

    result = CliRunner().invoke(main, ["build", "--update-software"])

    assert result.exit_code == 0
    assert calls == [True]


def test_clean_removed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: _config(tmp_path))
    monkeypatch.setattr(cli, "_require_docker", lambda: None)
    monkeypatch.setattr(docker, "remove_image", lambda: True)

    result = CliRunner().invoke(main, ["clean"])

    assert result.exit_code == 0
    assert "Removed" in result.stdout


def test_clean_nothing_to_remove(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: _config(tmp_path))
    monkeypatch.setattr(cli, "_require_docker", lambda: None)
    monkeypatch.setattr(docker, "remove_image", lambda: False)

    result = CliRunner().invoke(main, ["clean"])

    assert result.exit_code == 0
    assert "Nothing to remove" in result.stdout


def test_info_lists_extra_installed_apps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _info_stubs(tmp_path, monkeypatch)

    result = CliRunner().invoke(main, ["info"])

    assert result.exit_code == 0
    assert "extra installed apps:" in result.output
    for app in docker.EXTRA_APPS:
        assert app in result.output
    assert "uv" in docker.EXTRA_APPS


def test_info_present_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: _config(tmp_path))
    monkeypatch.setattr(docker, "docker_version", lambda: "27.0")
    monkeypatch.setattr(docker, "image_exists", lambda: True)

    result = CliRunner().invoke(main, ["info"])

    assert result.exit_code == 0
    assert "present" in result.stdout


def test_info_does_not_print_configured_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path, args={"opencode": ["--secret=abc"]})
    monkeypatch.setattr(cli, "load_config", lambda: config)
    monkeypatch.setattr(docker, "docker_version", lambda: None)

    result = CliRunner().invoke(main, ["info"])

    assert result.exit_code == 0
    assert "--secret=abc" not in result.stdout


def test_config_flag_prints_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = tmp_path / "tether" / "config.toml"
    monkeypatch.setattr(cli, "config_path", lambda: expected)

    result = CliRunner().invoke(main, ["--config"])

    assert result.exit_code == 0
    assert result.stdout.strip() == str(expected)
    assert "\x1b[" not in result.stdout
    assert not expected.exists()


def test_config_flag_does_not_load_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail() -> Config:
        raise AssertionError("config must not load for --config")

    monkeypatch.setattr(cli, "load_config", fail)

    result = CliRunner().invoke(main, ["--config"])

    assert result.exit_code == 0


def test_version_matches_pyproject() -> None:
    pyproject = tomllib.loads(
        Path("pyproject.toml").read_text(encoding="utf-8")
    )
    expected = pyproject["project"]["version"]

    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert f"tether, version {expected}" in result.stdout
    assert "\x1b[" not in result.stdout


def test_version_does_not_load_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail() -> Config:
        raise AssertionError("config must not load for --version")

    monkeypatch.setattr(cli, "load_config", fail)

    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0


@pytest.mark.parametrize(
    "args",
    [
        ["-h"],
        ["--help"],
        ["run", "-h"],
        ["run", "--help"],
        ["build", "-h"],
        ["info", "-h"],
        ["shell", "-h"],
        ["clean", "-h"],
    ],
)
def test_help_matrix(
    args: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: _config(tmp_path))

    result = CliRunner().invoke(main, args)

    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "\x1b[" not in result.output


def test_help_does_not_load_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail() -> Config:
        raise AssertionError("config must not load for --help")

    monkeypatch.setattr(cli, "load_config", fail)

    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0


def test_color_always_emits_ansi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _info_stubs(tmp_path, monkeypatch)

    result = CliRunner().invoke(main, ["--color", "always", "info"])

    assert "\x1b[" in result.stdout


def test_color_never_emits_no_ansi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _info_stubs(tmp_path, monkeypatch)

    result = CliRunner().invoke(main, ["--color", "never", "info"])

    assert "\x1b[" not in result.stdout


def test_color_auto_captured_emits_no_ansi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _info_stubs(tmp_path, monkeypatch)

    result = CliRunner().invoke(main, ["info"])

    assert "\x1b[" not in result.stdout


def test_force_color_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _info_stubs(tmp_path, monkeypatch)
    monkeypatch.setenv("FORCE_COLOR", "1")

    result = CliRunner().invoke(main, ["info"])

    assert "\x1b[" in result.stdout


def test_no_color_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _info_stubs(tmp_path, monkeypatch)
    monkeypatch.setenv("NO_COLOR", "1")

    result = CliRunner().invoke(main, ["info"])

    assert "\x1b[" not in result.stdout


def test_always_overrides_no_color(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _info_stubs(tmp_path, monkeypatch)
    monkeypatch.setenv("NO_COLOR", "1")

    result = CliRunner().invoke(main, ["--color", "always", "info"])

    assert "\x1b[" in result.stdout


def test_term_dumb_disables_color(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _info_stubs(tmp_path, monkeypatch)
    monkeypatch.setenv("TERM", "dumb")

    result = CliRunner().invoke(main, ["info"])

    assert "\x1b[" not in result.stdout


def test_dynamic_values_are_escaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = Config(
        path=tmp_path / "[red]config.toml",
        default_agent="opencode",
        mounts={"opencode": [], "claude": [], "antigravity": []},
    )
    monkeypatch.setattr(cli, "load_config", lambda: config)
    monkeypatch.setattr(docker, "docker_version", lambda: None)

    result = CliRunner().invoke(main, ["--color", "always", "info"])

    assert "[red]config.toml" in result.stdout


def test_mount_warnings_go_to_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(
        tmp_path,
        mounts={
            "opencode": ["~/.missing-file.json"],
            "claude": [],
            "antigravity": [],
        },
    )
    monkeypatch.setattr(cli, "load_config", lambda: config)
    monkeypatch.setattr(cli, "_require_docker", lambda: None)
    monkeypatch.setattr(cli, "_require_image", lambda: None)
    monkeypatch.setattr(docker, "run_container", lambda *args, **kwargs: 0)

    result = CliRunner().invoke(main, ["run"])

    assert result.exit_code == 0
    assert "warning:" in result.stderr


def test_errors_go_to_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: _config(tmp_path))
    monkeypatch.setattr(docker, "docker_available", lambda: False)

    result = CliRunner().invoke(main, ["run"])

    assert result.exit_code != 0
    assert "docker was not found" in result.stderr
    assert result.stdout == ""


def test_config_error_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail() -> Config:
        raise ConfigError("bad config")

    monkeypatch.setattr(cli, "load_config", fail)

    result = CliRunner().invoke(main, ["info"])

    assert result.exit_code != 0
    assert "bad config" in result.stderr


def test_build_rejects_removed_completion_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: _config(tmp_path))

    result = CliRunner().invoke(main, ["build", "--install-completion"])

    assert result.exit_code != 0
    assert "No such option" in result.output
