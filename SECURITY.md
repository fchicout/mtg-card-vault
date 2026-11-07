# Security policy

## Reporting a vulnerability
Please **do not open a public issue**. Report it privately through GitHub: *Security → Report a vulnerability* ([direct link](https://github.com/fchicout/mtg-card-vault/security/advisories/new)). Include what you found, how to reproduce it and the version or commit. You will get an answer as soon as the maintainer can, and credit if you want it once a fix is released.

## Supported versions
The project is pre-1.0: only the latest `develop` and the latest release receive fixes.

## How the project handles security
The controls (authentication, input validation, scanning in CI, dependency and image policy, nightly rescans, SBOMs) and the exception process are described in [`docs/05-architecture.md`](docs/05-architecture.md) sections 8.1 and 8.2. Accepted findings are listed, with an owner and an expiry date, in [`security/exceptions.yaml`](security/exceptions.yaml); CI fails when one expires.
