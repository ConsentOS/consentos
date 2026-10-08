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

## Upgrade notes

### Banner config and link validation

The site, site group and organisation config endpoints now validate
banner colours, fonts and link URLs. Values already stored are not
changed, but the next save of the settings, site group or site config
page returns `422` until any of the following are corrected:

- `privacy_policy_url` or `terms_url` without a scheme, such as
  `www.example.com/privacy`. Use `https://www.example.com/privacy`.
- `privacy_policy_url` or `terms_url` set to a bare file name
  (`privacy.html`), a fragment (`#privacy`), a protocol-relative URL
  (`//example.com/privacy`) or a `mailto:` link. Use an absolute
  `http(s)` URL or a path starting with a single `/`.
- Banner colour or font values containing `;`, `{`, `}`, `<`, `>`, `\`,
  `/*`, `*/` or `url(`, control characters, quotes in a colour, or an
  unclosed quote in a font. Any other CSS value up to 200 characters is
  accepted, including `var(--brand)`, `oklch()` and `color-mix()`.

Translations are now rendered as plain text. HTML in a translated
string is shown as written rather than as markup; use `[text](url)` for
links.
