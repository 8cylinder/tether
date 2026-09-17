from __future__ import annotations

from pathlib import Path

import pytest

from tether.config import Mount
from tether.mounts import (
    _TETHER_STATUS_LINE,
    CONTAINER_CLAUDE_DIR,
    CONTAINER_CLAUDE_JSON,
    CONTAINER_CLAUDE_SETTINGS,
    MountError,
    build_mounts,
    claude_config_mounts,
    has_git,
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
    assert mounts[0].mode == "rw"
    assert mounts[1].target == CONTAINER_CLAUDE_SETTINGS
    assert mounts[1].mode == "ro"
    assert mounts[2].source == claude_json
    assert mounts[2].target == CONTAINER_CLAUDE_JSON
    assert mounts[2].mode == "rw"
    assert len(temp_files) == 1
    import json

    filtered = json.loads(temp_files[0].read_text(encoding="utf-8"))
    assert filtered["statusLine"] == _TETHER_STATUS_LINE
    assert filtered["sandbox"] == {"enabled": False}
    assert filtered["permissions"] == {"allow": ["Bash(*)"], "deny": ["Edit", "Write"]}
    assert filtered["autoUpdaterStatus"] == "disabled"
    for f in temp_files:
        f.unlink(missing_ok=True)


def test_claude_config_mounts_dir_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".claude").mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    mounts, temp_files = claude_config_mounts()
    assert len(mounts) == 2
    assert mounts[0].target == CONTAINER_CLAUDE_DIR
    assert mounts[1].target == CONTAINER_CLAUDE_SETTINGS
    assert len(temp_files) == 1
    import json

    filtered = json.loads(temp_files[0].read_text(encoding="utf-8"))
    assert filtered["statusLine"] == _TETHER_STATUS_LINE
    assert filtered["sandbox"] == {"enabled": False}
    assert filtered["permissions"] == {"allow": ["Bash(*)"], "deny": ["Edit", "Write"]}
    assert filtered["autoUpdaterStatus"] == "disabled"
    for f in temp_files:
        f.unlink(missing_ok=True)


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

    filtered = json.loads(temp_files[0].read_text(encoding="utf-8"))
    assert "theme" in filtered
    assert "env" not in filtered
    assert "awsAuthRefresh" not in filtered
    assert filtered["statusLine"] == _TETHER_STATUS_LINE
    assert filtered["sandbox"] == {"enabled": False}
    assert filtered["permissions"] == {"allow": ["Bash(*)"], "deny": ["Edit", "Write"]}
    assert filtered["autoUpdaterStatus"] == "disabled"
    for f in temp_files:
        f.unlink(missing_ok=True)


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

    filtered = json.loads(temp_files[0].read_text(encoding="utf-8"))
    assert filtered["theme"] == "dark"
    assert filtered["model"] == "opus"
    assert filtered["statusLine"] == _TETHER_STATUS_LINE
    assert filtered["sandbox"] == {"enabled": False}
    assert filtered["permissions"] == {"allow": ["Bash(*)"], "deny": ["Edit", "Write"]}
    assert filtered["autoUpdaterStatus"] == "disabled"
    for f in temp_files:
        f.unlink(missing_ok=True)
