# Design Flaws

## Harden

### `_filter_claude_settings` assumes settings.json is a JSON object
`mounts.py:120-129` only catches `OSError`/`JSONDecodeError`. Valid JSON that is not an object (`[]`, `"x"`, `42`) reaches `data.pop(key, None)` and raises (`TypeError` for a list, `AttributeError` for a string), aborting every `tether run --agent claude`. Guard with `isinstance(data, dict)` before mutating.

### `_print_expiry` can raise on naive timestamps
`cli.py:567` subtracts `datetime.now(UTC)` from `creds.expiration`. `auth.py:176` leaves the parsed value naive when AWS omits the `Z`/offset, so the subtraction raises `TypeError`. Normalize to UTC (or treat a naive value as UTC) before comparing.

### Leading-dash image names interpreted as Docker flags
`config.image` is interpolated into Docker argv as a list, so there is no shell injection, but a name like `--help` is still parsed as a flag. Relevant sites: `docker.py:128` (`docker build --tag`), `docker.py:189` (`docker run` image position), and `docker.py:273` (`docker image rm`). Add a leading-dash check or a `--` separator.

## Documentation drift

### README no longer matches the opencode launch
`README.md:8`, `:21`, and `:201` claim `opencode --auto` runs with permissive flags. `AGENTS` now launches `opencode` with no flag (`agents.py:26-29`) and `_launch` injects `OPENCODE_CONFIG_CONTENT` with `"edit": "ask"` / `"bash": "allow"` (`cli.py:430-440`). Edits now require approval, contradicting the "permission prompts can be disabled" premise.

### README says macOS Bedrock credentials are env vars
`README.md:234` and `:263-264` say the STS tokens are injected as environment variables. `aws_credential_env` (`auth.py:220-230`) deliberately *excludes* the credential keys, and `_launch` mounts them as a staged file at `CONTAINER_AWS_CREDENTIALS` (`cli.py:400-402`). Only `AWS_REGION`/`AWS_DEFAULT_REGION`/`AWS_PAGER` are env vars.

### README claims the image is rebuilt for each new release
`README.md:88-91` says resolving latest versions means "the image is rebuilt whenever a new release is out". Both `build_image` (`docker.py:124-125`) and the `build` command (`cli.py:168-170`) early-return when the image already exists unless `--force`, so new releases are only picked up with `tether build --force` (or after removing the image).

## Acceptable as-is

### env-file permissions rely on `mkstemp` internals
`auth.py:68` — `mkstemp` creates mode 0600 before umask on Linux/macOS, but this is implicit. The test at `test_auth.py:26` verifies it, which catches regressions. This is fine: the env-file is read by the Docker CLI on the host, not by the container.

### `run_container` is untestable in isolation
`docker.py:194` — `subprocess.run` with no stdin/stdout/timeout. Correct for interactive use, but means any test that calls it launches Docker. Command-building is already split out, which is the important part to test.

### Dead `None` paths in `build_run_command`
`docker.py:185-188` — `RunConfig` defaults `memory`/`cpus` to `None`, but in real usage `Resources` always populates them with `"4g"`/`"2"`. The `None` guards are dead code that gives a false sense of flexibility. Harmless — leaving the guards is more defensive than removing them.

## Resolved

### Extra mounts can shadow the read-only `.git` overlay
`_check_mount_safety` (`mounts.py:67-77`) now validates the requested target, normalizes it with `posixpath.normpath`, rejects anything at or under `WORKSPACE`, and checks the target against `_DENIED_MOUNT_TARGETS`. Covered by new cases in `test_mounts.py`.

### `_container_name` can emit invalid Docker names
`_container_name` (`cli.py:580-585`) slugifies the project basename to `[A-Za-z0-9_.-]` (falling back to `project` when empty) before composing the name. Covered by `test_cli.py`.

### Unhandled `DockerError` crashes `run`/`refresh` when Docker is unavailable
`_launch` suppresses `DockerError` from `container_running` (`cli.py:404-408`) and `refresh` turns `list_tether_containers` failures into a friendly error (`cli.py:298-303`). Covered by `test_cli.py`.

### Dockerfile version pins with no override mechanism
Resolved by `resolve_agent_build_args` (`docker.py:59-66`), which fetches the latest npm versions and is passed as `--build-arg` by both `tether build` and the automatic build (`cli.py:172-175`, `516-519`). The Dockerfile `ARG`s are now documented fallbacks.

### macOS `--user` / uid mismatch (was: silently skipped, changing security posture)
Files bind-mounted from the host are now staged by `tether.staging`: each lives in a mode-0700 private directory (hidden from other host users) with an explicit mode that the container can use whichever uid it runs as — `0644` for read-only mounts (`mounts.py:129`, `:157`) and `0666` for the refresh-writable AWS credentials file (`auth.py:259-266`). The container `HOME` is also made world-writable with the sticky bit in the Dockerfile so `--user <host-uid>` can create `$HOME/.config`, `$HOME/.cache`, etc. This removes the uid dependency on both the read (auth/config) and write (HOME) sides; macOS Bedrock auth still resolves the same `/tmp/tether-home/.aws/credentials` path. Covered by `test_staging.py`, `test_aws_credentials.py`, and `test_mounts.py`.
