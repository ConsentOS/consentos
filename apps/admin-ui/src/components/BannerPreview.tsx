import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { BannerConfig, ButtonConfig } from '../types/api';

type DisplayMode = 'bottom_banner' | 'top_banner' | 'overlay' | 'corner_popup';
type CornerPosition = 'left' | 'right';
type Viewport = 'desktop' | 'mobile';

/* ── Default text values ─────────────────────────────────────────────── */

const DEFAULT_TITLE = 'We use cookies';
const DEFAULT_DESCRIPTION =
  'We use cookies and similar technologies to enhance your browsing experience, ' +
  'analyse site traffic, and personalise content. You can choose which categories to allow.';
const DEFAULT_ACCEPT_ALL = 'Accept all';
const DEFAULT_REJECT_ALL = 'Reject all';
const DEFAULT_MANAGE_PREFERENCES = 'Manage preferences';
const DEFAULT_SAVE_PREFERENCES = 'Save preferences';

interface Props {
  bannerConfig: BannerConfig;
  displayMode: DisplayMode;
  cornerPosition?: CornerPosition;
  viewport: Viewport;
  privacyPolicyUrl: string | null;
  siteUrl?: string | null;
  previewLocale?: string;
}

export default function BannerPreview({
  bannerConfig,
  displayMode,
  cornerPosition = 'right',
  viewport,
  privacyPolicyUrl,
  siteUrl,
  previewLocale,
}: Props) {
  const [iframeLoadFailed, setIframeLoadFailed] = useState(false);
  const [iframeLoaded, setIframeLoaded] = useState(false);
  const siteIframeRef = useRef<HTMLIFrameElement>(null);
  const bannerSrcdoc = useMemo(
    () => buildBannerOnlyHtml(bannerConfig, displayMode, cornerPosition, privacyPolicyUrl, previewLocale),
    [bannerConfig, displayMode, cornerPosition, privacyPolicyUrl, previewLocale],
  );
  const fallbackSrcdoc = useMemo(
    () => buildPreviewHtml(bannerConfig, displayMode, cornerPosition, privacyPolicyUrl, previewLocale),
    [bannerConfig, displayMode, cornerPosition, privacyPolicyUrl, previewLocale],
  );

  const fullSiteUrl = useMemo(() => {
    if (!siteUrl) return null;
    // Ensure the URL has a protocol
    if (siteUrl.startsWith('http://') || siteUrl.startsWith('https://')) return siteUrl;
    return `https://${siteUrl}`;
  }, [siteUrl]);

  // Reset state when the site URL changes
  useEffect(() => {
    setIframeLoadFailed(false);
    setIframeLoaded(false);
  }, [fullSiteUrl]);

  const handleSiteIframeLoad = useCallback(() => {
    // Check if the iframe actually loaded content by trying to access it
    // If X-Frame-Options or CSP blocks it, the iframe will be blank
    const iframe = siteIframeRef.current;
    if (!iframe) return;

    try {
      // Try to detect if the iframe loaded — accessing contentDocument will throw
      // for cross-origin frames, but that's fine (it means it loaded)
      // If the iframe is blank/error, some browsers fire load anyway
      const doc = iframe.contentDocument;
      if (doc && doc.body && doc.body.innerHTML === '') {
        // Empty body might mean it was blocked
        setIframeLoadFailed(true);
      } else {
        setIframeLoaded(true);
      }
    } catch {
      // Cross-origin — means the site loaded successfully
      setIframeLoaded(true);
    }
  }, []);

  const handleSiteIframeError = useCallback(() => {
    setIframeLoadFailed(true);
  }, []);

  const width = viewport === 'mobile' ? 375 : '100%';
  const useLiveSite = fullSiteUrl && !iframeLoadFailed;

  return (
    <div
      className="relative overflow-hidden rounded-lg border border-border bg-mist"
      style={{ height: 500 }}
      data-testid="banner-preview"
    >
      {useLiveSite ? (
        <>
          {/* Live site iframe (background) */}
          <iframe
            ref={siteIframeRef}
            src={fullSiteUrl}
            title="Site preview"
            sandbox="allow-scripts allow-same-origin"
            onLoad={handleSiteIframeLoad}
            onError={handleSiteIframeError}
            style={{
              width,
              height: '100%',
              border: 'none',
              margin: viewport === 'mobile' ? '0 auto' : undefined,
              display: 'block',
              transition: 'width 0.3s ease',
              opacity: iframeLoaded ? 1 : 0.3,
            }}
          />
          {/* Banner overlay on top of the live site */}
          <iframe
            srcDoc={bannerSrcdoc}
            sandbox="allow-scripts"
            title="Banner preview"
            style={{
              position: 'absolute',
              inset: 0,
              width: viewport === 'mobile' ? 375 : '100%',
              height: '100%',
              border: 'none',
              margin: viewport === 'mobile' ? '0 auto' : undefined,
              pointerEvents: 'none',
              background: 'transparent',
            }}
          />
          {!iframeLoaded && (
            <div className="absolute inset-0 flex items-center justify-center bg-mist/80">
              <p className="text-sm text-text-secondary">Loading site preview…</p>
            </div>
          )}
        </>
      ) : (
        /* Fallback: self-contained preview with placeholder content */
        <iframe
          srcDoc={fallbackSrcdoc}
          sandbox="allow-scripts"
          title="Banner preview"
          style={{
            width,
            height: '100%',
            border: 'none',
            margin: viewport === 'mobile' ? '0 auto' : undefined,
            display: 'block',
            transition: 'width 0.3s ease',
          }}
        />
      )}

      {iframeLoadFailed && fullSiteUrl && (
        <div className="absolute bottom-2 left-2 rounded bg-status-warning-bg px-2 py-1 text-xs text-status-warning-fg ring-1 ring-status-warning-fg/20">
          Could not load site preview — the site may block iframe embedding
        </div>
      )}
    </div>
  );
}

