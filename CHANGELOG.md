# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v0.2.0] - 2026-06-12
### :sparkles: New Features
- [`142e237`](https://github.com/ConsentOS/consentos/commit/142e2373d3c788c683f0e3a060bc398c22022741) - consent records page, tab persistence, and snippet copy fix *(PR [#9](https://github.com/ConsentOS/consentos/pull/9) by [@jamescottrill](https://github.com/jamescottrill))*
- [`d8e0a34`](https://github.com/ConsentOS/consentos/commit/d8e0a34e043db0603f16f756ccb0fe914ac2e4f1) - account management — change email, password, and CLI reset *(PR [#10](https://github.com/ConsentOS/consentos/pull/10) by [@jamescottrill](https://github.com/jamescottrill))*
- [`fc35e5b`](https://github.com/ConsentOS/consentos/commit/fc35e5b56434345fe58e7e71942b10dcb1e2dfa7) - cross-domain consent sharing via iframe bridge *(PR [#12](https://github.com/ConsentOS/consentos/pull/12) by [@jamescottrill](https://github.com/jamescottrill))*
- [`9700b79`](https://github.com/ConsentOS/consentos/commit/9700b796322ced467fa1ab8f3bf0cec018adaea7) - hosted cookie page, JS SDK, and bundle-on-every-page *(PR [#13](https://github.com/ConsentOS/consentos/pull/13) by [@jamescottrill](https://github.com/jamescottrill))*
- [`110dd93`](https://github.com/ConsentOS/consentos/commit/110dd93e58208439279ba222c7a9c4f762e56694) - anonymous telemetry heartbeat *(PR [#14](https://github.com/ConsentOS/consentos/pull/14) by [@jamescottrill](https://github.com/jamescottrill))*
- [`8e1b59d`](https://github.com/ConsentOS/consentos/commit/8e1b59d6f561c253a28d924911094148edce9284) - TCF v2.3 - end-to-end upgrade *(PR [#26](https://github.com/ConsentOS/consentos/pull/26) by [@jamescottrill](https://github.com/jamescottrill))*
- [`1aaf9a3`](https://github.com/ConsentOS/consentos/commit/1aaf9a3af7990bb8df6360d6a44696f7ad5c4eb6) - default Cloudflare GEOIP headers in .env.example *(PR [#30](https://github.com/ConsentOS/consentos/pull/30) by [@jamescottrill](https://github.com/jamescottrill))*
- [`b5e6a45`](https://github.com/ConsentOS/consentos/commit/b5e6a45b825e45f754a6ddba93c6e0638ebb7fad) - **admin-ui**: site deletion from the overview tab *(PR [#31](https://github.com/ConsentOS/consentos/pull/31) by [@jamescottrill](https://github.com/jamescottrill))*
- [`29bf36d`](https://github.com/ConsentOS/consentos/commit/29bf36ddbee46cbb8ef694a41a5a7a0b391c3e74) - multi-region consent settings (banner + admin editor) *(PR [#32](https://github.com/ConsentOS/consentos/pull/32) by [@jamescottrill](https://github.com/jamescottrill))*
- [`f99ea84`](https://github.com/ConsentOS/consentos/commit/f99ea84a699e052438dad071b1a1eeb683401e8c) - **banner**: honour blocking_mode at runtime (opt_out / informational) *(PR [#34](https://github.com/ConsentOS/consentos/pull/34) by [@jamescottrill](https://github.com/jamescottrill))*
- [`74806c5`](https://github.com/ConsentOS/consentos/commit/74806c5ea3f0e04a32a61f45b9ce653b3585c643) - **banner**: render logo, overlay backdrop & width; tidy builder UX *(PR [#36](https://github.com/ConsentOS/consentos/pull/36) by [@cmaerz](https://github.com/cmaerz))*
- [`e388d38`](https://github.com/ConsentOS/consentos/commit/e388d38aa0dfc2a02d4ca3547a748ce85ffb8179) - **admin**: preview the banner in configured languages *(PR [#37](https://github.com/ConsentOS/consentos/pull/37) by [@cmaerz](https://github.com/cmaerz))*

### :bug: Bug Fixes
- [`e0f1dd4`](https://github.com/ConsentOS/consentos/commit/e0f1dd43e82ad39d3bee174a9bf081cd97b704e0) - **scanner**: reliable cookie discovery, auto-categorisation, and scan scheduling UI *(PR [#7](https://github.com/ConsentOS/consentos/pull/7) by [@jamescottrill](https://github.com/jamescottrill))*
- [`30f786b`](https://github.com/ConsentOS/consentos/commit/30f786b82b6888222762250e3af318c9fd03dcf1) - **quickstart**: make seed provisions initial admin *(PR [#28](https://github.com/ConsentOS/consentos/pull/28) by [@jamescottrill](https://github.com/jamescottrill))*
- [`efa7f4a`](https://github.com/ConsentOS/consentos/commit/efa7f4a864e2f36c68dc974dd3c45a0df2ebd89f) - **api**: relax CSP on /docs, /redoc, /openapi.json *(PR [#27](https://github.com/ConsentOS/consentos/pull/27) by [@jamescottrill](https://github.com/jamescottrill))*
- [`d5293ac`](https://github.com/ConsentOS/consentos/commit/d5293acb9f1abce15d0d919f545e59e362a3b24a) - **api**: make Reset to inherited work for scalar config fields *(PR [#39](https://github.com/ConsentOS/consentos/pull/39) by [@jamescottrill](https://github.com/jamescottrill))*
- [`4ec57e8`](https://github.com/ConsentOS/consentos/commit/4ec57e8711b5c1ea042ab5d3bdd5eb53a8503b28) - **banner**: render the cookie count on the live banner *(PR [#38](https://github.com/ConsentOS/consentos/pull/38) by [@cmaerz](https://github.com/cmaerz))*

### :wrench: Chores
- [`bebcf90`](https://github.com/ConsentOS/consentos/commit/bebcf901f406e7fe87cf783b1f4820eabe00319f) - remove compliance UI from admin dashboard *(PR [#8](https://github.com/ConsentOS/consentos/pull/8) by [@jamescottrill](https://github.com/jamescottrill))*
- [`9c4daca`](https://github.com/ConsentOS/consentos/commit/9c4daca2249d38924465828ab263858dd84b4220) - bump Postgres to 17 in dev, test, helm *(PR [#29](https://github.com/ConsentOS/consentos/pull/29) by [@jamescottrill](https://github.com/jamescottrill))*
- [`3b80290`](https://github.com/ConsentOS/consentos/commit/3b8029050f2edcb473411ccd47c492bc3fca3646) - **ci**: authenticate release workflow as the deploy key *(PR [#40](https://github.com/ConsentOS/consentos/pull/40) by [@jamescottrill](https://github.com/jamescottrill))*


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
[v0.2.0]: https://github.com/ConsentOS/consentos/compare/0.1.0...v0.2.0
