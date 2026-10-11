# TETHER.plan.md

Plan for hardening `tether` against collisions with the older, unrelated `tether`
app that uses the same command name, config path, and Docker image tag.

## Goal

Let both apps coexist on one host without overwriting each other's
configuration or container image, while keeping current defaults unchanged.

## Collision points being addressed

| Resource | Shared value | Risk |
| --- | --- | --- |
| Executable | `tether` | PATH decides which app runs |
| Config file | `~/.config/tether/config.toml` | Conflicting schemas; either app may rewrite the other's file |
| Docker image | `tether:latest` | `build` overwrites and `clean` deletes the other app's image |

Container names are **not** a problem: this version is ephemeral
(`docker run --rm`, no `--name`) and `clean` only removes the image.

## Changes

### 1. Configurable config path

- Add a `TETHER_CONFIG` environment variable read by `config.py`.
- Precedence: explicit `--config` option > `TETHER_CONFIG` env > built-in
  `~/.config/tether/config.toml`.
- Keep the current default so existing behavior is unchanged.
- Do not write to the config file if it exists (already the case).

### 2. Configurable image name

- Add a `TETHER_IMAGE` environment variable and an optional `image` key in the
  config file.
- Precedence: explicit `--image` option > `TETHER_IMAGE` env > config `image`
  key > default `tether:latest`.
- `build`, `run`, `shell`, `clean`, and `info` all resolve the image through the
  same helper so they stay consistent.

### 3. CLI surface

- Add a global `--config PATH` option.
- Add a global `--image NAME` option.
- Document both in `README.md` and `--help`.

### 4. Recommended usage for coexistence

Set these in the shell profile to fully separate the two apps:

```bash
export TETHER_CONFIG="$HOME/.config/tether-agent/config.toml"
export TETHER_IMAGE="tether-agent:latest"
```

Or run with flags:

```bash
tether --config ~/.config/tether-agent/config.toml build
tether --config ~/.config/tether-agent/config.toml run
```

## Implementation steps

1. `config.py`: resolve config path from arg/env, add optional `image` key.
2. `util.py` / `docker.py`: resolve image name from arg/env/config.
3. `cli.py`: add global `--config` and `--image` options and thread them through
   `run`, `build`, `shell`, `info`, `clean`.
4. `README.md`: document the isolation variables.
5. Tests:
   - config path from `TETHER_CONFIG` and `--config`
   - image resolution precedence
   - ensure existing config file is never overwritten

## Verification

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

## Non-goals

- Renaming the app or its default image/config (defaults stay `tether`,
  `tether:latest`, `~/.config/tether/config.toml`).
- Migrating or merging the old app's config.
