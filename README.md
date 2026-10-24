# tether

Run AI coding harnesses inside a disposable Docker container with full
permissions, so an agent can do anything it wants inside `/workdir` without
being able to damage your host outside the mounted project directory.

Source: <https://github.com/8cylinder/tether>

Supported harnesses:

| name          | command             | description            |
| ------------- | ------------------- | ---------------------- |
| `opencode`    | `opencode --auto`   | OpenCode               |
| `claude`      | `claude`            | Anthropic Claude Code  |
| `antigravity` | `agy`               | Google Antigravity     |

## Requirements

- Docker Engine (or Docker Desktop) with a running daemon
- [`uv`](https://docs.astral.sh/uv/) for development

## Install

```bash
git clone https://github.com/8cylinder/tether.git
cd tether
make sync           # uv sync
uv run tether --help
make install        # optional: install tether as an editable uv tool
```

## Usage

```bash
tether                                    # same as tether run
tether --help                             # same as tether -h
tether --config                           # print the config file path
tether --completions                      # write bash completions and show how to load them
tether build                              # build/rebuild the container image
tether build --update-software            # rebuild and upgrade all installed software
tether run                                # run the default harness
tether run --agent=opencode               # run a specific harness
tether run --workdir=/path/to/project     # mount a different directory at /workdir
tether shell                              # interactive shell at /workdir
tether shell --workdir=/path/to/project   # shell with a different directory mounted
tether info                               # configuration and status
tether clean                              # remove the built image
```

`tether` with no subcommand behaves like `tether run`, including forwarded
options (`tether --agent claude`). `tether run` and `tether shell` mount the
current directory at `/workdir` in a fresh, disposable container
(`docker run --rm`).

### Commands and options

- With no subcommand, `tether` is equivalent to `tether run`.
- `--completions` — write a bash completion script to
  `$XDG_DATA_HOME/bash-completion/completions/tether` (or
  `~/.local/share/bash-completion/completions/tether`) and print the path plus a
  command that loads it in the current terminal.
- `--config` — print the config file path and exit.
- `build [--update-software]` — build or rebuild the container image.
  `--update-software` bypasses the build cache and pulls the latest base image
  and tools.
- `run [--agent NAME] [--workdir DIR]` — start a container and run a harness.
  `--agent` is one of `opencode`, `claude`, or `antigravity` and defaults to
  `default` in the config file. `--workdir` defaults to the current directory.
- `shell [--workdir DIR]` — open an interactive bash shell in the container.
- `info` — show the config path, default harness, Docker and image status,
  harness mounts, and bundled tools.
- `clean` — force-remove the tether image.
- `-h`, `--help` — show help for the top-level command or any subcommand.

## Shell completion

`tether --completions` writes a bash completion script and prints the path and a
`source` command for the current terminal. The file goes to
`$XDG_DATA_HOME/bash-completion/completions/tether`, falling back to
`~/.local/share/bash-completion/completions/tether` when `$XDG_DATA_HOME` is
unset.

The generated script uses `compopt` and `complete -o nosort`, so it requires
bash 4.4 or newer; tether warns when the `bash` on `PATH` is older. Automatic
loading of the file requires bash-completion 2.x. The unsuffixed `tether`
filename is what bash-completion looks for, though versions 2.18 and newer
prefer `tether.bash`.

On macOS the system `/bin/bash` is 3.2 and the default shell is zsh, which is
not covered. Install a newer bash (for example `brew install bash`) and use it
for completion.

## Configuration

tether reads `config.toml` from the platform's user config directory
(`~/.config/tether/config.toml` on Linux and
`~/Library/Application Support/tether/config.toml` on macOS) and creates it on
first run. Run
`tether --config` to print the exact path. `default` selects the harness used by
`tether run` when `--agent` is omitted. Each harness section lists the host
paths that are bind-mounted into the container so that settings, prompts and
history carry over between sessions, and the `args` passed to the harness when
it starts.

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

- `args` overrides the arguments passed to the harness; omit it to use the
  harness defaults (for example `--auto` for `opencode`). Set it to an empty
  list to pass none.
- `~` and environment variables are expanded.
- Host paths under `$HOME` are mounted to the same path under the container
  user's home (`/home/tether`), so the harnesses find their settings.
- Missing directories are created on first run; missing files are skipped with a
  warning (a file such as `~/.claude.json` will appear once the host tool
  creates it).
- Symlinks at the top level of a mounted directory that point outside it (for
  example an `opencode.jsonc` linked to `~/dotfiles/opencode.jsonc`) are mounted
  too, at the path they resolve to inside the container, so they still resolve.
  Broken links are reported and skipped.

## Development

```bash
make sync          # uv sync
make fmt           # ruff format
make lint          # ruff check --fix
make type          # ty check
make test          # pytest
make check         # format check + lint + type + test
```

`make format`, `make format-check`, and `make typecheck` remain as aliases.

## Notes

- The harnesses are installed inside the image at build time; only their
  settings are taken from the host. Run `tether build --update-software` to
  bypass the build cache and pull the latest base image and tool versions.
- The image also includes common command-line tools, including [`uv`](https://docs.astral.sh/uv/).
  Run `tether info` to list them.
- The image is built with your host UID/GID so files created in `/workdir` stay
  owned by you.
- OAuth sign-in may not work inside a container without a browser. Prefer
  authenticating on the host and mounting the result, or use API keys via
  environment variables.
