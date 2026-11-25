# Cyber Threat Exchange

## Product purpose and users

Cyber Threat Exchange (CTX) is a marketplace and delivery layer for specialist
cyber-threat-intelligence feeds. Producers publish structured STIX 2.1 into
focused feeds; consumers discover and subscribe to the feeds they need and
deliver them onward through the web interface, REST, TAXII, and integrations.

Primary users are CTI producers/researchers and defender teams consuming
specialist intelligence for TIP, SIEM, hunting, enrichment, and automation
workflows.

## Repositories

| Repository | Owns |
| --- | --- |
| `cyberthreatexchange` | Feed model, STIX validation/upload, per-feed graph storage, search, publisher connectors and core REST API |
| `cyberthreatexchange_web_be` | Hosted users/teams/plans, feed subscriptions/access, product proxy API, MCP/TAXII, schemas and sitemaps |
| `cyberthreatexchange_web_fe` | Feed publishing/editing, objects, connectors, subscriptions, jobs, search and consumer/team workflows |
| `cyberthreatexchange_web_deploy` | Production services, upload limits, Nginx routes, MCP gateway, backups and deployment |

## Data path

1. A producer creates a feed and uploads a STIX 2.1 bundle through the API, or
   configures a TAXII 2.1 connector that core polls.
2. Core validates supported standard/custom objects, separates unresolved
   relationships, and writes objects with `stix2arango` in versionless mode to
   feed-specific vertex/edge collections.
3. Core retries relationships after referenced objects arrive, records object
   values for search, and tracks job/connector/feed state in PostgreSQL.
4. The web backend owns hosted feed subscription and team/API-key access and
   exposes browser, REST, MCP, and TAXII surfaces.
5. Scheduled pipelines such as `feeds2stix` convert public sources into STIX and
   publish them into exchange feeds.

## Developer ownership guide

- STIX object/extension schema definitions: `stix2extensions` when custom
  types/properties are shared.
- Public-source-to-STIX mapping and scheduled publication: `feeds2stix` or the
  source-specific producer repository/workflow.
- Bundle validation, feed storage, connector polling, unresolved relationships,
  and core search: `cyberthreatexchange`.
- Hosted subscriptions, teams, API keys, MCP/TAXII and proxy behavior:
  `cyberthreatexchange_web_be` and possibly `web_commons`.
- Publisher/consumer UI: `cyberthreatexchange_web_fe`.
- Upload limits, routing, containers and backups:
  `cyberthreatexchange_web_deploy`.

## Important code surfaces

- Core routes: `cyberthreatexchange/urls.py`; uploads and connector polling:
  `cyberthreatexchange/worker/tasks.py`; models/views under
  `cyberthreatexchange/server/`.
- Web routes: `cyberthreatexchange_web_be/urls.py`; product proxy/API package:
  `cyberthreatexchange/` inside the web-backend repository; MCP:
  `cyberthreatexchange_mcp/`; team extensions: `ctx_teams/`.
- Frontend routes include `/feeds`, feed objects/jobs/connectors/subscriptions,
  `/search`, `/objects`, `/ttps`, public teams, integrations, and account/team
  administration.
- The production path accepts larger STIX uploads and must keep body-size
  limits aligned through Nginx, frontend/API proxy, backend and core.

## Validation focus

Cover per-feed and cross-team isolation, producer versus subscriber rights,
supported custom objects, duplicate/versionless imports, relationship ordering
and retry, connector pagination/date cursors, job state after worker failure,
upload-size enforcement, and REST/MCP/TAXII consistency.

## Supporting repositories

`stix2extensions`, `feeds2stix`, `dogesec_commons`, `stix2arango`,
`web_commons`, and `arango_taxii_server`.

Public positioning is maintained in `cyberthreatexchange-website`.

The `dogesec-cyberthreatexchange` OpenCTI connector is a production-critical
downstream API consumer. See
[external API consumers](../components/external-api-consumers.md).
