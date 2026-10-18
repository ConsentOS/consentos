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

Open your site in a private window. You should see your banner, or the built-in banner if you haven't published the site's configuration yet. See [Publishing configuration](publishing.md).
