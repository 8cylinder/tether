# Contributing

## Development setup

```bash
git clone https://github.com/8cylinder/tether.git
cd tether
make sync
```

Run the checks before opening a pull request:

```bash
make check
```

`make check` runs formatting, linting, type checking, tests with branch
coverage, and the Sphinx documentation build. Use `make fmt` and `make lint`
when you want the tools to apply fixes.

## Pull requests

- Keep changes focused and include tests for new behavior.
- Update `README.md`, `docs/`, and `CHANGELOG.md` when behavior changes.
- Do not commit generated output such as `dist/`, `docs/_build/`, or caches.
- By contributing, you agree that your changes are licensed under
  GPL-2.0-only.
