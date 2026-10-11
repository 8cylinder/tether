from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from tether.config import Config, ConfigError, load_config, resolve_mounts


def test_creates_default_config_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "tether" / "config.toml"
    config = load_config(path)

    assert path.exists()
    assert config.default_agent == "opencode"
    assert config.raw_mounts_for("opencode")


def test_does_not_create_when_disabled(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    load_config(path, create=False)
    assert not path.exists()


def test_parses_custom_mounts(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        'default = "claude"\n[claude]\nmount = ["/tmp/one", "/tmp/two"]\n',
        encoding="utf-8",
    )
    config = load_config(path)

    assert config.default_agent == "claude"
    assert config.raw_mounts_for("claude") == ["/tmp/one", "/tmp/two"]
    assert config.raw_mounts_for("opencode")


def test_accepts_deafault_typo(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('deafault = "antigravity"\n', encoding="utf-8")
    config = load_config(path)
    assert config.default_agent == "antigravity"


def test_unknown_default_falls_back(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('default = "nope"\n', encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        config = load_config(path)
    assert config.default_agent == "opencode"
    assert caught


def test_invalid_mount_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[claude]\nmount = "nope"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_resolve_mounts_maps_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    config_dir = tmp_path / ".config" / "opencode"
    config_dir.mkdir(parents=True)

    config = Config(
        path=tmp_path / "config.toml",
        default_agent="opencode",
        mounts={"opencode": ["~/.config/opencode", "~/.missing-file.json"]},
    )
    mounts, skipped = resolve_mounts(config, "opencode")

    assert mounts == [(str(config_dir), "/home/tether/.config/opencode")]
    assert skipped == [("~/.missing-file.json", "file does not exist")]


def test_resolve_mounts_creates_missing_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    config = Config(
        path=tmp_path / "config.toml",
        default_agent="claude",
        mounts={"claude": ["~/.claude"]},
    )
    mounts, skipped = resolve_mounts(config, "claude")

    assert skipped == []
    assert (tmp_path / ".claude").is_dir()
    assert mounts == [(str(tmp_path / ".claude"), "/home/tether/.claude")]


def test_resolve_mounts_no_create(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    config = Config(
        path=tmp_path / "config.toml",
        default_agent="claude",
        mounts={"claude": ["~/.claude"]},
    )
    mounts, skipped = resolve_mounts(config, "claude", create_missing=False)

    assert mounts == []
    assert skipped == [("~/.claude", "does not exist")]
