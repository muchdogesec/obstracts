# Maintaining this guidance

## Ownership model

This repository is the canonical cross-product map. Product repositories remain
authoritative for executable behavior and local development rules.

Codex is the accountable maintainer of this repository and the documented
product estate. It performs scheduled reviews, opens and resolves drift work,
and updates consumer snapshots. The user is the final escalation point only
for an unresolved blocker, required new authority/above-threshold spend, or an
unavoidable human-only action.

- A change that alters a documented repository boundary, request/data flow,
  public capability, build command, image/release path, runtime dependency, or
  operational procedure must update this repository in the same change set or
  create a linked documentation follow-up.
- Local `AGENTS.md` files should contain repository-specific rules. Do not copy
  the full product description into every repository.
- Product website content is authoritative for intended public positioning and
  audience; code and deployed schemas are authoritative for actual behavior.
  Reconcile disagreements explicitly.

## Review cadence

- Monthly: compare default branches for every repository in the product and
  shared-component maps; review material changes since `research/baseline.md`.
- On every product release: review the affected product guide and shared
  build/deploy guide before deployment.
- Quarterly: perform an end-to-end architecture review across all five products,
  including public websites, core/backend/frontend/deploy repositories, shared
  package versions, external data generators, OpenCTI connectors, browser
  extensions, backups, and rollback paths.
- Immediately: update guidance after a repository rename, new service,
  replacement dependency, authentication/billing model change, new public
  surface, or production topology change.

For every public API change, inspect the external-consumer matrix and update its
route/schema evidence. Connector and extension compatibility is a release gate,
not a documentation follow-up.

Updating the review date without inspecting the current code is not a review.

## Evidence standard

Every non-obvious statement should be traceable to one or more of:

- current default-branch implementation;
- current Docker/Compose/Nginx or GitHub workflow configuration;
- current public product website positioning;
- current schema/tests;
- a named owner decision recorded in `research/open-questions.md` or an issue.

Prefer stable file/symbol references over copied implementation snippets.
Avoid secrets, customer data, environment values, server addresses, and
credentials.

## Consumer update process

Consumers vendor only `AGENTS.md` and `docs/` under `.agent-guidance/`.

1. Update this canonical repository and validate its internal links/map.
2. Commit and merge the canonical change.
3. For each affected consumer, copy the canonical `AGENTS.md` and complete
   `docs/` tree into `.agent-guidance/`, deleting removed upstream files.
4. Update `.agent-guidance/UPSTREAM.md` to the merged canonical commit.
5. Review the consumer diff and run repository-appropriate documentation or
   agent-bootstrap checks.
6. Merge consumer updates through normal pull requests.

Do not use submodules, symlinks, or runtime downloads: mandatory guidance must
exist in ordinary clones, worktrees, and source archives.

## Handling uncertainty

Use `research/open-questions.md` for questions the code cannot answer, such as
business ownership, intended customer promises, undocumented environments, or
the operational owner of an external data publication pipeline. State what is
known, why it matters, and the smallest owner decision required.

Once answered, move the durable answer into the applicable guide and retain a
short dated decision note. Do not leave resolved decisions only in chat.
