# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security problem. Report it privately through GitHub:
open the repository's **Security** tab and choose **Report a vulnerability**.

Include what you found, how to reproduce it, and the version (`homer --version` or the release tag).
We aim to reply within 7 days and to agree a disclosure date with you once a fix is ready.

## Scope

In scope: the Homer backend, dashboard, MCP servers, installer and release workflow in this
repository. Of most interest are bypasses of the outbound allowlist (`homer_net`), actions that run
without an approval, session or passphrase weaknesses, and anything that exposes data under
`~/.homer`.

Out of scope: Ollama, Google APIs, the models themselves and other third-party services.

## Supported versions

Only the latest release receives security fixes.
