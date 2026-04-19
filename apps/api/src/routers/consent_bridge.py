"""Cross-domain consent bridge served as an iframe.

The banner embeds ``<iframe src="{apiBase}/consent-bridge?group={id}">``
when cross-domain consent sharing is enabled on the site group. The
iframe page reads/writes a ``_consentos_xd_{group_id}`` cookie on the
API's own domain and communicates the consent state back to the parent
page via ``postMessage``.

Flow:
  1. Parent banner embeds iframe with ``?group=<site_group_id>``
  2. Iframe reads its ``_consentos_xd_<group>`` cookie
  3. If consent exists → postMessage ``{type: 'consentos:xd-consent', consent: {...}}``
  4. If not → postMessage ``{type: 'consentos:xd-consent', consent: null}``
  5. When parent gives consent → postMessage
     ``{type: 'consentos:xd-store', consent: {...}}``
  6. Iframe writes cookie → replies ``{type: 'consentos:xd-stored'}``
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["consent-bridge"])

# Minimal inline HTML served inside the iframe. No external
# dependencies, no tracking — just cookie read/write + postMessage.
_BRIDGE_HTML = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
<script>
(function() {
  var params = new URLSearchParams(location.search);
  var group = params.get('group');
  if (!group) return;

  var COOKIE = '_consentos_xd_' + group;

  function readCookie() {
    var match = document.cookie.split('; ').find(function(r) {
      return r.startsWith(COOKIE + '=');
    });
    if (!match) return null;
    try { return JSON.parse(decodeURIComponent(match.split('=')[1])); }
    catch(e) { return null; }
  }

  function writeCookie(data, days) {
    var value = encodeURIComponent(JSON.stringify(data));
    var expires = new Date(Date.now() + (days || 365) * 86400000).toUTCString();
    var secure = location.protocol === 'https:' ? '; Secure' : '';
    document.cookie = COOKIE + '=' + value +
      '; path=/; expires=' + expires + '; SameSite=None' + secure;
  }

  // Send existing consent to the parent immediately.
  var existing = readCookie();
  parent.postMessage({
    type: 'consentos:xd-consent',
    consent: existing
  }, '*');

  // Listen for consent storage requests from the parent.
  window.addEventListener('message', function(e) {
    if (!e.data || e.data.type !== 'consentos:xd-store') return;
    writeCookie(e.data.consent, e.data.expiryDays || 365);
    parent.postMessage({ type: 'consentos:xd-stored' }, '*');
  });
})();
</script>
</body>
</html>
"""


@router.get("/consent-bridge", response_class=HTMLResponse)
async def consent_bridge() -> str:
    """Serve the cross-domain consent bridge iframe page.

    Public endpoint — no authentication required. The page is a
    minimal inline script that reads/writes a per-group cookie on
    the API domain and relays consent state via postMessage.
    """
    return _BRIDGE_HTML
