# Cookie scanning

The scanner loads a site's pages in a headless browser and records every cookie and storage item they set, with the script that set it. Scan results feed the site's cookie list, where you review and categorise what was found.

## When a site is scanned

- **When the site is added.** The first scan starts as soon as a site is created, so its cookies are ready to review by the time you get to them. If the scan can't be queued, the site is still created and the scan shows as failed on the **Scans** tab, where you can start it again.
- **When you ask.** **Trigger Scan** on the **Scans** tab starts a scan straight away.
- **On a schedule.** Choose a schedule on the **Scans** tab and the site is rescanned automatically. A scheduled scan is skipped if one is already running.

A site only runs one scan at a time.

## Following a scan

While a scan is running, the **Scans** tab shows how many pages have been scanned out of the total found, and how many cookies have been found so far. The page updates on its own, and the cookie list refreshes when the scan finishes. Nothing is polled while no scan is running.

## Which pages are scanned

The scanner reads the site's sitemap to find pages (also looking for one listed in `robots.txt`), up to the site's page limit of 50 by default. When there is no sitemap, it scans the home page and a few common paths. It only loads pages on the site's domain and its additional domains.

## Through the API

| Request | What it does |
| --- | --- |
| `POST /api/v1/sites/` | Creates a site and starts its first scan. Send `"start_scan": false` to skip it. |
| `POST /api/v1/scanner/scans` | Starts a scan. Returns `409` if one is already running for the site. |
| `GET /api/v1/scanner/scans/site/{site_id}` | Lists a site's scans, newest first, with `status`, `pages_scanned`, `pages_total` and `cookies_found`. |

A scan's `trigger` is `initial` for the first scan, `manual`, `scheduled`, or `client_report`.
