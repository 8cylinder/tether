from __future__ import annotations

import stat
from pathlib import Path

import pytest

from tether.config import Mount
from tether.mounts import (
    _TETHER_STATUS_LINE,
    CONTAINER_CLAUDE_DIR,
    CONTAINER_CLAUDE_JSON,
    CONTAINER_CLAUDE_SETTINGS,
    CONTAINER_OPENCODE_CONFIG_BASE,
    CONTAINER_OPENCODE_CONFIG_DIR,
    CONTAINER_OPENCODE_DATA_DIR,
    CONTAINER_OPENCODE_STATE_DIR,
    MountError,
    build_mounts,
    claude_config_mounts,
    has_git,
    opencode_config_mounts,
    opencode_state_mounts,
    project_state_dir,
    resolve_project,
)


def test_resolve_project_missing(tmp_path: Path) -> None:
    with pytest.raises(MountError):
        resolve_project(tmp_path / "nope")


def test_resolve_project_not_a_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(MountError):
        resolve_project(file_path)


def test_build_mounts_workspace_rw(tmp_path: Path) -> None:
    mounts = build_mounts(tmp_path)
    assert len(mounts) == 1
    assert mounts[0].target == "/workspace"
    assert mounts[0].mode == "rw"
    assert mounts[0].as_docker_arg() == f"{tmp_path}:/workspace:rw"


