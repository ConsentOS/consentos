/**
 * Embedded cookies-management widget. Site owners drop a div somewhere
 * on their page and either annotate it with ``data-consentos-cookies``
 * (auto-mount) or call ``window.ConsentOS.renderCookies(target)``. The
 * widget fetches the site's categories and classified cookies from the
 * API, renders an in-page HTML view, and routes Accept / Reject / Save
 * back through the host's consent flow so the audit trail, blocker
 * state, GCM signals, and dataLayer push all stay in sync.
 *
 * No Shadow DOM: site CSS can theme the widget. Default styles live
 * behind CSS custom properties so the override surface is just a few
 * named tokens.
 */

import type { TranslationStrings } from './i18n';
import type { CategorySlug } from './types';

interface CookieRow {
  name: string;
  domain: string;
  type: string;
  description: string;
  vendor: string;
}

interface CategoryRow {
  slug: string;
  name: string;
  description: string;
  locked: boolean;
  cookies: CookieRow[];
}

export interface CookiesWidgetData {
  site_id: string;
  site_name: string;
  domain: string;
  privacy_policy_url: string | null;
  consent_expiry_days: number;
  categories: CategoryRow[];
}

export interface CookiesWidgetOptions {
  target: string | HTMLElement | undefined;
  apiBase: string;
  siteId: string;
  t: TranslationStrings;
  currentAccepted: CategorySlug[];
  /** Called with the new accepted / rejected sets when the visitor saves. */
  onSave: (accepted: CategorySlug[], rejected: CategorySlug[]) => void;
}

const STYLE_ID = 'consentos-cookies-widget-styles';

export async function renderCookiesWidget(opts: CookiesWidgetOptions): Promise<void> {
  const el = resolveTarget(opts.target);
  if (!el) {
    console.warn('[ConsentOS] renderCookies: target element not found');
    return;
  }
  let data: CookiesWidgetData;
  try {
    const resp = await fetch(
      `${opts.apiBase}/api/v1/config/sites/${opts.siteId}/cookies`,
    );
    if (!resp.ok) {
      console.error('[ConsentOS] renderCookies: HTTP', resp.status);
      return;
    }
    data = (await resp.json()) as CookiesWidgetData;
  } catch (err) {
    console.error('[ConsentOS] renderCookies: fetch failed', err);
    return;
  }

  injectStyles();
  el.classList.add('cmp-cookies');
  el.innerHTML = buildHtml(data, opts.t, opts.currentAccepted);
  wireUp(el, data, opts);
}

function resolveTarget(target: string | HTMLElement | undefined): HTMLElement | null {
  if (target instanceof HTMLElement) return target;
  if (typeof target === 'string') {
    return document.querySelector<HTMLElement>(target);
  }
  return document.querySelector<HTMLElement>('[data-consentos-cookies]');
}