/* ── Banner-only HTML (transparent background, overlay on live site) ── */

function buildBannerOnlyHtml(
  bc: BannerConfig,
  displayMode: DisplayMode,
  cornerPosition: CornerPosition,
  privacyUrl: string | null,
  previewLocale?: string,
): string {
  const bg = bc.backgroundColour ?? '#ffffff';
  const text = bc.textColour ?? '#1a1a2e';
  const primary = bc.primaryColour ?? '#2563eb';
  const font = bc.fontFamily ?? 'system-ui';
  const radius = bc.borderRadius ?? 6;

  const positionStyles = getPositionStyles(displayMode, cornerPosition, radius, bc.bannerWidth);
  const { rejectBtn, manageBtn, acceptBtn, closeBtn, logoHtml, cookieCount, privacyLink, titleText, descriptionText } =
    buildBannerParts(bc, primary, text, radius, privacyUrl);

  const fontLink = bc.customFontUrl
    ? `<link rel="stylesheet" href="${escapeHtml(bc.customFontUrl)}">`
    : '';

  const langAttr = previewLocale ? escapeHtml(previewLocale) : 'en';

  return `<!DOCTYPE html>
<html lang="${langAttr}">
<head>
<meta charset="utf-8">
${fontLink}
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; background: transparent; }

  .consentos-banner {
    ${positionStyles}
    background: ${bg};
    color: ${text};
    font-family: ${font}, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.12);
    border: 1px solid rgba(0, 0, 0, 0.1);
    border-radius: ${displayMode === 'overlay' || displayMode === 'corner_popup' ? radius + 'px' : '0'};
    pointer-events: auto;
  }

  .consentos-banner__content {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px 24px;
    position: relative;
  }

  .cmp-logo { width: auto; max-width: 100%; margin-bottom: 10px; display: block; }
  .consentos-banner__title { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
  .consentos-banner__description { margin-bottom: 16px; opacity: 0.85; }
  .consentos-banner__link { color: ${primary}; text-decoration: underline; }
  .cmp-cookie-count { display: block; font-size: 12px; opacity: 0.6; margin-bottom: 12px; }
  .consentos-banner__actions { display: flex; gap: 10px; flex-wrap: wrap; }

  .cmp-btn {
    padding: 10px 20px;
    border-radius: ${radius}px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    font-family: inherit;
  }

  .cmp-close {
    position: absolute; top: 12px; right: 12px;
    background: none; border: none; font-size: 22px;
    cursor: pointer; color: ${text}; opacity: 0.5; line-height: 1;
  }

  .cmp-overlay-bg {
    display: ${displayMode === 'overlay' && bc.showOverlayBackdrop !== false ? 'block' : 'none'};
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.4);
    z-index: 2147483646;
  }

  @media (max-width: 640px) {
    .consentos-banner__actions { flex-direction: column; }
    .cmp-btn { width: 100%; text-align: center; }
  }
</style>
</head>
<body>
  <div class="cmp-overlay-bg"></div>
  <div class="consentos-banner" role="dialog" aria-label="Cookie consent">
    <div class="consentos-banner__content">
      ${closeBtn}
      ${logoHtml}
      <p class="consentos-banner__title">${escapeHtml(titleText)}</p>
      <p class="consentos-banner__description">
        ${escapeHtml(descriptionText)}${privacyLink}
      </p>
      ${cookieCount}
      <div class="consentos-banner__actions">
        ${rejectBtn}
        ${manageBtn}
        ${acceptBtn}
      </div>
    </div>
  </div>
</body>
</html>`;
}

