# Staying up to date

The admin UI shows a notice when a newer ConsentOS release is available.
This page explains how to upgrade to it.

Releases are published to GHCR, tagged with the version and `latest`:

- `ghcr.io/consentos/consentos-api`
- `ghcr.io/consentos/consentos-scanner`
- `ghcr.io/consentos/consentos-admin-ui`

See the [release notes](https://github.com/ConsentOS/consentos/releases)
for what changed before upgrading.

## Docker Compose

Pin the image tag to the new version (or use `latest`), then pull and
recreate:

```bash
docker compose pull
docker compose up -d
```

Apply any new database migrations after the API container is up:

```bash
docker compose exec api alembic upgrade head
```

## Helm / Kubernetes

Bump the image tag (and chart `appVersion`) to the new release and roll
it out:

```bash
helm upgrade consentos ./helm/consentos --set image.tag=<version>
```

Migrations run via the chart's pre-upgrade hook; check the release notes
for any manual steps.

## After upgrading

Reload the admin UI and confirm the footer shows the new version and the
update notice has cleared.
