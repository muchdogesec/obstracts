# External API consumers and integrations

These clients depend on public DOGESEC product APIs but run outside the product
production Compose stacks. Treat them as production-critical compatibility
surfaces whenever an API, authentication, pagination, schema, quota, or URL
contract changes.

## OpenCTI connectors

The authoritative connector implementations are in the upstream
`OpenCTI-Platform/connectors` repository under `external-import/`. The five
DOGESEC connectors were migrated to the OpenCTI catalog on 2026-11-24. The old
local `muchdogesec/opencti-connectors` fork is not the authoritative remote.
`opencti-deploy` contains local deployment examples and operator notes; it is a
consumer/deployment aid, not the connector source of truth.

All five connectors authenticate to the DOGESEC product with the `API-KEY`
header and send retrieved STIX bundles into the customer's OpenCTI instance.

| Product | Connector directory | Product API contracts directly consumed |
| --- | --- | --- |
| Obstracts | `external-import/dogesec-obstracts` | `GET /v1/feeds/`; `GET /v1/feeds/{feed_id}/posts/`; `GET /v1/feeds/{feed_id}/posts/{post_id}/objects/` |
| Stixify | `external-import/dogesec-stixify` | `GET /v1/dossiers/`; `GET /v1/dossiers/{dossier_id}/reports/`; `GET /v1/reports/{report_id}/objects/` |
| Vulmatch | `external-import/dogesec-vulmatch` | `GET /v1/sbom/`; `GET /v1/cve/objects/`; `GET /v1/cve/objects/{cve_name}/bundle/` |
| CTI Butler | `external-import/dogesec-ctibutler` | `GET /v1/{knowledge_base}/versions/installed/`; `GET /v1/{knowledge_base}/objects/`; `GET /v1/{knowledge_base}/objects/{object_id}/bundle/` |
| Cyber Threat Exchange | `external-import/dogesec-cyberthreatexchange` | `GET /v1/subscriptions/`; `GET /v1/feeds/{feed_id}/objects/` |

The clients also depend on response pagination and state semantics, including
`results` or `objects` list keys, absolute or cursor-based `next` values,
timestamps/cursors, stable object identifiers, and valid STIX 2.1 bundles.
Field-level behavior must be confirmed from current connector code and product
schema tests before a change; this table is a routing index, not a substitute
for source inspection.

## Stixify Chrome extension

`stixify_chrome_extension` is a first-class Stixify client. It:

1. captures a browser page as MHTML;
2. reads a user-supplied Stixify API endpoint and API key from Chrome sync
   storage;
3. calls `GET /v1/team/` to identify team/plan context;
4. submits multipart content to `POST /v1/reports/` using `API-KEY`;
5. polls `GET /v1/jobs/{job_id}/`; and
6. constructs hosted application links from the API hostname plus returned
   team, report, and job identifiers.

Changes to upload field names, accepted content types, quota responses, job
states, job/report identifiers, team payloads, CORS, API/app host conventions,
or API-key handling can break the extension even when product API tests pass.

## Compatibility and release gate

For a potentially breaking product API change:

1. Identify every route, header, field, pagination rule, STIX object, and error
   behavior used by the corresponding OpenCTI connector and, for Stixify, the
   Chrome extension.
2. Prefer additive changes and preserve the existing contract through a
   documented deprecation window. Never combine removal and consumer migration
   in an uncoordinated production release.
3. Add or update product-side contract tests using representative connector or
   extension requests and responses.
4. Run the affected connector's tests/build against the candidate product API.
   For Stixify, also run the extension lint/build and an end-to-end submission
   and job-polling smoke test against an ephemeral isolated environment.
5. Release consumers before or with the server change when compatibility cannot
   be preserved. Keep the server backward compatible until supported consumer
   versions have had a reasonable migration window.
6. After production deployment, verify a bounded API call and successful
   downstream ingestion/submission using the agent-owned account. Do not use
   customer credentials or data.

An API release is not complete while an affected connector or extension is
untested, known incompatible, or undocumented.