function injectStyles(): void {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = WIDGET_CSS;
  document.head.appendChild(style);
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function buildHtml(
  data: CookiesWidgetData,
  t: TranslationStrings,
  currentAccepted: CategorySlug[],
): string {
  const acceptedSet = new Set(currentAccepted);
  const categoriesHtml = data.categories
    .map((cat) => renderCategory(cat, acceptedSet))
    .join('');
  const privacyLink = data.privacy_policy_url
    ? `<p class="cmp-cookies__privacy">
        <a href="${escapeHtml(data.privacy_policy_url)}" target="_blank" rel="noopener">Privacy policy</a>
      </p>`
    : '';

  return `
    <div class="cmp-cookies__inner">
      <h2 class="cmp-cookies__title">Cookie preferences</h2>
      <p class="cmp-cookies__subtitle">
        Manage your cookie preferences for ${escapeHtml(data.domain)}.
      </p>
      <div class="cmp-cookies__categories">${categoriesHtml}</div>
      <div class="cmp-cookies__actions">
        <button type="button" data-action="reject" class="cmp-cookies__btn cmp-cookies__btn--secondary">
          ${escapeHtml(t.rejectAll || 'Reject all')}
        </button>
        <button type="button" data-action="save" class="cmp-cookies__btn cmp-cookies__btn--secondary">
          ${escapeHtml(t.savePreferences || 'Save preferences')}
        </button>
        <button type="button" data-action="accept" class="cmp-cookies__btn cmp-cookies__btn--primary">
          ${escapeHtml(t.acceptAll || 'Accept all')}
        </button>
      </div>
      <p class="cmp-cookies__saved" data-saved hidden>Your preferences have been saved.</p>
      ${privacyLink}
    </div>
  `;
}

function renderCategory(cat: CategoryRow, accepted: Set<CategorySlug>): string {
  const count = cat.cookies.length;
  const toggle = cat.locked
    ? `<span class="cmp-category__always">Always active</span>`
    : `<label class="cmp-toggle">
        <input
          type="checkbox"
          data-category="${escapeHtml(cat.slug)}"
          ${accepted.has(cat.slug as CategorySlug) ? 'checked' : ''}
        />
        <span>Use</span>
      </label>`;

  const cookiesBlock =
    count === 0
      ? ''
      : `<details class="cmp-category__cookies">
          <summary>${count} cookie${count === 1 ? '' : 's'} in this category</summary>
          ${renderCookieTable(cat.cookies)}
        </details>`;

  return `
    <div class="cmp-category" data-category-row="${escapeHtml(cat.slug)}">
      <div class="cmp-category__header">
        <h3 class="cmp-category__name">${escapeHtml(cat.name)}</h3>
        ${toggle}
      </div>
      ${cat.description ? `<p class="cmp-category__desc">${escapeHtml(cat.description)}</p>` : ''}
      ${cookiesBlock}
    </div>
  `;
}

function renderCookieTable(cookies: CookieRow[]): string {
  const rows = cookies
    .map(
      (c) => `
      <tr>
        <td><code>${escapeHtml(c.name)}</code></td>
        <td>${escapeHtml(c.domain)}</td>
        <td>${escapeHtml(c.type)}</td>
        <td>${escapeHtml(c.description)}</td>
      </tr>`,
    )
    .join('');
  return `
    <div class="cmp-cookie-table-wrap">
      <table class="cmp-cookie-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Domain</th>
            <th>Type</th>
            <th>Description</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function wireUp(
  el: HTMLElement,
  data: CookiesWidgetData,
  opts: CookiesWidgetOptions,
): void {
  const checkboxes = el.querySelectorAll<HTMLInputElement>('input[data-category]');
  const savedMsg = el.querySelector<HTMLElement>('[data-saved]');

  function readSelected(): CategorySlug[] {
    const accepted: CategorySlug[] = ['necessary'];
    checkboxes.forEach((cb) => {
      if (cb.checked) {
        accepted.push(cb.dataset.category as CategorySlug);
      }
    });
    return [...new Set(accepted)];
  }

  function nonEssentialSlugs(): CategorySlug[] {
    return data.categories
      .filter((c) => !c.locked && c.slug !== 'uncategorised')
      .map((c) => c.slug as CategorySlug);
  }

  function applyAndFlash(accepted: CategorySlug[]): void {
    const all = nonEssentialSlugs();
    const rejected = all.filter((slug) => !accepted.includes(slug));
    opts.onSave(accepted, rejected);
    if (savedMsg) {
      savedMsg.hidden = false;
      setTimeout(() => {
        savedMsg.hidden = true;
      }, 3000);
    }
  }

  el.querySelectorAll<HTMLButtonElement>('button[data-action]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      const action = (e.currentTarget as HTMLElement).dataset.action;
      if (action === 'accept') {
        const all: CategorySlug[] = ['necessary', ...nonEssentialSlugs()];
        checkboxes.forEach((cb) => {
          cb.checked = true;
        });
        applyAndFlash(all);
      } else if (action === 'reject') {
        checkboxes.forEach((cb) => {
          cb.checked = false;
        });
        applyAndFlash(['necessary']);
      } else if (action === 'save') {
        applyAndFlash(readSelected());
      }
    });
  });
}

const WIDGET_CSS = `
.cmp-cookies {
  --cmp-color-primary: #2C6AE4;
  --cmp-color-text: inherit;
  --cmp-color-muted: #5A6E96;
  --cmp-color-border: #DDE6F4;
  --cmp-color-surface: #F5F8FC;
  --cmp-radius: 8px;
}
.cmp-cookies__inner {
  max-width: 720px;
  margin: 0 auto;
  font-family: inherit;
  color: var(--cmp-color-text);
  line-height: 1.5;
}
.cmp-cookies__title {
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0 0 0.5rem;
}
.cmp-cookies__subtitle {
  color: var(--cmp-color-muted);
  margin: 0 0 1.5rem;
}
.cmp-cookies__categories {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-bottom: 1.5rem;
}
.cmp-category {
  border: 1px solid var(--cmp-color-border);
  border-radius: var(--cmp-radius);
  padding: 1rem 1.25rem;
  background: var(--cmp-color-surface);
}
.cmp-category__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}
.cmp-category__name {
  font-size: 1rem;
  font-weight: 600;
  margin: 0;
}
.cmp-category__always {
  font-size: 0.85rem;
  color: var(--cmp-color-muted);
}
.cmp-category__desc {
  color: var(--cmp-color-muted);
  margin: 0.5rem 0 0;
  font-size: 0.9rem;
}
.cmp-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-size: 0.9rem;
}
.cmp-toggle input { margin: 0; }
.cmp-category__cookies {
  margin-top: 0.75rem;
}
.cmp-category__cookies summary {
  cursor: pointer;
  font-size: 0.85rem;
  color: var(--cmp-color-muted);
  padding: 0.25rem 0;
}
.cmp-cookie-table-wrap {
  overflow-x: auto;
  margin-top: 0.5rem;
}
.cmp-cookie-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
.cmp-cookie-table th,
.cmp-cookie-table td {
  padding: 0.5rem 0.6rem;
  border-bottom: 1px solid var(--cmp-color-border);
  text-align: left;
  vertical-align: top;
}
.cmp-cookie-table th {
  font-weight: 500;
  color: var(--cmp-color-muted);
  font-size: 0.8rem;
}
.cmp-cookies__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}
.cmp-cookies__btn {
  padding: 0.6rem 1.2rem;
  border-radius: var(--cmp-radius);
  border: 1px solid var(--cmp-color-border);
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: 500;
  cursor: pointer;
}
.cmp-cookies__btn--primary {
  background: var(--cmp-color-primary);
  color: #fff;
  border-color: var(--cmp-color-primary);
}
.cmp-cookies__saved {
  margin: 1rem 0 0;
  color: #0a8a4a;
  font-size: 0.9rem;
}
.cmp-cookies__privacy {
  margin-top: 1rem;
  font-size: 0.85rem;
  color: var(--cmp-color-muted);
}
.cmp-cookies__privacy a {
  color: var(--cmp-color-primary);
}
@media (max-width: 600px) {
  .cmp-cookies__actions { flex-direction: column; }
  .cmp-cookies__actions .cmp-cookies__btn { width: 100%; }
}
`;
