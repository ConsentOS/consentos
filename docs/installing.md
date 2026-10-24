# Installing the banner

Each site's **Overview** in the admin UI shows **Install on your site**: the script tag for that site, with instructions for any site, WordPress and Shopify, and a copy button.

The tag looks like this:

```html
<script src="https://cmp.example.com/consent-loader.js"
        data-site-id="<site-id>"
        data-api-base="https://cmp.example.com"></script>
```

When the banner is served from a different address to the API, the tag also has `data-cdn-base`, which tells the loader where to fetch the rest of the banner. The admin UI works this out from the deployment's settings. See `CDN_BASE_URL` and `PUBLIC_API_URL` in the [deployment guide](deployment-guide.md#cdn--banner).

## Where it goes

The tag must be the **first `<script>` in `<head>`**, on every page, with no `async` or `defer`. The banner holds back other scripts and cookies until the visitor consents, so anything that runs before it can set cookies first.

### Any site

Paste the tag into your page template's `<head>`, before any other script.

### WordPress

Use a plugin for adding code to your site's header, such as WPCode, and paste the tag as the first thing in its header section. Or paste it straight after `<head>` in your theme's `header.php`.

If you use a caching or optimisation plugin that delays or combines JavaScript, exclude `consent-loader.js` from it.

### Shopify

In your Shopify admin, go to **Online Store** then **Themes**, open the menu next to your live theme and choose **Edit code**. Open `layout/theme.liquid`, paste the tag on the line straight after `<head>`, and save. Repeat for any other theme you publish.

## Domains

The banner only works on the site's domain, its additional domains and their subdomains. Consent from any other domain is rejected. The install guide lists the domains for the site.

## Checking it worked

Each site's **Overview** shows whether the banner is installed:

| State | Meaning |
| --- | --- |
| **Not detected** | The banner hasn't loaded on any of the site's pages yet. |
| **Installed** | The banner has loaded on one of the site's pages. The Overview shows when and where it was last seen. |
| **Problem found** | The last check found something wrong, and the banner hasn't been seen since. |

The **Sites** list shows the same state for each site.

### Automatic detection

The site is marked installed the first time a page on one of its domains loads the banner, usually within a minute. Pages on other domains don't count, so a copy of the snippet on another site doesn't mark yours installed. Only the page's address is kept, never its query string. Detection happens after the banner has been sent its configuration, so it doesn't slow the banner down.

### Check now

**Check now** loads the site's home page as a first-time visitor and reports on each of these:

| Check | What it means when it fails |
| --- | --- |
| The page loads | The page couldn't be reached from the internet, or returned an error. |
| The page is on one of this site's domains | The page redirected to a domain that isn't registered for the site, so the banner won't run there. |
| The ConsentOS script is on the page | `consent-loader.js` isn't in the page. A loader added by a tag manager still counts. |
| The script has this site's ID | `data-site-id` belongs to another site. |
| The script points at this ConsentOS server | `data-api-base` isn't this deployment's API. Only checked when `PUBLIC_API_URL` is set. |
| The script isn't loaded asynchronously | The tag has `async` or `defer`, so other scripts can run before it. |
| The script is the first in `<head>` | Another script runs before it, or it's outside `<head>`. |
| The banner fetched its settings | The banner couldn't reach the API, often because of the page's content security policy. |
| The banner appeared | The script ran but the banner didn't show. |
| This site's configuration is published | A warning only: visitors see the built-in banner until you publish. |

Each failure comes with a fix. The result is kept, so the next person to open the site sees it too. Owners, admins and editors can run a check.
