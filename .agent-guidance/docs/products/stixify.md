# Stixify

## Product purpose and users

Stixify turns unstructured files and web content—PDFs, Word documents,
PowerPoints, HTML, email-like content, images, and tabular input—into structured
STIX 2.1 intelligence. Analysts can search and pivot over extracted IoCs, TTPs,
entities and relationships, group work into dossiers, and share results through
REST, TAXII, MCP, and STIX exports.

Primary users are CTI/SOC teams, threat hunters, detection and purple teams,
security engineers, and service providers processing large volumes of reports.

## Repositories

| Repository | Owns |
| --- | --- |
| `stixify` | Upload/file domain model, document-to-STIX processing jobs, reports/topics, graph storage, and core REST API |
| `stixify_web_be` | Hosted users/teams/plans, uploads/reports/dossiers presentation and proxy endpoints, MCP/TAXII, schemas and sitemaps |
| `stixify_web_fe` | Upload, report, dossier, topic, observable/TTP and staff workflows |
| `stixify_web_deploy` | Production services, upload limits, Nginx routes, backups and deployment |
| `stixify_chrome_extension` | Captures webpages as MHTML, submits them to the public API, tracks jobs, and opens hosted results |

## Processing path

1. A user uploads content with an extraction profile.
2. Core creates a job and Celery worker task.
3. `dogesec_commons.stixifier.StixifyProcessor` invokes `file2txt` for the input
   type and `txt2stix` for extraction and relationship generation.
4. Core records the file/report and extraction metadata in PostgreSQL and writes
   the STIX graph through `stix2arango` to an identity/team-scoped collection.
5. Topic/clustering tasks and report/dossier workflows expose the result for
   analyst use.
6. The web backend applies hosted team/plan authorization and exposes browser,
   REST, MCP, and TAXII surfaces.

CTI Butler and Vulmatch provide optional knowledge-base/vulnerability lookups
during extraction.

## Developer ownership guide

- Input conversion, OCR, Markdown quality: `file2txt`.
- Extraction/relationship/Attack Flow/Navigator logic: `txt2stix`.
- Profiles and common processing orchestration: `dogesec_commons`.
- Job lifecycle, uploads, reports, topics and core graph API: `stixify`.
- Hosted dossiers, team access, subscriptions, MCP/TAXII and proxy behavior:
  `stixify_web_be` and possibly `web_commons`.
- Browser workflows: `stixify_web_fe`.
- Webpage capture, API submission, job polling, and extension storage/UI:
  `stixify_chrome_extension`.
- Payload limits, routes, containers, backups: `stixify_web_deploy`.

## Important code surfaces

- Core routes: `stixify/urls.py`; processing entry points:
  `stixify/worker/tasks.py` and `stixify/worker/process_post.py`; domain models:
  `stixify/web/models.py`.
- Web routes: `project/urls.py`; product API: `stixify_api/`; MCP:
  `stixify_mcp/`; team extensions: `stixify_teams/`.
- Frontend routes include `/uploads`, `/reports`, `/dossiers`, `/topics`,
  `/observables`, `/ttps`, `/integrations`, and `/staff/...`.
- The deployment Nginx configuration permits larger uploads than most products;
  preserve aligned limits through every proxy hop.

## Validation focus

Test each supported input mode, cleanup after failed/terminated jobs, reprocessing,
profile compatibility, media/R2 behavior, team isolation, report/dossier access,
STIX graph persistence, upload limits, and REST/MCP/TAXII contract parity. API
changes affecting `/v1/team/`, `/v1/reports/`, or `/v1/jobs/{id}/`, the
`API-KEY` header, upload fields, job/report identifiers, or app URL construction
must also build and exercise the Chrome extension.

## Supporting repositories

`file2txt`, `txt2stix`, `dogesec_commons`, `stix2arango`, `web_commons`,
`arango_taxii_server`, `ctibutler`, and `vulmatch`.

Downstream compatibility consumers are `stixify_chrome_extension` and the
`dogesec-stixify` OpenCTI connector. See
[external API consumers](../components/external-api-consumers.md).

Public positioning is maintained in `stixify-website`.
