# Shared web-product architecture

The five DOGESEC web products use the same broad architecture. The repository
names reflect layers, not standalone products.

## Runtime layers

```text
browser / API client / MCP client / TAXII client
                         |
                       Nginx
          +--------------+---------------+
          |              |               |
       Next.js       web backend      dedicated API,
       frontend        (Django)       TAXII and MCP hosts
                          |
                    core Django API
                    + Celery workers
                   /          |        \
             PostgreSQL     Redis     ArangoDB
                                      (STIX graph)
```

The deployment repositories run separate containers for the frontend, web
backend, core, Celery workers, and (where configured) beat schedulers. Nginx
exposes the browser app and routes dedicated public API, TAXII, and MCP
hostnames/ports to paths on the web backend. PostgreSQL, Redis, and ArangoDB are
host services provisioned outside the product Compose file.

## Repository layer boundaries

### Core

The un-suffixed product repository owns the open-source domain engine and core
API. It performs ingestion, transformation, graph persistence, search, and
product-specific background jobs. It is where an operation should live when it
must also work without the hosted commercial web layer.

Core repositories generally use Django/DRF, Celery, PostgreSQL for relational
state, Redis for queues/caches, and ArangoDB for STIX objects and relationships.
They reuse `dogesec_commons` and `stix2arango`.

### Web backend (`*_web_be`)

The web backend is the hosted control plane and public gateway. It owns hosted
users, WorkOS authentication, teams, API keys, plans/subscriptions, Stripe and
email integration, team authorization, sitemap/schema generation, MCP adapters,
TAXII integration, and product-specific proxy/presentation endpoints.

It calls the core through a product `*_SERVICE_BASE_URL` setting. It should not
silently reimplement core ingestion or graph rules. Shared hosted behavior
normally belongs in `web_commons`; product-specific access rules and response
shaping stay in the product web backend.

### Frontend (`*_web_fe`)

The frontend owns customer and staff browser workflows. The current products
are Next.js applications with React and Material UI. Several still contain a
legacy application structure under `src/legacy`, `src/pages`, or React Router
while routes are progressively exposed through `src/app`. Inspect the current
route and service implementation before assuming a pure App Router design.

The frontend calls same-origin `/api/...` routes. Nginx sends those requests to
the web backend; the web backend may satisfy them itself or proxy to core.

### Deployment (`*_web_deploy`)

The deployment repository is executable production architecture. It owns
Compose service wiring, image tags, Nginx routing, server restart/pull logic,
backup scripts, and manual deployment workflows. A code change that adds a
container, route, port, volume, environment variable, health check, or startup
dependency is incomplete until this layer is checked.

## Shared ownership rules

- A domain transformation, ingestion rule, graph query, or core API contract
  starts in core or its supporting processor/library.
- Hosted identity, team isolation, plans, billing, API keys, and shared MCP
  transport start in `web_commons` or the product web backend.
- Browser interaction and rendering start in the frontend, but the API contract
  must be traced through the web backend to core.
- STIX insertion/version semantics start in `stix2arango`; shared core object
  filtering and profile behavior start in `dogesec_commons`.
- TAXII protocol behavior starts in `arango_taxii_server`; product collection
  authorization/mapping stays in the product web backend.
- Production routing, container startup, backups, and rollouts start in the
  deployment repository.
- A change in a shared package requires compatibility checks in every affected
  consumer and coordinated version-pin/image updates where applicable.

## Data stores

- PostgreSQL stores Django models, jobs, users/teams/subscriptions, and other
  relational control data. Core and web backend use separate Django services
  and may use separate databases/schemas even when hosted on the same server.
- Redis supports Celery, results, locks, and caching.
- ArangoDB stores STIX vertices and edges. Collection naming and versioning are
  part of product behavior; do not treat ArangoDB as a generic opaque cache.
- Object/media storage may use Cloudflare R2. Product-specific bucket settings
  and public media URLs are configured outside the repository.

## Contract surfaces to trace

For an end-to-end change, identify all applicable contracts:

1. frontend route and service call;
2. web-backend route, permission, serializer, proxy, MCP tool, or TAXII mapping;
3. core REST endpoint and background job;
4. shared library/processor behavior;
5. PostgreSQL/Redis/ArangoDB persistence;
6. Docker image and environment configuration;
7. Nginx public routing;
8. public schema, API docs, marketing claims, and integration behavior.