def test_build_mounts_git_read_only(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    mounts = build_mounts(tmp_path)
    git_mount = mounts[1]
    assert git_mount.target == "/workspace/.git"
    assert git_mount.mode == "ro"
    assert has_git(tmp_path)


def test_build_mounts_without_git(tmp_path: Path) -> None:
    mounts = build_mounts(tmp_path)
    assert all(mount.target != "/workspace/.git" for mount in mounts)
    assert not has_git(tmp_path)


def test_build_mounts_extra_valid(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    extra_dir = tmp_path_factory.mktemp("extra")
    mounts = build_mounts(tmp_path, extra=[Mount(source=str(extra_dir), target="/data", mode="ro")])
    assert mounts[-1].target == "/data"
    assert mounts[-1].mode == "ro"


def test_build_mounts_extra_missing_raises(tmp_path: Path) -> None:
    extra = Mount(source=str(tmp_path / "ghost"), target="/data", mode="ro")
    with pytest.raises(MountError):
        build_mounts(tmp_path, extra=[extra])


def test_build_mounts_denies_dangerous_source(tmp_path: Path) -> None:
    extra = Mount(source="/", target="/host", mode="ro")
    with pytest.raises(MountError, match="dangerous"):
        build_mounts(tmp_path, extra=[extra])


def test_build_mounts_denies_ssh_dir(tmp_path: Path) -> None:
    ssh_dir = Path.home() / ".ssh"
    if not ssh_dir.exists():
        pytest.skip("~/.ssh does not exist")
    extra = Mount(source="~/.ssh", target="/ssh", mode="ro")
    with pytest.raises(MountError, match="dangerous"):
        build_mounts(tmp_path, extra=[extra])


@pytest.mark.parametrize("target", ["/workspace", "/workspace/.git", "/workspace/nested"])
def test_build_mounts_denies_workspace_target(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory, target: str
) -> None:
    extra_dir = tmp_path_factory.mktemp("extra")
    extra = Mount(source=str(extra_dir), target=target, mode="rw")
    with pytest.raises(MountError, match="managed workspace"):
        build_mounts(tmp_path, extra=[extra])


def test_build_mounts_denies_workspace_target_via_traversal(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    extra_dir = tmp_path_factory.mktemp("extra")
    extra = Mount(source=str(extra_dir), target="/workspace/../workspace/.git", mode="rw")
    with pytest.raises(MountError, match="managed workspace"):
        build_mounts(tmp_path, extra=[extra])


def test_build_mounts_denies_docker_socket_target(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    extra_dir = tmp_path_factory.mktemp("extra")
    extra = Mount(source=str(extra_dir), target="/var/run/docker.sock", mode="rw")
    with pytest.raises(MountError, match="dangerous target"):
        build_mounts(tmp_path, extra=[extra])


def test_claude_config_mounts_both_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    mounts, temp_files = claude_config_mounts()
    assert len(mounts) == 3
    assert mounts[0].source == claude_dir
    assert mounts[0].target == CONTAINER_CLAUDE_DIR
    assert mounts[0].mode == "ro"
    assert mounts[1].target == CONTAINER_CLAUDE_SETTINGS
    assert mounts[1].mode == "ro"
    assert mounts[2].source == claude_json
    assert mounts[2].target == CONTAINER_CLAUDE_JSON
    assert mounts[2].mode == "rw"
    assert len(temp_files) == 1
    import json

    filtered = json.loads(temp_files[0].path.read_text(encoding="utf-8"))
    assert filtered["statusLine"] == _TETHER_STATUS_LINE
    assert filtered["sandbox"] == {"enabled": False}
    assert filtered["permissions"] == {"allow": ["Bash(*)"], "deny": ["Edit", "Write"]}
    for f in temp_files:
        f.cleanup()


def test_claude_config_mounts_dir_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".claude").mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    mounts, temp_files = claude_config_mounts()
    assert len(mounts) == 2
    assert mounts[0].target == CONTAINER_CLAUDE_DIR
    assert mounts[1].target == CONTAINER_CLAUDE_SETTINGS
    assert len(temp_files) == 1
    import json

    filtered = json.loads(temp_files[0].path.read_text(encoding="utf-8"))
    assert filtered["statusLine"] == _TETHER_STATUS_LINE
    assert filtered["sandbox"] == {"enabled": False}
    assert filtered["permissions"] == {"allow": ["Bash(*)"], "deny": ["Edit", "Write"]}
    for f in temp_files:
        f.cleanup()


def test_claude_config_mounts_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    mounts, temp_files = claude_config_mounts()
    assert mounts == []
    assert temp_files == []


def test_claude_config_mounts_filters_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings = claude_dir / "settings.json"
    settings.write_text(
        '{"theme": "dark", "env": {"FOO": "bar"}, "awsAuthRefresh": "aws sso login",'
        ' "permissions": {"allow": ["*"]}, "sandbox": {"enabled": true}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    mounts, temp_files = claude_config_mounts()
    assert len(mounts) == 2
    assert mounts[0].target == CONTAINER_CLAUDE_DIR
    assert mounts[1].target == CONTAINER_CLAUDE_SETTINGS
    assert mounts[1].mode == "ro"
    assert len(temp_files) == 1
    import json

    filtered = json.loads(temp_files[0].path.read_text(encoding="utf-8"))
    assert "theme" in filtered
    assert "env" not in filtered
    assert "awsAuthRefresh" not in filtered
    assert filtered["statusLine"] == _TETHER_STATUS_LINE
    assert filtered["sandbox"] == {"enabled": False}
    assert filtered["permissions"] == {"allow": ["Bash(*)"], "deny": ["Edit", "Write"]}
    for f in temp_files:
        f.cleanup()


def test_claude_config_mounts_clean_settings_gets_statusline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings = claude_dir / "settings.json"
    settings.write_text('{"theme": "dark", "model": "opus"}', encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    mounts, temp_files = claude_config_mounts()
    assert len(mounts) == 2
    assert mounts[1].target == CONTAINER_CLAUDE_SETTINGS
    assert len(temp_files) == 1
    import json

    filtered = json.loads(temp_files[0].path.read_text(encoding="utf-8"))
    assert filtered["theme"] == "dark"
    assert filtered["model"] == "opus"
    assert filtered["statusLine"] == _TETHER_STATUS_LINE
    assert filtered["sandbox"] == {"enabled": False}
    assert filtered["permissions"] == {"allow": ["Bash(*)"], "deny": ["Edit", "Write"]}
    for f in temp_files:
        f.cleanup()


def test_claude_config_mounts_stages_container_readable_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    _, temp_files = claude_config_mounts()
    try:
        staged = temp_files[0]
        assert stat.S_IMODE(staged.path.stat().st_mode) == 0o644
        assert stat.S_IMODE(staged.path.parent.stat().st_mode) == 0o700
    finally:
        for f in temp_files:
            f.cleanup()


def test_opencode_config_mounts_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    mounts, temp_files, env = opencode_config_mounts()
    assert mounts == []
    assert temp_files == []
    assert env == {}


def test_opencode_config_mounts_dir_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / ".config" / "opencode"
    config_dir.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    mounts, temp_files, env = opencode_config_mounts()
    assert len(mounts) == 1
    assert mounts[0].source == config_dir
    assert mounts[0].target == CONTAINER_OPENCODE_CONFIG_DIR
    assert mounts[0].mode == "ro"
    assert temp_files == []
    assert env == {"OPENCODE_CONFIG_DIR": CONTAINER_OPENCODE_CONFIG_DIR}


def test_opencode_config_mounts_plain_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / ".config" / "opencode"
    config_dir.mkdir(parents=True)
    config = config_dir / "opencode.json"
    config.write_text('{"default_agent": "custom"}', encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    mounts, temp_files, env = opencode_config_mounts()
    assert len(mounts) == 2
    assert mounts[0].target == CONTAINER_OPENCODE_CONFIG_DIR
    assert mounts[1].target == f"{CONTAINER_OPENCODE_CONFIG_BASE}.json"
    assert mounts[1].mode == "ro"
    assert len(temp_files) == 1
    assert temp_files[0].path.read_text(encoding="utf-8") == '{"default_agent": "custom"}'
    assert env["OPENCODE_CONFIG"] == f"{CONTAINER_OPENCODE_CONFIG_BASE}.json"
    for f in temp_files:
        f.cleanup()


def test_opencode_config_mounts_resolves_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    config_dir = home / ".config" / "opencode"
    config_dir.mkdir(parents=True)
    target = tmp_path / "elsewhere" / "opencode.jsonc"
    target.parent.mkdir(parents=True)
    target.write_text('{"default_agent": "from-symlink"}', encoding="utf-8")
    (config_dir / "opencode.jsonc").symlink_to(target)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    mounts, temp_files, env = opencode_config_mounts()
    assert len(temp_files) == 1
    assert temp_files[0].path.read_text(encoding="utf-8") == '{"default_agent": "from-symlink"}'
    assert mounts[1].target == f"{CONTAINER_OPENCODE_CONFIG_BASE}.jsonc"
    assert env["OPENCODE_CONFIG"] == f"{CONTAINER_OPENCODE_CONFIG_BASE}.jsonc"
    for f in temp_files:
        f.cleanup()


def test_opencode_config_mounts_stages_container_readable_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / ".config" / "opencode"
    config_dir.mkdir(parents=True)
    (config_dir / "opencode.json").write_text('{"model": "x"}', encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    _, temp_files, _ = opencode_config_mounts()
    try:
        staged = temp_files[0]
        assert stat.S_IMODE(staged.path.stat().st_mode) == 0o644
        assert stat.S_IMODE(staged.path.parent.stat().st_mode) == 0o700
    finally:
        for f in temp_files:
            f.cleanup()


def test_opencode_state_mounts_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "proj"
    project.mkdir()
    mounts = opencode_state_mounts(project)
    assert [mount.target for mount in mounts] == [
        CONTAINER_OPENCODE_DATA_DIR,
        CONTAINER_OPENCODE_STATE_DIR,
    ]
    assert all(mount.mode == "rw" for mount in mounts)
    for mount in mounts:
        assert mount.source.is_dir()
        assert stat.S_IMODE(mount.source.stat().st_mode) == 0o700


def test_opencode_state_mounts_isolated_per_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    assert opencode_state_mounts(first)[0].source != opencode_state_mounts(second)[0].source


def test_opencode_state_mounts_stable_for_same_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    project = tmp_path / "proj"
    project.mkdir()
    assert opencode_state_mounts(project) == opencode_state_mounts(project)


def test_project_state_dir_is_private(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = project_state_dir(tmp_path)
    assert root.is_dir()
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
