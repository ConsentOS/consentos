# Staying up to date

The admin dashboard shows a notice when a newer ConsentOS release is
available, with the running version in the footer. Follow the steps
below for your deployment method.

Releases are published to GHCR as `ghcr.io/consentos/consentos-api`,
`...-scanner`, and `...-admin-ui`, tagged with the version and `latest`.

## Docker Compose

1. Read the [release notes](https://github.com/ConsentOS/consentos/releases)
   for the new version.
2. Pin the image tag in your `docker-compose.yml` to the new version (or
   leave it tracking `latest`).
3. Pull the new images and recreate the containers:

   ```bash
   docker compose pull
   docker compose up -d
   ```

4. Reload the admin dashboard. The footer should show the new version
   and the update notice should be gone.

## Helm / Kubernetes

1. Read the [release notes](https://github.com/ConsentOS/consentos/releases)
   for the new version.
2. Bump the image tag and roll out the release:

   ```bash
   helm upgrade consentos ./helm/consentos --set image.tag=<version>
   ```

3. Reload the admin dashboard. The footer should show the new version
   and the update notice should be gone.
