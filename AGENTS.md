# Agent Instructions

## Elastic Debug Access

- Kibana URL: `http://157.180.37.56:5601/`
- Account: `codex`
- Access method: Open Kibana in the Codex in-app browser. The user signs in
  when the session is not already authenticated.

Do not store passwords, API keys, tokens, or exported production data in this
repository.

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
