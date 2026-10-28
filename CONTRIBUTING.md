# Contributing

Thanks for helping improve classroom telepresence and its documentation.

## Local development

Follow the [mock quick start](README.md#quick-start--no-robot-required). Python 3.11–3.13 is supported by the package metadata; CI currently uses Python 3.11.

Create a focused branch from current main:

```bash
git switch main
git pull --ff-only
git switch -c docs/describe-your-change
```

Before submitting code changes:

```bash
ruff check src tests scripts
pytest -v
```

Run tests with mock hardware in an isolated development environment. Never direct automated tests at the live Pi service. For documentation-only changes, verify relative links, commands against the source and any diagrams.

## Pull requests

Explain the problem, resulting behavior and validation performed. Separate software tests from actual hardware acceptance. Include screenshots only when free of classroom participants, secrets and identifying information.

Keep changes to safety limits, authentication and deployment behavior explicit. Do not set calibration or pilot validation flags merely to bypass a check. Add meaningful tests when changing behavior.

Do not commit local environment files, keys, tokens, raw recordings or unreviewed diagnostics. Use synthetic fixtures where possible. Report vulnerabilities through [SECURITY.md](SECURITY.md), not a public issue containing sensitive details.

## Hardware changes

Describe the hardware, calibration procedure and supervised test conditions. Preserve central safety supervision, stop behavior and mode gates. A unit test pass does not establish physical safety.

## Documentation

Keep the README concise and link detailed procedures from [the documentation index](docs/README.md). Mark historical phase instructions clearly and update current guides when behavior changes.
