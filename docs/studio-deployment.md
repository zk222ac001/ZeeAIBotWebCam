# ZeeAI Studio: interface and private deployment

The Studio interface is a supervised preview of this Raspberry Pi application.
The visual redesign does not promote the robot to a final production release or
enable autonomous chassis movement. Review `/readiness` for the current device's
actual blockers.

## Interface

| Page | Purpose |
| --- | --- |
| `/` or `/operator` | Read-only room overview, camera preview, voltage and service status |
| `/conference` | WebRTC video and audio, with an explicit browser-microphone switch |
| `/api/pan-tilt/ui` | Bounded center/hold and following controls, with a tracking guide |
| `/api/control/ui` | Deliberate leased manual control, STOP, emergency stop and reset |
| `/readiness` | Live release checks, autonomy blockers and downloadable anonymous report |

Pages share responsive navigation, local CSS, local JavaScript, accessible labels,
keyboard focus states and an access-settings dialog. No external fonts or CDN
scripts are needed. Templates and static assets are included in the Python wheel;
there is no Node build or second frontend service to operate.

Page load never acquires a control lease, resumes camera following, or arms the
chassis. The Pi still starts with center hold and unarmed plan-only autonomy.
The overview and live-session pages send no movement commands.

The camera guide uses the configured tracking dead zones and selected body-box
center. Images and markers refresh separately. A successful servo submission is
not position feedback. Keep the existing bounds until travel is physically
measured. Opposite-side framing accuracy, acoustic echo cancellation and the full
classroom pilot are still pending acceptance.

## Recommended free starting point

Keep the Python application on the existing Pi, where it can access the camera,
microphone and controller. Private use on the local network adds no hosting fee.
For personal remote testing, consider Pi hosting plus Tailscale private access.
Its free Personal tier is for non-commercial personal use; check eligibility for
an institutional classroom deployment against the current
[Tailscale pricing](https://tailscale.com/pricing) (reviewed 2026-10-25).

A static website deployment alone cannot run this application's Pi hardware
drivers. A public frontend would also need a securely reachable backend and
separate WebRTC connectivity validation. This update does not publish camera or
robot access to the internet.

## Activate this checkout on the Pi

Use the existing service; do not start another hardware instance:

```bash
cd ~/ZeeAIBotWebCam
sudo systemctl restart zee-robot.service
systemctl status zee-robot.service --no-pager -l
```

The root-managed service requires administrator authentication. Enter the
password only in the terminal. Wait for restart to complete before refreshing
the browser. Through the existing VS Code port forward, open:

```text
https://localhost:8000/
```

The displayed device state comes from live APIs. A mock test server explicitly
identifies itself as a simulated device and never supplies invented live video.

## Access tokens before remote sharing

The setup helper prepares separate random tokens and enables both access gates.
It preserves other environment settings, reuses valid existing tokens by default,
and writes the environment and any backup with mode 0600. It never displays the
tokens or restarts the service. To apply it from the checkout:

```bash
sudo .venv/bin/python scripts/setup_studio_access.py --apply
sudoedit /etc/zee-robot/zee-robot.env
```

Copy the conference and control token values locally from that file, then restart
the service and enter the values through the Studio shield button. No credentials
need to be pasted into chat. The helper defaults to a dry run without `--apply`;
`--rotate` explicitly replaces both existing tokens. Existing multiline token
settings require manual review rather than an automatic rewrite.

Alternatively, configure separate long random secrets manually in the same
root-only environment file:

```text
CONFERENCE_AUTH_REQUIRED=true
CONFERENCE_ACCESS_TOKEN=<your-distinct-long-random-conference-secret>
CONTROL_AUTH_REQUIRED=true
CONTROL_ACCESS_TOKEN=<your-distinct-long-random-control-secret>
```

Replace these manual placeholders locally. Keep secrets out of Git, screenshots, chat,
URLs and command arguments. Restart the service after changing this file. Use
the shield button in Studio to enter the relevant token. Tokens remain in page
memory by default. The optional remember setting uses this browser tab's
session storage, and Clear tokens removes it.

The conference gate also protects camera frames and camera/audio/tracking
observations. Camera mode changes and control-lease acquisition use the separate
control token. Normal motion, heartbeat and reset additionally require a valid
control lease. Emergency stop remains available without obtaining a lease.

`/api/conference/client-config` supplies configured ICE settings to an authorized
browser. If TURN credentials are configured, they are intentionally available to
authorized conference clients, never embedded into the HTML or readiness report.
Use appropriately scoped/expiring relay credentials for an institutional release.

For command-line microphone calibration, supply `CONFERENCE_ACCESS_TOKEN` in the
local process environment when authentication is enabled. The pilot helper also
supports this token. Do not put it on a command line or print it into a report.

## Optional private HTTPS through Tailscale

This requires your account and a Tailscale client on both the Pi and the viewing
computer. Install and sign in using the official
[Tailscale setup instructions](https://tailscale.com/docs/install). Limit access
to the people and devices you authorize.

After the Pi service is healthy, the documented Serve pattern for this existing
self-signed loopback HTTPS backend is:

```bash
tailscale serve --bg https+insecure://localhost:8000
tailscale serve status
```

Open the actual HTTPS URL returned by Serve from an authorized device. The
`https+insecure` target applies only to the local proxy connection to the Pi's
self-signed certificate; the browser-facing Serve connection uses provisioned
HTTPS. See [the Serve command documentation](https://tailscale.com/docs/reference/tailscale-cli/serve).
This recipe uses private Serve, not public Funnel. No account, network install,
remote-sharing rule or public deployment is created by this code update.

Serve makes the web interface reachable. WebRTC audio/video has its own media
connectivity, so test from another network with both devices on the private
network. Configure and validate STUN/TURN if the target network needs it; loading
the page alone does not prove media connectivity.

## Before calling the release final

Run `.venv/bin/python scripts/production_readiness.py` and review `/readiness`.
Current pending work includes access-token configuration, acoustic echo and
double-talk acceptance, the complete supervised classroom pilot and deliberate
production promotion. Keep `APPLICATION_ENVIRONMENT` unchanged until that work
has actually passed. Do not set validation flags to make the display green.

Autonomous navigation and docking are not implemented. Independent controller
inhibition/timeout and physical stop behavior still need validation before
unattended mobility. These remain separate from professional interface design.

## Verification

Run `ruff check src tests` and `pytest`. Browser verification should use a
separate mock process on a different loopback port. Never point automated
movement/control tests at the live Pi service. Source files live under
`src/robotic_classroom/web/templates` and `src/robotic_classroom/web/static`.
