# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub's security advisory
feature:

<https://github.com/8cylinder/tether/security/advisories/new>

Do not open a public issue for a vulnerability. Include the affected version,
reproduction steps, and any relevant logs with secrets removed.

## Scope

tether runs containers with access to the mounted project directory. Treat any
behavior that lets a container escape its intended mounts, overwrite host files
outside `/workdir`, or leak host credentials as a security issue.
