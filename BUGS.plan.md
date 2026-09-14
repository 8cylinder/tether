# Design Flaws

## Fix soon

### Extra mounts can escape the safety model
`mounts.py:71-76` accepts extra mounts from config with no validation that the source isn't dangerous (`/`, `/etc`, `~/.ssh`, `~/.aws`, Docker socket). An accidental `source = "/"` with `mode = "rw"` gives the agent full host filesystem access. Add a denylist or warning for mounts outside the project tree.

### macOS `--user` silently skipped, changing security posture
`cli.py:280-281` only passes `--user` on Linux. On macOS the container runs as `node` (uid 1000), so files created by the agent in `/workspace` are owned by uid 1000 on the host — the invoking user can't delete them without `sudo`. Silent behavior difference between platforms, undocumented.

### Error ordering: auth checked before image existence
`cli.py:273-274` — `_launch` runs `collect_env` (which validates passthrough env vars) before `_ensure_image`. A user who hasn't built the image yet gets an auth error instead of "run `tether build` first" if their env vars aren't set. Reorder to check image existence first.

## Clean up

### `AgentSpec.env` is dead code
`agents.py:17` defines `env: dict[str, str]` on `AgentSpec` but no code path reads it. `_launch` in `cli.py` only uses `spec.command`. Either wire it up or remove it.

### `shell` command resolves an agent spec for nothing
`cli.py:200` passes `command=("bash",)` to `_launch`, but `_launch` still calls `get_agent(agent_name)` even though the result is unused for shell.

### Dead `None` paths in `build_run_command`
`docker.py:129-132` — `RunConfig` defaults `memory`/`cpus` to `None`, but in real usage `Resources` always populates them with `"4g"`/`"2"`. The `None` guards in `build_run_command` are dead code that gives a false sense of flexibility.

## Harden

### Leading-dash image names interpreted as Docker flags
`docker.py:74` and `docker.py:108` interpolate `config.image` into Docker commands via list argv (no shell injection), but a name like `--help` would be interpreted as a flag. Add a leading-dash check or `--` separator.

### Dockerfile version pins with no override mechanism
`Dockerfile:3-5` pins agent versions (`CLAUDE_CODE_VERSION`, `OPENCODE_VERSION`, `GEMINI_CLI_VERSION`) baked into source. `build_image` accepts `build_args` but the CLI never passes them. Users must edit source to update. Expose `--build-arg` on the `build` CLI command or read versions from config.

## Acceptable as-is

### env-file permissions rely on `mkstemp` internals
`auth.py:62` — `mkstemp` creates mode 0600 before umask on Linux/macOS, but this is implicit. The test at `test_auth.py:26` verifies it, which catches regressions.

### `run_container` is untestable in isolation
`docker.py:146` — `subprocess.run` with no stdin/stdout/timeout. Correct for interactive use, but means any test that calls it launches Docker. Command-building is already split out, which is the important part to test.
