# Command reference

## SYNOPSIS

`tether [OPTIONS] COMMAND [ARGS]...`

## DESCRIPTION

Run AI coding harnesses inside a disposable Docker container. With no
subcommand, `tether` is equivalent to `tether run`.

```{click} tether.cli:main
:prog: tether
:nested: full
```

## FILES

`~/.config/tether/config.toml`

The per-user configuration file. On macOS it lives under
`~/Library/Application Support/tether/config.toml`. Run `tether --config` to
print the exact path for the current platform.

`$XDG_DATA_HOME/bash-completion/completions/tether.bash`

The generated bash completion script. When `$XDG_DATA_HOME` is unset it is
written to `~/.local/share/bash-completion/completions/tether.bash`. If
`$BASH_COMPLETION_USER_DIR` is set, its first non-empty colon-separated entry
is used instead.

## ENVIRONMENT

`NO_COLOR`

Disable color when `--color=auto` is in effect.

`FORCE_COLOR`

Force color when `--color=auto` is in effect. `FORCE_COLOR` takes precedence
over `NO_COLOR`.

`TERM`

`TERM=dumb` disables color when `--color=auto` is in effect.

`BASH_COMPLETION_USER_DIR`

The first non-empty colon-separated entry is used as the base directory for the
generated completion script.

`XDG_DATA_HOME`

The base data directory for the generated completion script when
`BASH_COMPLETION_USER_DIR` is not set.

Completion requires bash 4.4 or newer. Automatic loading of the generated
`tether.bash` file requires bash-completion 2.18 or newer, which prefers the
`.bash` suffix. zsh is not supported.

## SEE ALSO

`tether --help`, `tether --version`, and
<https://github.com/8cylinder/tether>.
