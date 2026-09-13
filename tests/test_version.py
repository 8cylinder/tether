from __future__ import annotations

import tomllib
from pathlib import Path

import tether


def test_version_matches_pyproject() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with pyproject.open("rb") as handle:
        data = tomllib.load(handle)
    assert tether.__version__ == data["project"]["version"]
