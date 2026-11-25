# Product dependency classification

This classification is based on current default-branch dependency declarations,
deployment Dockerfiles, frontend manifests, imports, and data-ingestion paths.
The direct dependency declarations are the primary evidence for runtime
criticality.

## Critical runtime packages

These packages execute inside product core, web-backend, or frontend containers.
A breaking change can prevent the product from starting or serving correct
results.

| Component repository | Runtime consumers | Evidence |
| --- | --- | --- |
| `dogesec_commons` | All five cores | Direct core dependency |
| `stix2arango` | All five cores and all five web backends | Direct Python dependency |
| `web_commons` | All five web backends | Installed from a versioned Git ref in each deployment Dockerfile |
| `arango_taxii_server` | All five web backends | Direct backend dependency |
| `history4feed` | Obstracts core | Direct core dependency |
| `file2txt` | Obstracts and Stixify cores | Locked/runtime extraction dependency; direct in Stixify |
| `txt2stix` | Obstracts and Stixify cores | Direct core dependency |
| `stix2extensions` | CTX core; extraction stacks transitively | Direct CTX dependency and locked extraction dependency |
| `arango_cve_processor` | Vulmatch core | Direct core dependency |
| `arango_cti_processor` | CTI Butler core | Direct core dependency |
| `stixviewer` | All five frontends | Production npm dependency |

Treat these repositories as part of the affected product for dependency
updates, vulnerabilities, releases, integration testing, and incidents. A
package release is not complete until compatible consumer pins/images are
published and validated.

## Production data-supply pipelines

These repositories do not execute inside the product containers, but their
outputs feed production data. A defect can corrupt, omit, or delay product data.

| Pipeline | Product/data supplied |
| --- | --- |
| `cve2stix`, `cpe2stix` | Vulmatch CVE/CPE bundle inputs |
| `cwe2stix`, `location2stix`, `sectors2stix`, `disarm2stix`, `d3f3nd2stix`, `cloak2stix` | CTI Butler versioned bundle inputs |
| `feeds2stix` | Scheduled public-feed bundles published into Cyber Threat Exchange |
| Upstream ATT&CK, CAPEC, ATLAS and F3 mirror/transform workflows | CTI Butler versioned bundle inputs |

Treat these as production-critical pipelines for mapping, publication,
provenance, and incident response, but do not describe them as runtime
microservices or add them to product Compose stacks.

## Operational prerequisites

`server_setup_scripts` is production-critical provisioning code. It establishes
the host services and filesystem contract assumed by every deployment
repository, but it is not an application runtime package.

The five deployment repositories are likewise production-critical control
planes rather than libraries.

## Production API consumers and integrations

The five DOGESEC OpenCTI connectors and the Stixify Chrome extension are
production-critical downstream consumers. They do not execute in the product
Compose stacks and therefore do not appear in product `requirements.txt`
files, but their compatibility is part of the supported public API contract.

An API change is incomplete until affected downstream clients have been traced,
tested, and either proven compatible or released in a coordinated migration.
See [external API consumers](external-api-consumers.md).

## Adjacent and standalone repositories

A repository that is absent from the dependency declarations, production
Dockerfiles, frontend manifests, and verified ingestion/publication paths is not
part of the five products' critical runtime by default. It may be a standalone
tool, an adjacent product, a website, a demo, a dataset, an experiment, or a
legacy repository.

Examples include unrelated `*2stix` converters, demos, marketing websites,
sample feeds, media repositories, and tools for other DOGESEC products. The
OpenCTI connectors and Stixify Chrome extension are explicit exceptions because
their production dependency is contractual rather than a package import. Do not
delete, deprecate, or label one experimental solely because it is absent here;
that requires a repository-specific review. The default classification only
means it is outside the critical runtime and production-data path of these five
products.

## Classification rule

When a dependency changes:

1. Update this document and the affected product guide.
2. Trace direct and transitive consumer pins.
3. Test the package itself and every affected product contract.
4. Publish and promote in dependency order.
5. Verify production data/output, not only container startup.
