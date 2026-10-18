# Publishing configuration

Changes to a site's configuration don't reach visitors as you save them.
They build up in a **draft**, and you **publish** the draft when it's
ready. Each publish creates a numbered **revision** (v1, v2, ...), and the
latest one is **live**: it's what the banner is served.

This means a mistaken edit never goes live by accident, you can review
exactly what will change before it does, and you can go back to any
earlier version.

## What goes in the draft

Everything the banner uses:

- the site's settings, banner design and categories
- translations
- cookie classifications, review decisions and the allow-list
- organisation and site group defaults the site inherits

Scan settings aren't part of it, and the scanner still records newly found
cookies straight away. A new cookie only affects what visitors see once
it's classified and published.

## In the admin UI

While a site's draft differs from what visitors see, every tab of the site
shows a bar: **Unpublished changes since vN**. It also appears when
organisation or site group defaults have changed since the live version.

**Review and publish** lists every change, grouped by area. Changes that
come from organisation or site group defaults are labelled with where they
came from. Add an optional note and publish.

If someone saves another change while you're reviewing, the publish is
refused so that you never publish something you haven't seen. Review the
latest changes and publish again.

### Asking visitors to consent again

Publishing keeps the consent visitors have already given, so a wording or
colour change doesn't prompt anyone again. When a change affects what
visitors consented to (the categories shown, the TCF purposes or the
disclosed vendors), the publish dialog ticks **Ask visitors to consent
again** for you and says why. You can untick it.

### History and rollback

The **History** tab lists every revision with who published it, when, its
note, and whether it asked visitors again. Pick any two to compare them.

**Roll back** makes an earlier revision live again. It's added to the
history as a new revision ("Rollback to v2"), so nothing is lost. Your
unpublished changes are kept.

### Discarding changes

**Discard changes** puts the site's own settings, translations and cookie
rules back to the live revision. Changes inherited from organisation or
site group defaults can't be discarded from a site; change them where they
were made, or publish them.

### Changing defaults for many sites

After changing organisation or site group defaults, the settings page lists
the sites with unpublished changes. **Publish all affected sites**
publishes each as its own revision with one note. If one site fails, the
others still publish, and the results say which failed and why.

### Previewing on your site

**Preview on your site** in the review dialog opens your real site with the
draft applied. Only you see it, through a link that expires after 30
minutes. Nothing is saved or recorded as consent while previewing. To end a
preview early, open any page of the site with `?consentos_preview=off`.

### New sites

A new site has nothing live until its first publish. Until then the banner
uses its built-in defaults and the site list marks it **Not yet
published**.

### Who can publish

Editors can change the draft. Owners and admins can publish, bulk publish,
roll back, discard and create preview links. Viewers can see the draft, the
changes and the history.

## Consent records

Each consent record notes the revision the visitor saw and its consent
version, shown as **Configuration** on the record. Records made before
revisions existed show **Not recorded**.

## Using the API

Writing configuration through the API (`PUT` and `PATCH
/sites/{id}/config`, organisation and site group config, translations and
cookie rules) changes the draft only. Publish to make it live.

```bash
API=https://cmp.example.com/api/v1
AUTH="Authorization: Bearer <token>"

# What would a publish change? ``to.content_hash`` identifies this draft.
curl -s "$API/config/sites/<site-id>/diff" -H "$AUTH"

# Publish exactly that draft. Refused with 409 if it has changed since.
curl -s -X POST "$API/config/sites/<site-id>/publish" -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"expected_content_hash": "<to.content_hash>", "note": "New privacy policy"}'
```

| Endpoint | What it does |
| --- | --- |
| `GET /config/sites/{id}/draft` | Whether there are unpublished changes, the draft's hash, the live revision and the last publish attempt |
| `GET /config/sites/{id}/diff` | Changes between the live revision and the draft, or between `from_revision` and `to_revision` |
| `POST /config/sites/{id}/publish` | Publish the draft. Body: `expected_content_hash`, optional `note` and `ask_visitors_again` |
| `GET /config/sites/{id}/revisions` | Revision history, newest first (`limit`, `offset`) |
| `GET /config/sites/{id}/revisions/{revision_id}` | One revision, including what it serves |
| `POST /config/sites/{id}/revisions/{revision_id}/rollback` | Make an earlier revision live again. Body: optional `ask_visitors_again` |
| `POST /config/sites/{id}/discard` | Put the site's own values back to the live revision |
| `GET /config/affected-sites` | Published sites with unpublished changes, optionally for one `site_group_id` |
| `POST /config/bulk-publish` | Publish several sites. Body: `sites` (each `site_id` and `expected_content_hash`), optional `note` and `ask_visitors_again` |
| `POST /config/sites/{id}/preview` | Create a preview link for the draft |

A refused publish, rollback or discard returns `409` with the reason in
`detail`, and `404` for a revision that isn't the site's. The banner's
config endpoint, `GET /config/sites/{id}/geo-resolved`, serves the live
revision and returns `404` for a site that hasn't been published.
