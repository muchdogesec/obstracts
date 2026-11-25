# Build, release, and deployment model

This document describes the common production path verified on 2026-11-25 and
the target rollback/recovery controls adopted on that date. Always read the
current workflow and deployment source before operating it.

## Environment model

Production is the only persistent deployed environment. There is no persistent
local, test, or staging deployment. Do not create an always-on non-production
environment merely to mirror production.

Application branches may still use `develop` and `staging` as checked promotion
gates; those branch names do not imply deployed environments or staging image
channels. QA uses unit tests, integration tests, schema tests, frontend builds,
and ephemeral CI service containers. For a change whose risk cannot be reduced
adequately in CI, Codex may create a short-lived isolated validation environment
within the standing cost policy and must remove it after evidence is captured.

## Build and test

- Core and web-backend repositories are Python/Django services. Dependencies
  are installed from `requirements.txt` or `pyproject.toml`; tests use `pytest`.
  Integration/schema tests commonly require PostgreSQL, Redis, ArangoDB, and a
  running core service.
- Frontends are Node/Next.js services. `npm run build` is the production build.
  Test coverage differs by repository: some have Jest, some Playwright suites,
  and some currently only enforce build/lint checks.
- Deployment repositories should validate Compose/Nginx behavior. Vulmatch and
  Cyber Threat Exchange include explicit MCP gateway tests; Obstracts includes
  Nginx tests.
- Shared Python libraries publish releases and are consumed by pinned package
  versions or a versioned private `web_commons` install.

Never substitute another product's commands without checking the local
`AGENTS.md`, README, workflow files, and test configuration.

## Image publication

Merges/pushes to `main` in each core, web-backend, and frontend repository build
and publish a GHCR image tagged for that repository's production service. The
production Compose files currently consume mutable `:main` image tags.

Stixify, Vulmatch, CTI Butler, and Cyber Threat Exchange core repositories also
contain staging/test image workflows. That does not imply the other three
repository layers or deployment wiring have equivalent staging environments;
verify the complete target before claiming a staged release.

## Production deployment

Production deployment is a separate, manually dispatched workflow in each
`*_web_deploy` repository. The workflow connects to the product server and runs
`/etc/deployment/<repo>/start_server.sh`.

The script:

1. pulls the current deployment repository;
2. restarts the host PostgreSQL and ArangoDB containers;
3. waits for them to report running;
4. pulls current product images;
5. stops and recreates the product Compose stack;
6. prunes unused Docker objects.

Because the Compose files use mutable image tags, the deployment commit alone
does not identify the exact core/backend/frontend revisions deployed. Before a
release, record the image digests or source workflow runs and confirm all
required images finished publishing.

## Routing

Nginx in each deployment repository exposes four broad surfaces:

- the frontend and same-origin web API;
- a dedicated public REST API mapped through the web backend to product routes;
- a TAXII 2.1 surface backed by `arango_taxii_server` integration;
- a dedicated MCP surface backed by the product web backend.

Stixify and Cyber Threat Exchange set larger body-size limits for document/STIX
uploads. Do not copy limits or routes between products without checking the
product's expected payloads.

## Current recovery gaps

As of the baseline review:

- backup workflows are manually dispatched rather than scheduled;
- dump scripts retain only the latest three matching archives;
- every product dumps all PostgreSQL databases to R2;
- only Obstracts, Stixify, and Cyber Threat Exchange have ArangoDB dump
  workflows in their deployment repositories;
- Vulmatch and CTI Butler rely on rebuildable published datasets but do not yet
  have a bounded, tested ArangoDB recovery workflow;
- production Compose files consume mutable `:main` images, so a deployment is
  not reproducible from its deployment-repository commit alone;
- restore drills and RTO/RPO evidence are not automated.

Treat these as implementation gaps against the target model below, not as an
acceptable recovery guarantee.

## Target release rollback model

Every production deployment must be reproducible from a release manifest that
records:

- source commit for core, web backend, frontend, deployment, and changed shared
  packages;
- immutable image digest for each deployed container;
- deployment repository commit;
- applied database migrations and required data jobs;
- pre-deployment backup identifiers when state can change;
- the previous verified release manifest.

Production must deploy immutable image digests or immutable `sha-<commit>` tags.
Mutable channel tags may identify the current release but must not be the only
rollback reference. Retain the active release and one proven healthy previous
release until the new release passes post-deployment verification.

Use this rollback order:

1. Stop further writes/jobs that could amplify the fault.
2. If state remains compatible, redeploy the previous release manifest without
   restoring data.
3. If a migration or corrupting job changed state incompatibly, restore into
   new database/container targets from the verified pre-deployment backup.
4. Validate counts, schema, key queries, permissions and product smoke tests
   against the restored targets.
5. Cut over only after validation; retain the failed state for bounded forensic
   analysis until the incident is closed.

Prefer expand/migrate/contract database changes so the previous application
release remains compatible during the rollback window. A destructive or
irreversible migration requires a verified pre-deployment backup and an
explicit restore procedure in the release record.

## Target backup and recovery policy

| State | RPO target | RTO target | Recovery method |
| --- | --- | --- | --- |
| PostgreSQL for every product | 24 hours | 4 hours | Restore verified dump into new PostgreSQL target, validate, then cut over |
| ArangoDB for Obstracts, Stixify, CTX | 24 hours | 8 hours | Restore verified `arangodump` into new Arango target, validate graph/API, then cut over |
| ArangoDB for Vulmatch and CTI Butler | 24 hours | 12 hours restore; 48 hours rebuild fallback | Restore dump first; rebuild from versioned source bundles and rerun processors only if restore is unavailable |
| R2 user uploads/media | 24 hours | 8 hours | Object versioning/replication or verified backup plus metadata reconciliation |
| Redis cache/queues | No durable RPO | 1 hour | Recreate; reconcile in-flight jobs from PostgreSQL and mark/requeue safely |

Run backups daily and before any destructive migration or bulk data job. Retain
at least seven daily, four weekly, and three monthly recovery points. Verify
remote size/checksum after upload, monitor missed/failed runs, and perform a
quarterly isolated restore drill for every product. A backup is not proven until
it has been restored and the product contract validated.

Vulmatch and CTI Butler graph data is derived, but restoration is the primary
recovery method because a full rebuild can be slow and can depend on external
source availability. The rebuild path must use recorded bundle versions,
collection settings, processor versions/modes, and index creation steps so it
produces a reproducible graph.

## Release checklist

1. Identify every changed repository and shared package.
2. Run each repository's required unit, integration, schema, build, and gateway
   checks.
3. Coordinate shared-package versions and consumer pins.
4. Merge in dependency order and wait for every required image to publish.
5. Record source SHAs, image workflow runs/digests, database migration and
   rollback expectations.
6. Run the deployment workflow for the intended environment.
7. Verify frontend, REST, TAXII, MCP, worker/beat, and health-check surfaces that
   the change can affect.
8. Confirm migrations/jobs completed and inspect errors before calling the
   release complete.
9. Preserve the previous healthy release and recovery points until the new
   release satisfies the rollback window and all post-deploy checks.
