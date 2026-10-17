# Security

## Local Use Only

The desktop GUI does not start an HTTP server. The optional `--web` mode binds
to loopback only and must not be exposed through port forwarding, reverse
proxies, tunnels, or a public network interface.

Web requests use a per-process token and same-origin/loopback checks. These
protect against unwanted browser requests, not malicious software already
running as your OS user. Network/device output paths are not accepted by the
web API. Do not enter untrusted output paths or share a browser session with
untrusted extensions.

Browser cookies can grant access to your account. Do not commit, upload, log,
or send them in bug reports. This application does not require you to give its
maintainer a password or cookie file. `auto` cookie selection tries available
browser profiles; select no cookies when account access is not needed.

## Reporting

Use the repository's private vulnerability reporting feature if the maintainer
has enabled it. Otherwise request a private reporting channel without posting
secrets, personal URLs, or exploit details publicly. This local project does
not currently advertise a hosted reporting service or guaranteed response time.

Include the app version, operating system and a minimal reproduction with
redacted data. Never include `.env`, browser databases, cookies, downloaded
media, or unredacted authentication errors.

## Release Checks

Run `python scripts/release_check.py` before sharing source. It is a limited
pattern/path check, not a comprehensive secret scanner or security audit.
Review Git history separately. Binary release remains disabled until the
corresponding-source and native dependency review in docs/DISTRIBUTION.md is
completed. A successful build or passing tests is not redistribution approval.
