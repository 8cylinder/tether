# tether

Run AI coding harnesses inside a disposable Docker container with full
permissions, so an agent can do anything it wants inside `/workdir` without
being able to damage your host outside the mounted project directory.

[![CI](https://github.com/8cylinder/tether/actions/workflows/ci.yml/badge.svg)](
    https://github.com/8cylinder/tether/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-online-blue.svg)](
    https://8cylinder.github.io/tether/)
[![License: GPL-2.0-only](https://img.shields.io/badge/license-GPL--2.0--only-blue.svg)](
    https://github.com/8cylinder/tether/blob/main/LICENSE)

Source: <https://github.com/8cylinder/tether>

Documentation: <https://8cylinder.github.io/tether/>

## Supported harnesses

| name          | command                        | description            |
| ------------- | ------------------------------ | ---------------------- |
| `opencode`    | `opencode --standalone --auto` | OpenCode               |
| `claude`      | `claude`                       | Anthropic Claude Code  |
| `antigravity` | `agy`                          | Google Antigravity     |

## Requirements

- Docker Engine or Docker Desktop with a running daemon.
- Python 3.11 or newer for development and installing from source.
- bash 4.4 or newer for shell completions.
- bash-completion 2.18 or newer for automatic completion loading.
- Linux or macOS. On Windows, use WSL2.

## Installation

From PyPI, when published:

```bash
uv tool install tether
```

From source:

```bash
git clone https://github.com/8cylinder/tether.git
cd tether
make sync
make install
```

`make install` installs the `tether` command, bash completions, and the man
page. It writes to user-level XDG directories and does not require `sudo`.
`uv tool install --editable --force .` alone installs only the command.

## Quick start

```bash
cd /path/to/project
tether run
```

```bash
tether shell --workdir=/path/to/project
```

```bash
tether info
```

## Command reference

With no subcommand, `tether` is equivalent to `tether run`. Root options must
appear before the subcommand.

| Command | Description |
| --- | --- |
| `tether run [--agent NAME] [--workdir DIR]` | Start a container and run a harness. `--agent` is `opencode`, `claude`, or `antigravity` and defaults to the `default` value in the config file. `--workdir` defaults to the current directory. |
| `tether build [--update-software]` | Build or rebuild the container image. `--update-software` bypasses the build cache and pulls the latest base image and tools. |
| `tether shell [--workdir DIR]` | Open an interactive bash shell in the container at `/workdir`. |
| `tether info` | Show the config path, default harness, Docker and image status, harness mounts, and bundled tools. |
| `tether clean` | Force-remove the tether image. |

### Global options

| Option | Description |
| --- | --- |
| `-h`, `--help` | Show help for the root command or any subcommand. |
| `--version` | Print `tether, version X.Y.Z` and exit. |
| `--config` | Print the absolute config file path and exit. |
| `--completions` | Write the bash completion script and exit. The path is printed to stdout; instructions and warnings go to stderr. |
| `--color [auto\|always\|never]` | Control colored output. Defaults to `auto`. |

`--color=auto` respects `NO_COLOR`, `FORCE_COLOR`, `TERM=dumb`, and whether the
destination is a terminal. `--color=always` forces color; `--color=never`
disables all ANSI styling.

Run `tether --help` or `man tether` for the full option list.

## Configuration

tether reads `config.toml` from the platform's user config directory
(`~/.config/tether/config.toml` on Linux and
`~/Library/Application Support/tether/config.toml` on macOS). Run
`tether --config` to print the exact path. A missing file uses built-in
defaults and is created with mode `0600` on the first command that needs it.

```toml
default = "opencode"

[opencode]
args = ["--auto"]
mount = [
    "~/.config/opencode",
    "~/.local/share/opencode",
    "~/.local/state/opencode",
    "~/.cache/opencode",
]

[claude]
mount = [
    "~/.claude",
    "~/.claude.json",
    "~/.config/claude",
]

[antigravity]
mount = [
    "~/.gemini/antigravity-cli",
    "~/.antigravity",
]
```

- `default` selects the harness used by `tether run` when `--agent` is omitted.
- `args` overrides the arguments passed to the harness; omit it to use the
  harness defaults (for example `--auto` for `opencode`). Set it to an empty
  list to pass none.
- `mount` lists host paths bind-mounted into the container so settings, prompts,
  and history carry over between sessions.
- tether always runs `opencode` with `--standalone`, so each container gets a
  private OpenCode server. The default background service is shared through
  `~/.local/state/opencode/service.json`, which containers cannot reach across
  their separate loopback networks.
- `~` and environment variables are expanded.
- Relative paths are resolved against the config file's directory.
- Host paths under `$HOME` are mounted to the same path under the container
  user's home (`/home/tether`), so harnesses find their settings.
- Missing directories are created on first run; missing files are skipped with
  a warning (a file such as `~/.claude.json` appears once the host tool creates
  it).
- Symlinks at the top level of a mounted directory that point outside it are
  mounted too, at the path they resolve to inside the container. Broken links
  are reported and skipped.
- Unknown config keys produce a warning to stderr and are ignored.
- Precedence is command-line option, then config value, then code default.

## Bash completions

```bash
tether --completions
```

The command writes a static completion script to
`$BASH_COMPLETION_USER_DIR/bash-completion/completions/tether.bash` when
`$BASH_COMPLETION_USER_DIR` is set (first non-empty colon-separated entry),
otherwise to `$XDG_DATA_HOME/bash-completion/completions/tether.bash`, and
otherwise to `~/.local/share/bash-completion/completions/tether.bash`. It prints
only the path to stdout and prints the `source` command and any warnings to
stderr.

To enable completions in the current terminal:

```bash
source ~/.local/share/bash-completion/completions/tether.bash
```

The generated script uses bash arrays, `compgen`, `compopt`, and
`complete -o nosort`, so it requires bash 4.4 or newer. tether warns when the
`bash` on `PATH` is older. Automatic loading of `tether.bash` requires
bash-completion 2.18 or newer; older 2.x versions can still source the file
manually.

On macOS the system `/bin/bash` is 3.2 and the default shell is zsh, which is
not covered. Install a newer bash (for example `brew install bash`) and use it
for completion.

## Man page

```bash
man tether
```

`make install` builds the page with Sphinx and installs it to
`$XDG_DATA_HOME/man/man1/tether.1` (or `~/.local/share/man/man1/tether.1`). If
`man` cannot find it, add that directory to `MANPATH`. Installing from PyPI
gives you the command but not the man page unless your package manager installs
data files.

## Documentation website

The published documentation is at <https://8cylinder.github.io/tether/>.

```bash
make docs          # build the HTML site into docs/_build/html
make docs-serve    # serve it with live reload
```

`README.md` remains the manually written GitHub landing page; it is included in
the Sphinx site but not generated from it.

## Development

```bash
make sync          # uv sync --all-groups
make fmt           # ruff format
make lint          # ruff check --fix
make type          # ty check
make test          # pytest with branch coverage
make check         # format check, lint, types, tests, and docs
make build         # build the wheel and sdist into dist/
```

Run one test:

```bash
uv run pytest tests/test_cli.py::test_bare_invocation_runs_default_agent
```

## License

GPL-2.0-only. See
[LICENSE](https://github.com/8cylinder/tether/blob/main/LICENSE).

Copyright (C) 2026 tether contributors

## Contributing and issues

- Repository: <https://github.com/8cylinder/tether>
- Issues: <https://github.com/8cylinder/tether/issues>
- Contributing guide: [CONTRIBUTING.md](https://github.com/8cylinder/tether/blob/main/CONTRIBUTING.md)
- Security policy: [SECURITY.md](https://github.com/8cylinder/tether/blob/main/SECURITY.md)
