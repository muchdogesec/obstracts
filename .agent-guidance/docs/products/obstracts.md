# Obstracts

## Product purpose and users

Obstracts turns public security blogs and RSS/Atom feeds into structured STIX
2.1 threat intelligence. It continuously collects current and historical posts,
extracts IoCs, TTPs and related context, and makes the results searchable and
available through REST, TAXII, MCP, and STIX exports.

Primary users are threat-intelligence and SOC teams, threat hunters, detection
and purple teams, and engineers building CTI automations. The product is both an
analyst research interface and a structured upstream source for TIPs and other
security systems.

## Repositories

| Repository | Owns |
| --- | --- |
| `obstracts` | Feed/post domain model, history retrieval integration, HTML/document processing, extraction jobs, STIX graph storage, topics/clustering, and core REST API |
| `obstracts_web_be` | Hosted users/teams/plans, feed subscriptions/bookmarks, team authorization, core proxy/presentation API, MCP tools, TAXII mapping, schemas and sitemaps |
| `obstracts_web_fe` | Feed/post/topic/observable/TTP browser workflows, bookmarks, integrations, staff feed/profile/job workflows |
| `obstracts_web_deploy` | Production services, Nginx routes, MCP/REST/TAXII gateways, backups, health/startup and deployment |

## Processing path

1. A user or staff member adds a feed and selects an extraction profile.
2. `history4feed` discovers the live feed and Wayback history, retrieves posts,
   and stores HTML/post metadata inside the core Django application.
3. Core Celery tasks use `dogesec_commons.stixifier.StixifyProcessor` to run
   `file2txt` in HTML/article mode, then `txt2stix` with the selected profile.
4. The processor emits STIX bundles plus extraction metadata, summaries,
   ATT&CK Navigator/Attack Flow context, and media artifacts.
5. `stix2arango` persists objects/relationships in per-feed ArangoDB
   collections; PostgreSQL stores feeds, posts, jobs, profiles, and clustering
   metadata.
6. The web backend authorizes the hosted team and proxies/presents core data to
   the frontend, public API, MCP, and TAXII clients.

Obstracts also calls CTI Butler and Vulmatch for knowledge-base and vulnerability
lookups used during extraction/enrichment. Those are service dependencies, not
code that should be copied into Obstracts.

## Developer ownership guide

- Historical discovery, feed parsing, article retrieval: `history4feed` first,
  then its integration in `obstracts`.
- HTML/file-to-Markdown fidelity or OCR: `file2txt`.
- Extractor definitions, AI/pattern extraction, relationship generation,
  Attack Flow/Navigator output: `txt2stix`, then profile/orchestration behavior
  in `dogesec_commons` and `obstracts`.
- Feed/post/jobs/topics/core graph API: `obstracts`.
- Team subscriptions, bookmarks, hosted access rules, API keys, MCP adapter, or
  hosted proxy response: `obstracts_web_be` and possibly `web_commons`.
- Customer/staff interaction: `obstracts_web_fe` plus its API contract.
- Public host/path/body-size/container/backup change:
  `obstracts_web_deploy`.

## Important code surfaces

- Core routes: `obstracts/urls.py`; processing: `obstracts/cjob/tasks.py`;
  models/storage: `obstracts/server/models.py`.
- Web routes: `obstracts_web/urls.py`; product proxy/API: `obstracts_api/`;
  MCP: `obstracts_mcp/`; hosted team extensions: `obstracts_teams/`.
- Frontend routes include `/feeds`, `/posts`, `/topics`, `/observables`,
  `/ttps`, `/bookmark`, `/integrations`, and `/staff/...`.
- Deployment runs core, core Celery/beat, backend, backend Celery/beat,
  frontend, and Nginx. Dedicated API, TAXII, and MCP listeners proxy through the
  web backend.

## Validation focus

Exercise feed isolation, team authorization, subscription limits, default-feed
rules, retries/cancellation, extraction-profile compatibility, Arango collection
selection, and schemas across both REST and MCP. Pipeline tests must distinguish
mocked processor coverage from a real core stack with PostgreSQL, Redis,
ArangoDB, worker, and seed feed.

## Supporting repositories

`history4feed`, `file2txt`, `txt2stix`, `dogesec_commons`, `stix2arango`,
`web_commons`, `arango_taxii_server`, `ctibutler`, and `vulmatch`.

Public positioning is maintained in `obstracts-website`.

The `dogesec-obstracts` OpenCTI connector is a production-critical downstream
API consumer. See [external API consumers](../components/external-api-consumers.md).
