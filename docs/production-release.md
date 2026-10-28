# ZeeAI Studio production release workflow

This release targets the existing Raspberry Pi classroom telepresence setup,
with an operator present and chassis autonomy remaining plan-only. It includes
packaged software, deployment checks, integrity verification and rollback steps.
It does not implement unattended navigation or certify physical acceptance.

## Build and verify a release candidate

From a reviewed checkout with the development and WebRTC dependencies installed:

```bash
.venv/bin/python scripts/build_release.py
```

The builder snapshots allowlisted source files, builds a wheel without downloading
dependencies, records the installed runtime/WebRTC dependency versions, and writes
`dist/zeeai-studio-VERSION-DIGEST.tar.gz`. The digest identifies source,
dependencies, target Python/platform and recorded device SDK drivers. It records
uncommitted changes explicitly; commit and review the source before publishing.

The bundle includes source, deployment scripts, guides, a wheel, constraints,
`release-manifest.json` and `SHA256SUMS`. It excludes local `.env`, certificates,
logs, recordings and vendor checkout. Configured YAML credentials cause the build
to fail. Review source and documentation before sharing; this is not a secret
history scan. Checksums detect changes but do not authenticate a publisher.

Extract into a new release directory, preserving the previous deployment:

```bash
mkdir -p ~/zeeai-releases
# Replace BUNDLE with the actual generated archive path.
tar -xzf BUNDLE -C ~/zeeai-releases
cd ~/zeeai-releases/zeeai-studio-VERSION-DIGEST
python3 scripts/verify_release.py .
```

Verify before adding local configuration, certificates, SDK or virtual environment.
Constraints describe the build platform's Python dependencies. They are not a
cross-platform lock or a snapshot of Raspberry Pi OS packages. A bundle built on
CI without device SDK fingerprints remains a generic software candidate.

## Prepare a separate installation

The Pi must already have its OS camera, USB, serial and audio packages installed;
use the existing hardware preparation guides for a new device. On a fresh release:

```bash
./scripts/install_release.sh
```

This verifies the bundle and installs its wheel plus WebRTC dependencies using
its runtime constraints in a new `.venv` with OS package access. It refuses to
replace an existing environment and never starts or installs a robot service.

Privately copy the existing Pi's `vendor/TurboPi` SDK and `.local-certs` into the
new release directory. Preserve private-key mode 0600 and the existing local CA.
The deployment check compares the three runtime SDK driver hashes against the
release manifest. Review local SDK modifications; the builder records their
presence but does not redistribute vendor code. Certificate trust must also be
installed on each approved viewing device.

`config.pi.yaml` contains the original Pi's calibration. It is not acceptance
evidence for another robot. Preserve or remeasure device calibration and observe
physical limits before enabling execution on different hardware.

## Prepare managed access and run preflight

After inspecting the configuration, install the new unit without starting it:

```bash
./scripts/install_systemd_service.sh
./scripts/service_preflight.sh
```

The installer prepares distinct managed conference/control tokens, preserves valid
existing tokens and unrelated environment values, and saves the previous unit
when its contents change. It enables boot startup but does not restart the current
process without `--start`. The root-managed environment is authoritative;
manual-launch `.env` settings are ignored under systemd.

`service_preflight.sh` needs local administrator authentication to load the managed
environment through a short-lived systemd check. It runs as the normal Pi account
and never sources the environment as shell code, prints secrets, touches hardware,
resets a stop or restarts the robot. It checks configuration, installed modules,
model/SDK files, TLS trust/localhost identity, certificate/key match and key permissions.

Use `./scripts/service_preflight.sh --production` after acceptance and production
promotion. Passing preflight is a configuration check, not observed media quality.

## Supervised activation and acceptance

An operator must inspect the stationary robot and resolve any emergency-stop
condition before a deliberate restart. A restart must not substitute for that
inspection. Then activate the prepared unit:

```bash
sudo systemctl restart zee-robot.service
systemctl status zee-robot.service --no-pager -l
.venv/bin/python scripts/service_healthcheck.py
```

Keep the application in preview until all of these have been observed:

- Moving video, both audio directions and reconnection work on the intended network.
- Camera follows the actual speaker within physically inspected servo/cable limits.
- Remote-only speech and overlapping local/remote speech remain intelligible without
  strong returning echo or loud feedback; software counters alone are insufficient.
- The complete 600-second pilot and all eight human observations have been reviewed.
- The chassis remains stationary; stop and watchdog behavior have appropriate physical evidence.

Use [stationary validation](stationary-classroom-validation.md) and
[the acceptance/promotion sequence](phase-16-production-readiness.md). Only after
successful observation record acceptance flags and promote the managed application
environment to production. Production startup refuses disabled/shared credentials
or missing HTTPS configuration. Required environment values must be present before
restart; validation errors omit input configuration from their displayed text.

The final release check is:

```bash
./scripts/service_preflight.sh --production
.venv/bin/python scripts/production_readiness.py
```

Both must pass, and a post-restart real call must still work. Readiness does not
arm the robot. Room navigation and docking remain unavailable.

## Rollback and support evidence

Keep the previous directory, its virtual environment, original device configuration,
local certificates and the saved unit. If activation fails, an operator should keep
the robot stationary, restore the saved unit to
`/etc/systemd/system/zee-robot.service`, run `sudo systemctl daemon-reload`, and
restart under supervision. Do not erase the managed credential file during rollback;
if credentials were rotated, update the authorized browsers locally.

Review `journalctl -u zee-robot.service --since '10 minutes ago'` locally. Collect the
release ID, readiness report and anonymous pilot findings for troubleshooting.
Keep raw classroom media, private keys, tokens and unreviewed logs out of support
reports. A known working release and observed acceptance are the rollback baseline;
a checksum match alone is insufficient.
