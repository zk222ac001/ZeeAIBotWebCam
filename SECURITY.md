# Security

## Project status

ZeeAIBotWebCam is a supervised research prototype. There is no declared long-term security support policy or response-time guarantee. Reports should identify the affected commit and configuration; test fixes against the current main branch.

## Report a vulnerability privately

Use the repository's [Security advisories page](https://github.com/zk222ac001/ZeeAIBotWebCam/security/advisories) and **Report a vulnerability** if that option is available.

Private vulnerability reporting has not been verified as enabled. If the button is absent, ask the maintainer to enable a private reporting channel without posting exploit details, credentials, classroom media or personal data in an issue. No private contact address is designated here.

Include the affected commit, relevant configuration with secrets removed, expected/observed behavior and safe reproduction steps using mock hardware. Do not reproduce an issue through live robot motion or unauthorized media access.

## Deployment security

- Follow [Studio deployment](docs/studio-deployment.md) to configure separate conference and control tokens.
- Restrict access to the whole application and use HTTPS.
- Keep credentials outside version control and rotate them after suspected exposure.
- Review [privacy limitations](docs/privacy.md), including unauthenticated operational endpoints.
- Treat branch protection and repository visibility as separate controls from robot authentication.

The [repository security review](docs/repository-security-review.md) records observed settings and outstanding owner actions. This document does not itself enable any GitHub security feature.
