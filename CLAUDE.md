# ConsentOS

## Project Overview

ConsentOS is a multi-tenant cookie consent management platform — a source-available alternative to OneTrust, Cookiebot, and CookieYes — that provides cookie scanning, consent collection, auto-blocking, and compliance checking across many sites with per-site configuration.

The platform delivers a single `<script>` tag that site owners embed. This script handles consent collection, cookie blocking, IAB TCF v2.2, and Google Consent Mode v2 signalling. A separate admin dashboard allows site owners to manage configurations, review scan results, and check compliance.

**Public repo:** [github.com/consentos/consentos](https://github.com/consentos/consentos)
**Domain:** [consentos.dev](https://consentos.dev)

## Architecture Summary

```
CDN (static assets)
├── consent-loader.js      (~2KB gzipped, sync bootstrap)
├── consent-bundle-{v}.js  (~25KB gzipped, full banner + blocker)
├── site-config-{id}.json  (cached site configuration)
└── translations-{locale}.json

Client Browser
├── Script Interceptor (MutationObserver + createElement override)
├── Cookie Blocker (document.cookie proxy, Storage proxy)
├── Banner UI (Shadow DOM, customisable, a11y-compliant)
├── TCF v2.2 API (__tcfapi)
├── Google Consent Mode v2 (gtag integration)
├── Client-side Cookie Reporter
└── Consent State Manager
        │
        ▼
API Layer (FastAPI)
├── Config API    — site/org CRUD, banner config, allow-lists, CDN publishing
├── Consent API   — consent recording, retrieval, TC string generation, analytics
├── Scanner API   — scan management, client-side cookie reports
└── Admin BFF     — aggregates the above for the admin UI

Scanner Service (Python + Playwright)
├── Scheduled headless browser crawls
├── Cookie discovery and script attribution
└── Auto-categorisation via known cookies DB

PostgreSQL — all persistent state
Redis      — caching, rate limiting, Celery job queue

Admin UI (Vite + React + TypeScript)
├── Site management, configuration editor
├── Cookie manager, allow-list management
├── Banner builder (visual editor with live preview)
├── Compliance checker (GDPR, CNIL, CCPA, ePrivacy, LGPD)
└── Analytics dashboard (consent rates, trends, regional)
```

## Technology Stack

### Backend (`apps/api/`)
- **Language:** Python 3.12+
- **Framework:** FastAPI
- **ORM:** SQLAlchemy 2.0 (async)
- **Migrations:** Alembic
- **Database:** PostgreSQL 16
- **Cache/Queue:** Redis + Celery
- **Auth:** JWT (org-scoped, role-based)
- **Validation:** Pydantic v2

### Scanner (`apps/scanner/`)
- **Language:** Python 3.12+
- **Browser automation:** Playwright
- **Job scheduling:** Celery + Redis

### Banner Script (`apps/banner/`)
- **Language:** TypeScript
- **Build:** Rollup (outputs IIFE bundles)
- **UI isolation:** Shadow DOM
- **Standards:** IAB TCF v2.2, Google Consent Mode v2

### Admin UI (`apps/admin-ui/`)
- **Framework:** Vite + React + TypeScript
- **Primary UI:** shadcn/ui + TailwindCSS
- **Complex components:** MUI (DataGrid for tables, charts)
- **Server state:** TanStack Query
- **Client state:** Zustand
- **Routing:** React Router v6
- **Forms:** React Hook Form + Zod
- **i18n:** react-i18next

### Infrastructure
- **Containerisation:** Docker / Docker Compose
- **Orchestration:** Kubernetes (Helm chart)
- **CDN:** Cloud-agnostic (CloudFlare, Cloud CDN, or CloudFront)

## Project Structure

```
consent-platform/
├── apps/
│   ├── api/                          # FastAPI backend
│   │   ├── src/
│   │   │   ├── config/               # Pydantic settings, environment
│   │   │   ├── models/               # SQLAlchemy models
│   │   │   ├── schemas/              # Pydantic request/response schemas
│   │   │   ├── routers/              # API route handlers
│   │   │   │   ├── config.py         # site/org config endpoints
│   │   │   │   ├── consent.py        # consent recording/retrieval
│   │   │   │   ├── scanner.py        # scan management
│   │   │   │   ├── analytics.py      # analytics endpoints
│   │   │   │   ├── compliance.py     # compliance checker
│   │   │   │   └── auth.py           # authentication
│   │   │   ├── services/             # Business logic
│   │   │   │   ├── consent.py
│   │   │   │   ├── tcf.py            # TC string encoding/decoding
│   │   │   │   ├── gcm.py            # Google Consent Mode logic
│   │   │   │   ├── compliance.py     # Compliance rule engine
│   │   │   │   ├── publisher.py      # CDN publishing
│   │   │   │   └── classification.py # Cookie auto-categorisation
│   │   │   ├── db/                   # Database connection, session
│   │   │   └── main.py
│   │   ├── tests/
│   │   ├── alembic/
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   │
│   ├── scanner/                      # Cookie scanner service
│   │   ├── src/
│   │   │   ├── crawler.py            # Playwright-based crawler
│   │   │   ├── classifier.py         # Cookie classification
│   │   │   ├── scheduler.py          # Scan job scheduling
│   │   │   └── worker.py             # Celery worker
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── admin-ui/                     # Vite + React + TS admin dashboard
│   │   ├── src/
│   │   │   ├── components/
│   │   │   ├── pages/
│   │   │   ├── hooks/
│   │   │   ├── api/                  # TanStack Query hooks
│   │   │   ├── stores/               # Zustand stores
│   │   │   └── i18n/
│   │   ├── package.json
│   │   ├── vite.config.ts
│   │   ├── tsconfig.json
│   │   └── tailwind.config.ts
│   │
│   └── banner/                       # Client-side consent banner
│       ├── src/
│       │   ├── loader.ts             # Lightweight bootstrap (~2KB)
│       │   ├── banner.ts             # Banner UI engine
│       │   ├── blocker.ts            # Script/cookie interceptor
│       │   ├── tcf.ts                # TCF v2.2 API implementation
│       │   ├── gcm.ts                # Google Consent Mode v2
│       │   ├── reporter.ts           # Client-side cookie reporter
│       │   ├── consent.ts            # Consent state management
│       │   ├── i18n.ts               # Translation loader
│       │   ├── a11y.ts               # Accessibility utilities
│       │   └── types.ts
│       ├── rollup.config.js
│       ├── package.json
│       └── tsconfig.json
│
├── packages/
│   └── shared/                       # Shared types, constants, utils
│
├── helm/consentos/                  # Kubernetes deployment
├── docker-compose.yml
├── Makefile
└── README.md
```

## Key Data Entities

- **organisations** — multi-tenant root, each org has multiple sites
- **users** — org-scoped with roles: owner, admin, editor, viewer
- **sites** — a domain being managed (e.g. example.com), belongs to an org
- **site_configs** — full configuration per site: blocking mode, TCF settings, GCM defaults, banner config JSON, scan schedule, consent expiry
- **cookie_categories** — taxonomy (necessary, functional, analytics, marketing, personalisation) with TCF purpose and GCM consent type mappings
- **cookies** — discovered cookies per site with metadata, vendor, category, review status
- **cookie_allow_list** — approved cookies per site with category assignment
- **known_cookies** — shared knowledge base of known cookie patterns for auto-categorisation
- **consent_records** — audit trail of every consent event (partitioned by month)
- **scan_jobs** / **scan_results** — scanning pipeline state and results
- **translations** — i18n strings per site per locale

## Configuration Hierarchy

Configuration resolves in this order (each level overrides the previous):

```
System Defaults (code) → Organisation Defaults → Site Config → Regional Overrides
```

The `site_configs.regional_modes` JSONB field allows per-region blocking mode:
```json
{"EU": "opt_in", "GB": "opt_in", "US-CA": "opt_out", "BR": "opt_in", "DEFAULT": "opt_in"}
```

## Consent Flow

1. Site loads `consent-loader.js` (sync, before other scripts)
2. Loader reads existing consent cookie — if valid, applies consent state and exits
3. If no consent: installs script interceptor, blocks non-essential scripts/cookies
4. Sets Google Consent Mode defaults (`gtag('consent', 'default', {...})`)
5. Installs `__tcfapi` stub for TCF v2.2
6. Async-loads full banner bundle + site config from CDN
7. Banner displays; user interacts
8. On consent action: generates TC string, sets first-party cookie, calls `gtag('consent', 'update', {...})`, releases blocked scripts by category
9. POSTs consent record to Consent API for server-side audit storage
10. Fires `consent-change` custom event + dataLayer push for GTM

## Banner Script Architecture

The banner is split into two files for performance:

- **consent-loader.js** (~2KB gzipped) — synchronous critical path: consent cookie read, GCM defaults, TCF stub, script interceptor installation, async bundle load
- **consent-bundle-{version}.js** (~25KB gzipped) — full UI, consent engine, TCF encoder, reporter

The banner UI renders inside **Shadow DOM** for complete style isolation from the host site.

**Display modes:** overlay (full-screen modal), bottom_banner, top_banner, corner_popup, inline (into specific DOM element)

**Auto-blocking works by:**
- Overriding `document.createElement` to intercept `<script>` tag creation
- `MutationObserver` on `<head>` and `<body>` for dynamically inserted scripts
- Proxying `document.cookie` setter to block writes from non-essential categories
- Wrapping `localStorage.setItem` and `sessionStorage.setItem`
- Maintaining a queue of blocked scripts, released per-category when consent is granted

## Compliance Frameworks

The compliance engine is rule-based. Each framework is a set of `ComplianceRule` objects:

- **GDPR** — opt-in, reject = accept prominence, granular consent, proof of consent, no cookie walls, no pre-ticked boxes
- **CNIL** — all GDPR rules plus: Tout refuser on first layer, max 13-month cookie lifetime, max 6-month consent retention, re-consent every 6 months
- **CCPA/CPRA** — opt-out model, Do Not Sell link, honour GPC signal, under-16 opt-in
- **ePrivacy** — consent for non-essential, strictly necessary exempt
- **LGPD** — consent or legitimate interest basis, identify data controller

Rules output: severity (critical/warning/info), message, recommendation. Aggregated into per-framework scores.

## Coding Conventions

- **Language:** British English throughout (code comments, UI strings, documentation)
- **Python:** Use `pyproject.toml`, type hints everywhere, async where possible
- **SQL:** CTEs over subqueries, no `SELECT *`, explicit column lists
- **TypeScript:** strict mode, explicit return types on exported functions
- **Git:** conventional commits (`feat:`, `fix:`, `chore:`, `docs:`)
- **Testing:** pytest for Python, Vitest for TypeScript, aim for >80% coverage on services
- **API design:** RESTful, Pydantic schemas for all request/response bodies, consistent error format
- **Database:** UUID primary keys, `created_at`/`updated_at` timestamps on all tables, soft deletes where appropriate

## Development Environment

```bash
# Start everything
docker compose up -d

# Run migrations
make migrate

# Seed default data (cookie categories, known cookies)
make seed

# Run tests
make test

# Lint
make lint
```

Services in Docker Compose:
- `api` — FastAPI on port 8000
- `scanner` — Playwright scanner service
- `postgres` — PostgreSQL 16 on port 5432
- `redis` — Redis on port 6379
- `admin-ui` — Vite dev server on port 5173 (also serves the banner scripts)

## Implementation Phases

| Phase | Scope |
|-------|-------|
| 1 (Weeks 1–3) | DB schema, FastAPI scaffold, auth, site CRUD, basic banner, consent API, Docker Compose |
| 2 (Weeks 4–6) | TCF v2.2, Google Consent Mode v2, script interceptor/auto-blocking, cookie categories, allow-list, config hierarchy, admin UI scaffold |
| 3 (Weeks 7–8) | Playwright crawler, auto-categorisation, client-side reporter, scan scheduling, admin UI for scans |
| 4 (Weeks 9–10) | Compliance rule engine (GDPR/CNIL/CCPA/ePrivacy/LGPD), consent analytics API, compliance + analytics admin UI |
| 5 (Weeks 11–12) | Banner builder (visual editor), all display modes, full i18n, a11y audit, GeoIP, multi-domain, Helm chart, security hardening, load testing |

## Key External Standards

- **IAB TCF v2.2:** [IAB TCF Technical Specification](https://github.com/InteractiveAdvertisingBureau/GDPR-Transparency-and-Consent-Framework/blob/master/TCFv2/IAB%20Tech%20Lab%20-%20Consent%20string%20and%20vendor%20list%20formats%20v2.md)
- **Google Consent Mode v2:** [Google Developer Docs](https://developers.google.com/tag-platform/security/guides/consent)
- **Global Vendor List (GVL):** Loaded from IAB, cached, updated regularly
- **WCAG 2.1 AA:** Accessibility target for the banner UI
