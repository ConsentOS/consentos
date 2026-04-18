# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-18

Initial public release of ConsentOS.

### Added

- **API:** FastAPI backend with JWT authentication, org/site CRUD, consent recording, analytics, and compliance checking
- **Banner:** Lightweight consent banner script (~2KB loader + ~25KB bundle) with Shadow DOM isolation, auto-blocking, IAB TCF v2.2, and Google Consent Mode v2
- **Scanner:** Playwright-based cookie crawler with auto-categorisation and dark pattern detection
- **Admin UI:** React dashboard with site management, cookie manager, banner builder, compliance checker, and analytics
- **Known cookies:** Seeded from the [Open Cookie Database](https://github.com/jkwakman/Open-Cookie-Database) (2,200+ patterns)
- **Compliance:** Rule-based engine covering GDPR, CNIL, CCPA/CPRA, ePrivacy, and LGPD
- **Infrastructure:** Docker Compose (dev/test/prod), Helm chart, Ansible playbooks
- **CI:** GitHub Actions pipeline with linting, testing, type checking, and bundle size checks
