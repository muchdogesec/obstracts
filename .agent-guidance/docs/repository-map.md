# Repository map

Use this map before deciding where a change belongs. A customer-facing product
is the combination of its core, web backend, frontend, deployment repository,
and shared/supporting components.

## Product repositories

| Repository | Product | Role | Read next |
| --- | --- | --- | --- |
| `obstracts` | Obstracts | Core ingestion, extraction, storage, and public core API | [Obstracts](products/obstracts.md) |
| `obstracts_web_be` | Obstracts | Commercial web control plane, proxy API, MCP/TAXII, teams and subscriptions | [Obstracts](products/obstracts.md) |
| `obstracts_web_fe` | Obstracts | Customer/staff Next.js interface | [Obstracts](products/obstracts.md) |
| `obstracts_web_deploy` | Obstracts | Production Compose, Nginx routing, deployment and backup workflows | [Obstracts](products/obstracts.md) |
| `stixify` | Stixify | Core file-processing, extraction, storage, and public core API | [Stixify](products/stixify.md) |
| `stixify_web_be` | Stixify | Commercial web control plane, proxy API, MCP/TAXII, teams and subscriptions | [Stixify](products/stixify.md) |
| `stixify_web_fe` | Stixify | Customer/staff Next.js interface | [Stixify](products/stixify.md) |
| `stixify_web_deploy` | Stixify | Production Compose, Nginx routing, deployment and backup workflows | [Stixify](products/stixify.md) |
| `stixify_chrome_extension` | Stixify | Chrome extension that submits webpages through the public API and tracks processing jobs | [Stixify](products/stixify.md) |
| `vulmatch` | Vulmatch | CVE/CPE ingestion, enrichment, graph storage, and public core API | [Vulmatch](products/vulmatch.md) |
| `vulmatch_web_be` | Vulmatch | Commercial web control plane, proxy API, MCP/TAXII, teams and subscriptions | [Vulmatch](products/vulmatch.md) |
| `vulmatch_web_fe` | Vulmatch | Customer Next.js interface | [Vulmatch](products/vulmatch.md) |
| `vulmatch_web_deploy` | Vulmatch | Production Compose, Nginx routing, deployment and backup workflows | [Vulmatch](products/vulmatch.md) |
| `ctibutler` | CTI Butler | Knowledge-base ingestion, relationship processing, graph storage, and core API | [CTI Butler](products/ctibutler.md) |
| `ctibutler_web_be` | CTI Butler | Commercial web control plane, proxy API, MCP/TAXII, teams and subscriptions | [CTI Butler](products/ctibutler.md) |
| `ctibutler_web_fe` | CTI Butler | Customer Next.js interface | [CTI Butler](products/ctibutler.md) |
| `ctibutler_web_deploy` | CTI Butler | Production Compose, Nginx routing, deployment and backup workflows | [CTI Butler](products/ctibutler.md) |
| `cyberthreatexchange` | Cyber Threat Exchange | Feed publishing/subscription model, STIX validation/storage, connectors, and core API | [Cyber Threat Exchange](products/cyberthreatexchange.md) |
| `cyberthreatexchange_web_be` | Cyber Threat Exchange | Commercial web control plane, proxy API, MCP/TAXII, teams and subscriptions | [Cyber Threat Exchange](products/cyberthreatexchange.md) |
| `cyberthreatexchange_web_fe` | Cyber Threat Exchange | Publisher/consumer Next.js interface | [Cyber Threat Exchange](products/cyberthreatexchange.md) |
| `cyberthreatexchange_web_deploy` | Cyber Threat Exchange | Production Compose, Nginx routing, deployment and backup workflows | [Cyber Threat Exchange](products/cyberthreatexchange.md) |

The local workspace directory for `cyberthreatexchange_web_be` may be named
`cyberthreatexchange_be`; use the Git remote/repository name as the canonical
identity.

## Shared runtime and data components

Read [shared components](components/shared-components.md) for full boundaries
and [dependency classification](components/dependency-classification.md) for
the evidence-based criticality model.

| Repository | Primary responsibility | Main consumers |
| --- | --- | --- |
| `dogesec_commons` | Core Django object views, profiles/extraction orchestration, common filters and knowledge-base sync | Product core repositories |
| `web_commons` | Users, teams, API keys, WorkOS, subscriptions/Stripe, email automation, shared MCP primitives | Product web backends |
| `stix2arango` | Insert/version STIX 2.1 bundles and generate graph edges in ArangoDB | All product cores |
| `arango_taxii_server` | Reusable TAXII 2.1 server over ArangoDB | Product web backends |
| `server_setup_scripts` | Base host provisioning for production product servers | Product deployment repositories |
| `file2txt` | Convert HTML/documents/images/tabular input to Markdown | Obstracts, Stixify |
| `txt2stix` | Extract IoCs/TTPs/relationships and produce STIX 2.1 bundles | Obstracts, Stixify |
| `history4feed` | Discover historical RSS/Atom posts and retrieve article content | Obstracts |
| `arango_cve_processor` | Link CVEs to CWE/CAPEC/ATT&CK, EPSS, KEV, and CPE match context | Vulmatch |
| `cve2stix` | Generate CVE/CPE-oriented STIX bundle inputs | Vulmatch data pipeline |
| `cpe2stix` | Generate CPE software STIX bundle inputs | Vulmatch data pipeline |
| `arango_cti_processor` | Generate cross-knowledge-base relationships and groupings | CTI Butler |
| `cwe2stix` | Generate CWE bundle inputs | CTI Butler |
| `location2stix` | Generate location bundle inputs | CTI Butler |
| `sectors2stix` | Generate sector bundle inputs | CTI Butler |
| `disarm2stix` | Generate DISARM bundle inputs | CTI Butler |
| `d3f3nd2stix` | Generate D3FEND bundle inputs | CTI Butler |
| `cloak2stix` | Generate CLOAK bundle inputs | CTI Butler |
| `stix2extensions` | Custom STIX objects/extensions accepted by the exchange | Cyber Threat Exchange and producers |
| `feeds2stix` | Convert public feeds to STIX and publish them through scheduled workflows | Cyber Threat Exchange supply |
| `stixviewer` | Render STIX graphs and objects in browser workflows | Product frontends |

## Downstream API consumers

All five products have OpenCTI external-import connectors maintained in the
upstream `OpenCTI-Platform/connectors` repository. `opencti-deploy` provides
DOGESEC-oriented local OpenCTI deployment examples. Stixify additionally has
the `stixify_chrome_extension` client.

These are production-critical compatibility consumers: they are not services
inside a product's production Compose stack, but public API changes can break
customer ingestion or browser workflows. See the
[external API consumer matrix](components/external-api-consumers.md) for exact
routes, ownership, and release gates.

## Adjacent repositories

The five `*-website` repositories are public marketing/documentation sites, not
the authenticated product frontends. They are nevertheless the best source for
current positioning, named audiences, public feature claims, and public API
links. Changes to product behavior may require coordinated updates there.

Other conversion, connector, demo, dataset, and website repositories can be
upstream or downstream of a product without running in its production Compose
stack. Confirm the relationship in current code/workflows before broadening a
change.
