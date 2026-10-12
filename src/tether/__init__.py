"""tether - run AI coding harnesses in a disposable Docker container."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("tether")
except PackageNotFoundError:
    __version__ = "0.0.0"
