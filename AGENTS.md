# Agent Instructions

## Staging server access

The staging server can be accessed using `https://app.obstracts.staging.signalscorps.com/`

You can login with your email `codex@dogesec.com`

Deploy staging through the `obstracts_web_deploy` repository using the staging
target. Always deploy the `staging` branch and test the staged application in a
browser before marking work complete.
## Elastic Debug Access

- Kibana URL: `http://157.180.37.56:5601/`
- Account: `codex`
- Access method: Open Kibana in the Codex in-app browser. The user signs in
  when the session is not already authenticated.

Do not store passwords, API keys, tokens, or exported production data in this
repository.

## Behavior Documentation

When implementing non-obvious product behavior, especially filtering,
permissions, data boundaries, or workflow invariants, document the rationale
in the relevant code and cover it with a regression test. Do this as part of
the change so future work preserves the intended behavior.

## Agent Guidance Maintenance

When the user provides a reusable workflow or working pattern, update every
`AGENTS.md` in the DogeSec repositories so the instruction applies consistently
to future work. Do not leave this guidance only in the repository currently
being changed.

## Issue Ownership

Own each reported issue through implementation, a PR with terminal required
checks, staging deployment, and acceptance validation. Only after the staging
checks pass, add the `ready for review` label and comment on the issue tagging
`@himynamesdave` with the verification evidence for human testing.

## Active Delivery Blockers

Treat CI failures, protection-rule errors, and blocked promotions as active
implementation work. Diagnose the exact cause, update the branch or
configuration when authorized, rerun validation, and continue the release
workflow. Do not stop at reporting a blocker or wait for the user when a safe,
available remediation exists; request help only when a required permission or
external action is genuinely unavailable.
## Delivery Workflow

For reported product bugs, use GitHub Issues by default. Reproduce and
diagnose the behavior, add or improve regression coverage (including relevant
permission paths), and link test evidence from the PR.

For release, image publishing, deployment, branch protection, or promotion
work, use the `dogesec-product-deployments` skill and its release baseline.
Application changes promote from a feature branch to `develop`, then
`staging`, then `main`. The agent owns an issue through successful staging
acceptance validation, then applies `ready for review` and comments tagging
`@himynamesdave` with the verification evidence and review request.

Use the `obstracts_web_deploy` repository's staging target for staging
deployments. Do not mark work complete until the `staging` branch is deployed
and the change is verified in a browser against the staging environment.
## Dependency Updates

Treat every Dependabot or other dependency-update PR as unverified until its
real application checks pass. Do not infer safety from a version diff or from a
stale PR. Keep monitoring required checks to their terminal conclusion;
diagnose and fix any failure before proceeding. Recreate stale updates from
`develop`, then promote only passing updates through `staging`, deploy them,
and complete staging acceptance validation before handing them to the user for
review.

## PR Completion

For every PR, actively monitor required checks until they reach a terminal
result. Do not merge, promote, deploy, or report a PR as tested while any
required check is pending. If a check fails, inspect the logs, fix or document
the root cause, and rerun the checks before continuing.
