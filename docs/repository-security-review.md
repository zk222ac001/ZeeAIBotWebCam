# Repository privacy and protection review

**Reviewed:** 2026-10-27  
**Baseline:** `fdb9ecdf411ab30d77d64fbf4237249cdb3f8c30` on `main`  
**Scope:** GitHub repository/branch/ruleset metadata, tracked-file inventory, README, workflow, configuration, authentication helpers and selected web routes. This is not a full source, dependency, secret-history or penetration audit. The live Pi environment was not accessed.

## Observed findings

| Finding | Evidence | Implication / action |
| --- | --- | --- |
| Repository is public | Repository API: `private=false`, `visibility=public` | Anyone can read public repository content; branches are not independently private |
| Main is unprotected | Branch API: `protected=false`; protection disabled | Add protection before relying on CI as a merge gate |
| No repository rulesets returned | Rulesets API returned `[]` | No rulesets were visible at review time |
| CI exists | `.github/workflows/ci.yml`: workflow `CI`, job `test`, Ruff and pytest on PRs/main pushes | CI runs are not currently required for merging by observed protection settings |
| Pi authentication defaults are off | `config.pi.yaml`: both access gates false, web host `0.0.0.0` | Without overrides/network restrictions, reachable clients can access media and request control |
| Some status routes lack authentication | `web/app.py`: health and operational routes | Health exposes room observations even when media-route authentication is enabled |
| Tracked media needs review | `imx500_detection.264`, 3,840,160 bytes | Contents/consent unknown; review privately before deciding whether to remove it |
| Ignore rules are partial safeguards | `.env`, local certificates and a diagnostics path are ignored | Ignore rules neither scan secrets nor remove already tracked files |

The repository API reported administrator permission for the connected account, but the available connector exposes no administration write operation for protection or visibility. **No GitHub protection, visibility or security setting was changed by this review.**

## Recommended main-branch protection

In [repository branch settings](https://github.com/zk222ac001/ZeeAIBotWebCam/settings/branches), add a protection rule for `main`:

1. Require changes through pull requests.
2. Require the existing CI test check before merging. Select its exact name from an actual successful run; the YAML job ID is `test`.
3. Require branches to be up to date and review conversations resolved.
4. Keep force pushes and branch deletion disallowed.
5. Apply protection to administrators / disable bypass where appropriate.
6. Require one approving review only once another trusted reviewer is available. A sole maintainer cannot approve their own pull request.

Verify the saved rule in GitHub and re-read branch metadata. These are recommended settings, not controls activated by adding this document.

Reference: [GitHub protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).

## Visibility and privacy

A public repository may be appropriate for this educational project. A private repository restricts source access but does not secure a running robot, and cannot retract existing public copies. Do not change visibility without deciding the intended audience and checking feature availability for the account plan.

Review the tracked media privately. If it contains material that should not have been public, decide on removal and history remediation separately; deleting only the current file leaves historical versions available.

## Remaining security settings to verify

The review did not establish the current state of secret scanning, push protection, dependency alerts or private vulnerability reporting. Inspect repository security settings and enable applicable controls. Do not assume that absence from this report means disabled.

Enable [private vulnerability reporting](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository) so the route described in [SECURITY.md](../SECURITY.md) is available.

For the running robot, confirm local token overrides and restricted HTTPS access using [Studio deployment](studio-deployment.md). Prioritize reducing unauthenticated health data or restricting those routes at the network/gateway layer. This documentation update does not alter runtime access behavior.