/* ── Full preview HTML (with placeholder page content, used as fallback) ── */

function buildPreviewHtml(
  bc: BannerConfig,
  displayMode: DisplayMode,
  cornerPosition: CornerPosition,
  privacyUrl: string | null,
  previewLocale?: string,
): string {
  const bg = bc.backgroundColour ?? '#ffffff';
  const text = bc.textColour ?? '#1a1a2e';
  const primary = bc.primaryColour ?? '#2563eb';
  const font = bc.fontFamily ?? 'system-ui';
  const radius = bc.borderRadius ?? 6;

  const positionStyles = getPositionStyles(displayMode, cornerPosition, radius, bc.bannerWidth);
  const { rejectBtn, manageBtn, acceptBtn, closeBtn, logoHtml, cookieCount, privacyLink, titleText, descriptionText, savePreferencesText } =
    buildBannerParts(bc, primary, text, radius, privacyUrl);

  const fontLink = bc.customFontUrl
    ? `<link rel="stylesheet" href="${escapeHtml(bc.customFontUrl)}">`
    : '';

  const langAttr = previewLocale ? escapeHtml(previewLocale) : 'en';

  // Build the save preferences button with accept button styling (filled by default)
  const acceptStyle = buildButtonStyle(bc.acceptButton, 'filled', primary, '#ffffff', 'none', radius);
  const saveBtnHtml = `<button class="cmp-btn cmp-btn--primary cmp-btn--save" style="${acceptStyle}">${escapeHtml(savePreferencesText)}</button>`;

  return `<!DOCTYPE html>
<html lang="${langAttr}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
${fontLink}
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  html, body {
    height: 100%;
    background: #f3f4f6;
    font-family: ${font}, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }

  .page-content {
    padding: 32px 24px;
    color: #6b7280;
    font-size: 13px;
    line-height: 1.8;
  }
  .page-content h2 { color: #374151; font-size: 18px; margin-bottom: 12px; }
  .page-content p { margin-bottom: 12px; }

  .consentos-banner {
    ${positionStyles}
    background: ${bg};
    color: ${text};
    font-family: ${font}, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.12);
    border: 1px solid rgba(0, 0, 0, 0.1);
    border-radius: ${displayMode === 'overlay' || displayMode === 'corner_popup' ? radius + 'px' : '0'};
  }

  .consentos-banner__content {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px 24px;
    position: relative;
  }

  .cmp-logo { width: auto; max-width: 100%; margin-bottom: 10px; display: block; }
  .consentos-banner__title { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
  .consentos-banner__description { margin-bottom: 16px; opacity: 0.85; }
  .consentos-banner__link { color: ${primary}; text-decoration: underline; }
  .cmp-cookie-count { display: block; font-size: 12px; opacity: 0.6; margin-bottom: 12px; }
  .consentos-banner__actions { display: flex; gap: 10px; flex-wrap: wrap; }

  .cmp-btn {
    padding: 10px 20px;
    border-radius: ${radius}px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: opacity 0.2s;
    font-family: inherit;
  }

  .cmp-close {
    position: absolute; top: 12px; right: 12px;
    background: none; border: none; font-size: 22px;
    cursor: pointer; color: ${text}; opacity: 0.5; line-height: 1;
  }

  .consentos-banner__categories { display: none; margin-bottom: 16px; }

  .cmp-category {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 0; border-bottom: 1px solid rgba(0, 0, 0, 0.08);
  }

  .cmp-category__info { display: flex; flex-direction: column; flex: 1; margin-right: 12px; }
  .cmp-category__name { font-weight: 500; }
  .cmp-category__desc { font-size: 12px; opacity: 0.7; }
  .cmp-category input[type="checkbox"] { width: 18px; height: 18px; accent-color: ${primary}; }
  .cmp-btn--save { margin-top: 12px; width: 100%; }

  .cmp-overlay-bg {
    display: ${displayMode === 'overlay' && bc.showOverlayBackdrop !== false ? 'block' : 'none'};
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.4);
    z-index: 2147483646;
  }

  @media (max-width: 640px) {
    .consentos-banner__actions { flex-direction: column; }
    .cmp-btn { width: 100%; text-align: center; }
  }
</style>
</head>
<body>
  <div class="page-content">
    <h2>Example page</h2>
    <p>This is a preview of how the consent banner will appear on your site. The banner is rendered with your current theme and layout settings.</p>
    <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.</p>
  </div>

  <div class="cmp-overlay-bg"></div>

  <div class="consentos-banner" role="dialog" aria-label="Cookie consent">
    <div class="consentos-banner__content">
      ${closeBtn}
      ${logoHtml}
      <p class="consentos-banner__title">${escapeHtml(titleText)}</p>
      <p class="consentos-banner__description">
        ${escapeHtml(descriptionText)}${privacyLink}
      </p>
      ${cookieCount}
      <div class="consentos-banner__categories" id="cmp-prefs">
        <label class="cmp-category">
          <div class="cmp-category__info">
            <span class="cmp-category__name">Necessary</span>
            <span class="cmp-category__desc">Essential for the website to function. Always active.</span>
          </div>
          <input type="checkbox" checked disabled />
        </label>
        <label class="cmp-category">
          <div class="cmp-category__info">
            <span class="cmp-category__name">Functional</span>
            <span class="cmp-category__desc">Enable enhanced functionality and personalisation.</span>
          </div>
          <input type="checkbox" />
        </label>
        <label class="cmp-category">
          <div class="cmp-category__info">
            <span class="cmp-category__name">Analytics</span>
            <span class="cmp-category__desc">Help us understand how visitors interact with the site.</span>
          </div>
          <input type="checkbox" />
        </label>
        <label class="cmp-category">
          <div class="cmp-category__info">
            <span class="cmp-category__name">Marketing</span>
            <span class="cmp-category__desc">Used to deliver personalised advertisements.</span>
          </div>
          <input type="checkbox" />
        </label>
        <label class="cmp-category">
          <div class="cmp-category__info">
            <span class="cmp-category__name">Personalisation</span>
            <span class="cmp-category__desc">Enable content personalisation based on your profile.</span>
          </div>
          <input type="checkbox" />
        </label>
        ${saveBtnHtml}
      </div>
      <div class="consentos-banner__actions">
        ${rejectBtn}
        ${manageBtn}
        ${acceptBtn}
      </div>
    </div>
  </div>

  <script>
    function togglePrefs() {
      var el = document.getElementById('cmp-prefs');
      if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
    }
  </script>
</body>
</html>`;
}

