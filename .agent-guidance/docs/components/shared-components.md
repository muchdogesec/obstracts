# Shared and supporting components

See [dependency classification](dependency-classification.md) for which
components are critical runtime packages, production data-supply pipelines,
operational prerequisites, or adjacent repositories.

## `dogesec_commons`

Shared code used inside the core product services. It provides common ArangoDB
object views/helpers, knowledge-base sync, identities, profile/extractor models,
the `StixifyProcessor` orchestration used by Obstracts/Stixify, pagination,
filtering, ordering, schema and exception helpers.

Change it when behavior is genuinely common to core products. Do not patch an
installed copy in a consumer or duplicate it into one core. A release requires
consumer version updates and compatibility tests.

## `web_commons`

Shared code used inside hosted web backends. It owns reusable users,
authentication/WorkOS integration, teams and roles, invitations, API keys and
permissions, subscriptions/Stripe, email automation, shared MCP transport/client
primitives, pagination, and common management commands.

Product-specific entitlement rules and proxy contracts stay in the product web
backend unless the same rule and data model are intentionally shared across
products. Treat changes to memberships, permissions, API keys, billing or MCP
request context as cross-product security changes.

## `stix2arango`

The shared STIX-to-ArangoDB persistence layer. It maps bundle objects into
vertex/edge collections, handles embedded relationships, records import
metadata, and implements default versus versionless update semantics.

Changes can alter graph shape and object visibility across all products. Check
collection names, `_is_latest`, `_record_md5_hash`, generated relationships,
large-file behavior, repeat imports, and rollback/rebuild implications.

## `arango_taxii_server`

Reusable TAXII 2.1 Django implementation over ArangoDB. Product web backends
install its app and supply product/team authorization plus collection mapping.
Protocol discovery, API roots, collections, manifests, object pagination and
TAXII schemas belong here; which team may access which product collection
belongs in the consumer.

## Extraction stack

### `history4feed`

Obstracts-only feed history and article retrieval layer. It turns RSS/Atom plus
Wayback history into a durable post archive and full-text input.

### `file2txt`

Converts supported documents, HTML, CSV and images into Markdown and extracts
image text. It may use external Marker and Google Vision services for some
modes. Changes affect input fidelity and cost/failure behavior in Obstracts and
Stixify.

### `txt2stix`

Extracts observables and TTPs using pattern, lookup and optional LLM providers;
generates STIX objects, relationships, summaries, Attack Flow and Navigator
metadata. It calls CTI Butler/Vulmatch for selected enrichments. Changes affect
both Obstracts and Stixify output contracts.

## Knowledge-base and vulnerability processors

### `arango_cti_processor`

Creates cross-knowledge-base STIX relationships/groupings for CTI Butler. It
expects required source collections to have been loaded first.

### `arango_cve_processor`

Enriches Vulmatch CVEs with CWE/CAPEC/ATT&CK links, EPSS, KEV, and CPE-match
context. Several modes have ordering prerequisites; preserve those dependencies
in jobs and backfills.

### Data generators

Repositories such as `cve2stix`, `cpe2stix`, `cwe2stix`, `location2stix`,
`sectors2stix`, `disarm2stix`, `d3f3nd2stix`, and `cloak2stix` generate the
versioned STIX inputs consumed by product core services. A mapping bug should be
fixed at the generator and followed through publication, core import, graph
processing, APIs, and UI—not patched only in a displayed response.

## Cyber Threat Exchange supply

`stix2extensions` defines reusable custom STIX objects/extensions accepted by
CTX. `feeds2stix` contains many public-source processors and scheduled GitHub
workflows that publish bundles into the exchange. They are upstream producers,
not containers in the CTX product stack.

## Operations

`server_setup_scripts` provisions base product hosts, including deployment
users, Docker, PostgreSQL, ArangoDB, Redis, storage layout, and related services.
Product deployment repositories assume that host baseline already exists.

Do not solve a base-host problem only in a single product's Compose repository
when the provisioning contract is shared. Conversely, do not put product route
or container behavior into the generic host bootstrap.
