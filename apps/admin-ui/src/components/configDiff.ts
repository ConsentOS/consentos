import type { ChangeSource, DiffChange } from '../types/api';

const FIELD_LABELS: Record<string, string> = {
  blocking_mode: 'Blocking mode',
  regional_modes: 'Regional blocking modes',
  tcf_enabled: 'IAB TCF',
  tcf_publisher_cc: 'TCF publisher country',
  gpp_enabled: 'Global Privacy Platform',
  gpp_supported_apis: 'GPP sections',
  gpc_enabled: 'Global Privacy Control',
  gpc_jurisdictions: 'GPC jurisdictions',
  gpc_global_honour: 'Honour GPC everywhere',
  gcm_enabled: 'Google Consent Mode',
  gcm_default: 'Google Consent Mode defaults',
  shopify_privacy_enabled: 'Shopify Customer Privacy',
  privacy_policy_url: 'Privacy policy link',
  terms_url: 'Terms link',
  consent_expiry_days: 'Consent expiry (days)',
  enabled_categories: 'Categories shown',
  disclosed_vendor_ids: 'Disclosed vendors',
  consent_sharing_enabled: 'Cross-domain consent sharing',
  consent_bridge_url: 'Consent bridge URL',
  consent_group_id: 'Consent sharing group',
  gvl_version: 'Global Vendor List version',
};

export const SOURCE_LABELS: Record<Exclude<ChangeSource, 'site'>, string> = {
  organisation: 'From organisation defaults',
  site_group: 'From site group defaults',
  system: 'System',
};

/** A plain-language name for a change's key. */
export function changeLabel(change: DiffChange): string {
  const [prefix, ...rest] = change.key.split('.');
  const remainder = rest.join('.');
  if (prefix === 'banner_config') return remainder;
  if (prefix === 'category_tcf_purposes') return `TCF purposes for ${remainder}`;
  if (prefix === 'cookies') return `Cookie ${remainder.split('#')[0].replace('@', ' on ')}`;
  if (prefix === 'allow_list') return `Allow-list entry ${remainder.replace('@', ' on ')}`;
  if (change.area === 'translations') return `${prefix}: ${remainder}`;
  return FIELD_LABELS[change.key] ?? change.key;
}

/** A plain-language rendering of a value on either side of a change. */
export function formatValue(change: DiffChange, value: unknown): string {
  if (value === null || value === undefined) {
    return change.area === 'cookies' ? 'Not listed' : 'Not set';
  }
  if (change.area === 'cookies' && typeof value === 'object') {
    const category = (value as { category?: string | null; category_id?: string | null }).category;
    return category === undefined ? 'Listed' : (category ?? 'Uncategorised');
  }
  if (typeof value === 'boolean') return value ? 'On' : 'Off';
  if (Array.isArray(value)) return value.length ? value.join(', ') : 'None';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}