/* ── Shared helpers ──────────────────────────────────────────────────── */

function buildButtonStyle(
  config: ButtonConfig | undefined,
  defaultStyle: 'filled' | 'outline',
  fallbackBg: string,
  fallbackText: string,
  fallbackBorder: string,
  radius: number,
): string {
  const bg = config?.backgroundColour ?? fallbackBg;
  const color = config?.textColour ?? fallbackText;
  const style = config?.style ?? defaultStyle;
  const border = config?.borderColour
    ? `1px solid ${config.borderColour}`
    : style === 'outline'
      ? `1px solid ${config?.textColour ?? fallbackBorder}`
      : style === 'text'
        ? 'none'
        : fallbackBorder === 'none'
          ? 'none'
          : `1px solid ${fallbackBorder}`;
  const background = style === 'text' ? 'transparent' : style === 'outline' ? 'transparent' : bg;

  return `background: ${background}; color: ${color}; border: ${border}; border-radius: ${radius}px;`;
}

function buildBannerParts(
  bc: BannerConfig,
  primary: string,
  text: string,
  radius: number,
  privacyUrl: string | null,
) {
  // Each button falls back to its own default style: the primary Accept
  // button is filled, the secondary Reject/Manage buttons are outlined.
  const acceptStyle = buildButtonStyle(bc.acceptButton, 'filled', primary, '#ffffff', 'none', radius);
  const rejectStyle = buildButtonStyle(bc.rejectButton, 'outline', 'transparent', text, 'rgba(0,0,0,0.2)', radius);
  const manageStyle = buildButtonStyle(bc.manageButton, 'outline', 'transparent', text, 'rgba(0,0,0,0.2)', radius);

  // Resolve text content from config or defaults
  const titleText = bc.text?.title ?? DEFAULT_TITLE;
  const descriptionText = bc.text?.description ?? DEFAULT_DESCRIPTION;
  const acceptAllText = bc.text?.acceptAll ?? DEFAULT_ACCEPT_ALL;
  const rejectAllText = bc.text?.rejectAll ?? DEFAULT_REJECT_ALL;
  const managePreferencesText = bc.text?.managePreferences ?? DEFAULT_MANAGE_PREFERENCES;
  const savePreferencesText = bc.text?.savePreferences ?? DEFAULT_SAVE_PREFERENCES;

  const acceptBtn = `<button class="cmp-btn" style="${acceptStyle}">${escapeHtml(acceptAllText)}</button>`;

  const rejectBtn = bc.showRejectAll !== false
    ? `<button class="cmp-btn" style="${rejectStyle}">${escapeHtml(rejectAllText)}</button>`
    : '';

  const manageBtn = bc.showManagePreferences !== false
    ? `<button class="cmp-btn" style="${manageStyle}" onclick="typeof togglePrefs==='function'&&togglePrefs()">${escapeHtml(managePreferencesText)}</button>`
    : '';

  const closeBtn = bc.showCloseButton
    ? `<button class="cmp-close" aria-label="Close">&times;</button>`
    : '';

  const logoHeight = Math.min(120, Math.max(12, Math.round(bc.logoHeight ?? 28)));
  const logoHtml = bc.showLogo && bc.logoUrl
    ? `<img src="${escapeHtml(bc.logoUrl)}" alt="Logo" class="cmp-logo" style="height:${logoHeight}px" />`
    : '';

  const cookieCount = bc.showCookieCount
    ? `<span class="cmp-cookie-count">12 cookies used on this site</span>`
    : '';

  const privacyLink = privacyUrl
    ? ` <a href="#" class="consentos-banner__link" onclick="return false">Privacy Policy</a>`
    : '';

  return { rejectBtn, manageBtn, acceptBtn, closeBtn, logoHtml, cookieCount, privacyLink, titleText, descriptionText, savePreferencesText };
}

function getPositionStyles(
  mode: DisplayMode,
  cornerPosition: CornerPosition,
  radius: number,
  bannerWidth?: number,
): string {
  const width = Math.min(960, Math.max(280, Math.round(bannerWidth ?? 600)));
  switch (mode) {
    case 'top_banner':
      return 'position: fixed; top: 0; left: 0; right: 0; z-index: 2147483647;';
    case 'overlay':
      return `position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 2147483647; width: 90%; max-width: ${width}px; border-radius: ${radius}px;`;
    case 'corner_popup': {
      const side = cornerPosition === 'left' ? 'left: 20px;' : 'right: 20px;';
      return `position: fixed; bottom: 20px; ${side} z-index: 2147483647; width: 380px; max-width: calc(100% - 40px); border-radius: ${radius}px;`;
    }
    case 'bottom_banner':
    default:
      return 'position: fixed; bottom: 0; left: 0; right: 0; z-index: 2147483647;';
  }
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
