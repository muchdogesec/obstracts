# Vulmatch

## Product purpose and users

Vulmatch is a vulnerability-intelligence search and relationship layer. It
stores CVE and CPE data as STIX 2.1 and enriches it with CVSS, EPSS, known
exploitation, CWE/CAPEC/ATT&CK context, and affected-product relationships. It
is not a scanner, endpoint agent, or patch-management system.

Primary users are vulnerability-management, threat-intelligence, SOC,
detection/engineering, research, and developer teams building
vulnerability-aware workflows and SBOM monitoring.

## Repositories

| Repository | Owns |
| --- | --- |
| `vulmatch` | CVE/CPE import, vulnerability enrichment, graph queries, statistics and core REST API |
| `vulmatch_web_be` | Hosted users/teams/plans, product proxy API, SBOM/team workflows, MCP/TAXII, schemas and sitemaps |
| `vulmatch_web_fe` | Vulnerability/CPE/CNA/EPSS/KEV/SBOM/dashboard and integration workflows |
| `vulmatch_web_deploy` | Production services, Nginx routes, MCP gateway, backups and deployment |

## Data path

1. `cve2stix` and related data-generation workflows publish CVE/CPE-oriented
   bundle inputs. Core downloads dated bundles from the configured Vulmatch
   bucket.
2. Core Celery tasks load bundles with `stix2arango` into fixed product
   collections and maintain supporting PostgreSQL state.
3. `arango_cve_processor` creates/updates CVE-to-CWE/CAPEC/ATT&CK relationships,
   EPSS history, CISA/VulnCheck KEV reports, and CPE-match groupings.
4. CTI Butler supplies knowledge-base lookups used for CWE/CAPEC/ATT&CK views.
5. The web backend applies hosted team/plan/API-key authorization and exposes
   browser, REST, MCP, and TAXII surfaces.

Large initial backfills and index-building are operational data-pipeline tasks;
they are not equivalent to starting the web containers.

## Developer ownership guide

- Source CVE/CPE-to-STIX mapping: `cve2stix`/`cpe2stix` data pipeline.
- CVE enrichment and relationship algorithms: `arango_cve_processor`.
- Import jobs, graph query/filter/sort behavior, CVE/CPE/KEV/EPSS core API:
  `vulmatch`.
- Hosted SBOM/team/subscription/API-key/MCP/TAXII behavior:
  `vulmatch_web_be` and possibly `web_commons`.
- Browser flows: `vulmatch_web_fe`.
- Gateway/routing/container/backup change: `vulmatch_web_deploy`.

## Important code surfaces

- Core routes: `vulmatch/urls.py`; jobs/import/enrichment:
  `vulmatch/worker/tasks.py`; graph search: `vulmatch/server/arango_helpers.py`;
  APIs: `vulmatch/server/views.py`.
- Web routes: `project/urls.py`; product proxy API: `vulmatch_api/`; MCP:
  `vulmatch_mcp/`; team extensions: `vulmatch_teams/`.
- Frontend routes include `/vulnerabilities`, `/cpes`, `/cnas`, `/epss`,
  `/kevs`, `/sbom`, `/dashboard`, `/knowledgebases`, and `/integrations`.

## Validation focus

Cover CVE/CPE import ranges and idempotency, `_is_latest`/version semantics,
EPSS time history, KEV source distinctions, vulnerable versus merely referenced
CPEs, cross-knowledge-base relationships, team/SBOM isolation, pagination/sort
indexes, REST/MCP/TAXII parity, and initial-backfill/rebuild behavior.

## Supporting repositories

`cve2stix`, `cpe2stix`, `arango_cve_processor`, `dogesec_commons`,
`stix2arango`, `web_commons`, `arango_taxii_server`, and `ctibutler`.

Public positioning is maintained in `vulmatch-website`.

The `dogesec-vulmatch` OpenCTI connector is a production-critical downstream
API consumer. See [external API consumers](../components/external-api-consumers.md).
