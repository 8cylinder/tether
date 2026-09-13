from __future__ import annotations

from pathlib import Path

import pytest

from tether.config import Mount
from tether.mounts import MountError, build_mounts, has_git, resolve_project


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
