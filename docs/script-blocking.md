# Deferring scripts until consent

The consent loader holds back scripts that belong to a category the
visitor has not accepted, and runs them once that category is granted.
This page explains how to tag scripts so they are deferred reliably, and
what the automatic matching can and cannot handle.

## Recommended: tag scripts in the page HTML

The most reliable way to defer a script is to mark it in your page
markup with `type="text/plain"` and a `data-category` attribute:

```html
<script type="text/plain" data-category="analytics"
        src="https://www.example-analytics.com/tag.js" async></script>

<script type="text/plain" data-category="marketing">
  exampleTracker('init', 'ABC-123');
</script>
```

Browsers do not run `text/plain` scripts, so a tagged script stays inert
however early it appears on the page and whatever loads it. When the
visitor accepts the category, ConsentOS replaces each tagged script with
a live copy that keeps its other attributes (`src`, `async`,
`crossorigin` and so on). Returning visitors who already accepted the
category get the live copy as soon as the tag is parsed.

Valid categories are `necessary`, `functional`, `analytics`, `marketing`
and `personalisation`. Scripts tagged `necessary` are never held back:
they are made live as soon as the tag is parsed.

Place the consent loader `<script>` tag before any tagged scripts, as
high in `<head>` as possible.

## Automatic matching

For scripts you have not tagged, the loader also matches script URLs
against built-in patterns for common analytics, advertising and chat
services. It checks scripts at the point they are inserted, whether
added by the HTML parser or by other scripts (for example via
`appendChild`, `insertBefore`, `append`, `replaceChildren` or a
`DocumentFragment`), and when a script's `src` or `type` is set.
Scripts with an unrecognised URL and no `data-category` are allowed to
run.

## Limitations

Automatic matching works from a script's URL or its `data-category`
attribute, so some patterns cannot be deferred without tagging:

- **Inline code injected at runtime.** A script element created with
  inline code and no `data-category` has nothing to match on, so it
  runs immediately.
- **`document.write`.** Markup written with `document.write` is handled
  by the parser in ways that cannot be fully intercepted.
- **Shadow DOM.** Scripts the parser places inside a shadow root (for
  example through declarative shadow DOM) are not seen by the loader.
  Keep scripts that need deferring in the main document, tagged with
  `type="text/plain"` and `data-category`.
- **Code already running.** A script that ran before the loader, or was
  allowed to run, can still set cookies directly. The loader removes
  known non-consented cookies and storage keys, but tagging the script
  is the dependable fix.

If a third-party tag relies on any of these, tag its loader script in
your HTML as shown above so nothing from it runs before consent.
