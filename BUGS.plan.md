# Design Flaws

## Fix soon

### macOS `--user` silently skipped, changing security posture
`cli.py:393` only passes `--user` on Linux. On macOS the container runs as `node` (uid 1000), so files created by the agent in `/workspace` are owned by uid 1000 on the host — the invoking user can't delete them without `sudo`. Silent behavior difference between platforms, undocumented.

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

### Dead `None` paths in `build_run_command`
`docker.py:129-132` — `RunConfig` defaults `memory`/`cpus` to `None`, but in real usage `Resources` always populates them with `"4g"`/`"2"`. The `None` guards in `build_run_command` are dead code that gives a false sense of flexibility. Harmless — leaving the guards is more defensive than removing them.
