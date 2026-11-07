"""tether - run AI coding harnesses in a disposable Docker container."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("tether")
except PackageNotFoundError as exc:  # pragma: no cover - installation problem
    raise RuntimeError(
        "tether is not installed. Install it with `uv sync` or "
        "`pip install -e .` before running it."
    ) from exc
