# Setting up a site

An organisation with no sites yet sees **Add your first site** on the **Sites** page, with the form ready to fill in. Adding a site opens it with a **setup checklist** on its **Overview**, which takes it from nothing to a working banner. The site's first cookie scan starts as soon as it is added.

| Step | Done when |
| --- | --- |
| **Scan your site** | A scan has finished. The step shows the scan's progress while it runs, and offers to start it again if it didn't finish. See [Cookie scanning](scanning.md). |
| **Review cookies** | No cookie found on the site is still waiting for a category. |
| **Set up your banner** | You've saved the **Banner** or **Categories** tab, chosen **Looks good**, or published. |
| **Preview and publish** | The site has a published configuration. Only owners and admins can publish. See [Publishing configuration](publishing.md). |
| **Install on your site** | The banner has been seen on one of the site's pages, or a check found it. See [Installing the banner](installing.md). |
| **Check it's working** | A check passed, or the banner has been seen on the site since the live version was published. |

Configuring and publishing come before installing, so visitors see your real banner from the first page they load, not the built-in one.

Each step is worked out from the site itself, so steps can be done in any order, and the checklist stays right after a reload or when someone else does a step. Once every step is done, **Dismiss** hides the checklist for everyone. The **Sites** list shows how far through setup each site is until then.

Sites that were already published before the checklist existed don't show it.

## Through the API

| Request | What it does |
| --- | --- |
| `GET /api/v1/sites/{site_id}/setup` | Each step with its `status` (`todo`, `in_progress` or `done`) and a description. |
| `POST /api/v1/sites/{site_id}/setup/banner-confirmed` | Marks the banner step done. |
| `POST /api/v1/sites/{site_id}/setup/dismiss` | Hides the checklist. Returns `409` until every step is done. |
| `GET /api/v1/sites/setup-summary` | How many steps each site in the organisation has done. |
