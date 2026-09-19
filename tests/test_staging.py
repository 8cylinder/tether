from __future__ import annotations

import stat

from tether.staging import READ_ONLY_MODE, READ_WRITE_MODE, stage


def _mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_stage_text_content_and_modes() -> None:
    staged = stage("hello\n", mode=READ_ONLY_MODE, suffix=".txt")
    try:
        assert staged.path.read_text(encoding="utf-8") == "hello\n"
        assert _mode(staged.path) == READ_ONLY_MODE
        assert _mode(staged.path.parent) == 0o700
        assert staged.path.name.endswith(".txt")
    finally:
        staged.cleanup()


def test_stage_bytes_content() -> None:
    staged = stage(b"\x00\x01", mode=READ_WRITE_MODE)
    try:
        assert staged.path.read_bytes() == b"\x00\x01"
        assert _mode(staged.path) == READ_WRITE_MODE
    finally:
        staged.cleanup()


def test_stage_cleanup_removes_directory() -> None:
    staged = stage("secret", mode=READ_ONLY_MODE)
    directory = staged.path.parent
    assert directory.exists()
    staged.cleanup()
    assert not directory.exists()
    staged.cleanup()


def test_staged_files_are_isolated() -> None:
    first = stage("a", mode=READ_ONLY_MODE)
    second = stage("b", mode=READ_ONLY_MODE)
    try:
        assert first.path.parent != second.path.parent
    finally:
        first.cleanup()
        second.cleanup()
