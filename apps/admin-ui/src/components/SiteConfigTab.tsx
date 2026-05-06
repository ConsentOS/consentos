import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import type { FormEvent } from 'react';

import { getGvlMeta } from '../api/iab-gvl';
import { getConfigInheritance, updateSiteConfig } from '../api/sites';
import { trackConfigChange } from '../services/analytics';
import type { ConfigInheritanceResponse, ConfigSource, SiteConfig } from '../types/api';
import IabVendorPicker from './IabVendorPicker';
import { Alert } from './ui/alert';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { FormField } from './ui/form-field';
import { Input } from './ui/input';
import { Select } from './ui/select';

interface Props {
  siteId: string;
  config: SiteConfig | null;
}

const GPP_SECTIONS = [
  { value: 'usnat', label: 'US National Privacy (Section 7)' },
  { value: 'usca', label: 'US California — CCPA/CPRA (Section 8)' },
  { value: 'usva', label: 'US Virginia — VCDPA (Section 9)' },
  { value: 'usco', label: 'US Colorado — CPA (Section 10)' },
  { value: 'usct', label: 'US Connecticut — CTDPA (Section 11)' },
  { value: 'usfl', label: 'US Florida — FDBR (Section 14)' },
];

const GPC_JURISDICTIONS = [
  { value: 'US-CA', label: 'California (CCPA/CPRA)' },
  { value: 'US-CO', label: 'Colorado (CPA)' },
  { value: 'US-CT', label: 'Connecticut (CTDPA)' },
  { value: 'US-TX', label: 'Texas (TDPSA)' },
  { value: 'US-MT', label: 'Montana (MTCDPA)' },
];

const SOURCE_LABELS: Record<ConfigSource, string> = {
  system: 'System default',
  org: 'Organisation default',
  group: 'Group default',
  site: 'Site override',
};

const SOURCE_COLOURS: Record<ConfigSource, string> = {
  system: 'bg-gray-100 text-gray-600',
  org: 'bg-blue-50 text-blue-700',
  group: 'bg-purple-50 text-purple-700',
  site: 'bg-green-50 text-green-700',
};

function SourceBadge({ source, field }: { source: ConfigSource; field: string }) {
  if (source === 'site') return null;
  return (
    <span
      className={`ml-2 inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ${SOURCE_COLOURS[source]}`}
      title={`The value for "${field}" is inherited from ${SOURCE_LABELS[source].toLowerCase()}`}
    >
      {SOURCE_LABELS[source]}
    </span>
  );
}

/**
 * Button to reset a field to its inherited default.
 * Only shown when the field is overridden at site level.
 */
function ResetButton({
  field,
  inheritance,
  onReset,
}: {
  field: string;
  inheritance: ConfigInheritanceResponse | undefined;
  onReset: () => void;
}) {
  const source = inheritance?.fields[field]?.source;
  if (source !== 'site') return null;

  const parentSource = getParentSource(field, inheritance);
  const label = parentSource
    ? `Reset to ${SOURCE_LABELS[parentSource].toLowerCase()}`
    : 'Reset to default';

  return (
    <button
      type="button"
      onClick={onReset}
      className="ml-2 text-[10px] font-medium text-primary hover:text-primary/80 hover:underline"
      title={label}
    >
      {label}
    </button>
  );
}

/** Determine which parent level would provide the value if site override is removed. */
function getParentSource(
  field: string,
  inheritance: ConfigInheritanceResponse | undefined,
): ConfigSource | null {
  if (!inheritance) return null;
  const info = inheritance.fields[field];
  if (!info) return null;
  if (info.group_value != null) return 'group';
  if (info.org_value != null) return 'org';
  return 'system';
}

export default function SiteConfigTab({ siteId, config }: Props) {
  const queryClient = useQueryClient();
  const [blockingMode, setBlockingMode] = useState<string>(config?.blocking_mode ?? 'opt_in');
  const [tcfEnabled, setTcfEnabled] = useState(config?.tcf_enabled ?? false);
  const [disclosedVendorIds, setDisclosedVendorIds] = useState<number[]>(
    config?.disclosed_vendor_ids ?? [],
  );
  const [gcmEnabled, setGcmEnabled] = useState(config?.gcm_enabled ?? true);
  const [shopifyEnabled, setShopifyEnabled] = useState(config?.shopify_privacy_enabled ?? false);
  const [consentExpiry, setConsentExpiry] = useState(config?.consent_expiry_days ?? 365);
  const [privacyUrl, setPrivacyUrl] = useState(config?.privacy_policy_url ?? '');
  const [termsUrl, setTermsUrl] = useState(config?.terms_url ?? '');

  // GPP state
  const [gppEnabled, setGppEnabled] = useState(config?.gpp_enabled ?? true);
  const [gppSupportedApis, setGppSupportedApis] = useState<string[]>(
    config?.gpp_supported_apis ?? ['usnat'],
  );

  // GPC state
  const [gpcEnabled, setGpcEnabled] = useState(config?.gpc_enabled ?? true);
  const [gpcJurisdictions, setGpcJurisdictions] = useState<string[]>(
    config?.gpc_jurisdictions ?? ['US-CA', 'US-CO', 'US-CT', 'US-TX', 'US-MT'],
  );
  const [gpcGlobalHonour, setGpcGlobalHonour] = useState(config?.gpc_global_honour ?? false);

  // Track which fields should be sent as null (reset to default)
  const [resetFields, setResetFields] = useState<Set<string>>(new Set());

  const [saved, setSaved] = useState(false);

  const { data: inheritance } = useQuery({
    queryKey: ['sites', siteId, 'inheritance'],
    queryFn: () => getConfigInheritance(siteId),
    enabled: !!siteId,
  });

  // Surface the cached GVL version next to the TCF toggle. Banners
  // stamp this onto every TC string they emit, so operators want to
  // see at a glance which list version their disclosure is built
  // against.
  const { data: gvlMeta } = useQuery({
    queryKey: ['iab', 'gvl-meta'],
    queryFn: getGvlMeta,
    staleTime: 5 * 60_000,
  });

  const mutation = useMutation({
    mutationFn: (body: Record<string, unknown>) => updateSiteConfig(siteId, body as Partial<SiteConfig>),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sites', siteId, 'config'] });
      queryClient.invalidateQueries({ queryKey: ['sites', siteId, 'inheritance'] });
      trackConfigChange('site_config', { site_id: siteId });
      setResetFields(new Set());
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  const markReset = (field: string) => {
    setResetFields((prev) => new Set([...prev, field]));
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();

    const body: Record<string, unknown> = {
      blocking_mode: blockingMode,
      tcf_enabled: tcfEnabled,
      // Empty selection clears the override and falls back to the
      // cascade (group → org → []). Non-empty wins per the resolver.
      disclosed_vendor_ids: disclosedVendorIds.length > 0 ? disclosedVendorIds : null,
      gcm_enabled: gcmEnabled,
      shopify_privacy_enabled: shopifyEnabled,
      consent_expiry_days: consentExpiry,
      privacy_policy_url: privacyUrl || null,
      terms_url: termsUrl || null,
      gpp_enabled: gppEnabled,
      gpp_supported_apis: gppEnabled ? gppSupportedApis : null,
      gpc_enabled: gpcEnabled,
      gpc_jurisdictions: gpcEnabled ? gpcJurisdictions : null,
      gpc_global_honour: gpcGlobalHonour,
    };

    // Override any fields marked for reset with null
    for (const field of resetFields) {
      body[field] = null;
    }

    mutation.mutate(body);
  };

  const toggleGppSection = (api: string) => {
    setGppSupportedApis((prev) =>
      prev.includes(api) ? prev.filter((a) => a !== api) : [...prev, api],
    );
  };

  const toggleGpcJurisdiction = (code: string) => {
    setGpcJurisdictions((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code],
    );
  };

  const getSource = (field: string): ConfigSource => {
    return inheritance?.fields[field]?.source ?? 'site';
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Inheritance info banner */}
      {inheritance && (
        <div className="rounded-xl border border-dashed border-border bg-surface p-4">
          <p className="text-xs text-text-secondary">
            <strong>Configuration cascade:</strong> System defaults
            {' \u2192 '}Organisation defaults
            {inheritance.site_group_id && <>{' \u2192 '}Group defaults</>}
            {' \u2192 '}<span className="font-semibold">Site config</span>
            {' \u2192 '}Regional overrides.
            Fields with a coloured badge are inherited from a higher level.
            Click &ldquo;Reset&rdquo; to remove a site-level override and inherit the parent value.
          </p>
        </div>
      )}

      <Card className="p-6">
        <h3 className="font-heading mb-4 text-sm font-semibold text-foreground">Consent settings</h3>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <div>
            <div className="flex items-center">
              <FormField label="Blocking mode">
                <Select
                  value={blockingMode}
                  onChange={(e) => setBlockingMode(e.target.value)}
                >
                  <option value="opt_in">Opt-in (GDPR)</option>
                  <option value="opt_out">Opt-out (CCPA)</option>
                  <option value="informational">Informational only</option>
                </Select>
              </FormField>
              <SourceBadge source={getSource('blocking_mode')} field="blocking mode" />
              <ResetButton field="blocking_mode" inheritance={inheritance} onReset={() => markReset('blocking_mode')} />
            </div>
          </div>

          <div>
            <div className="flex items-center">
              <FormField label="Consent expiry (days)">
                <Input
                  type="number"
                  min={1}
                  max={730}
                  value={consentExpiry}
                  onChange={(e) => setConsentExpiry(Number(e.target.value))}
                />
              </FormField>
              <SourceBadge source={getSource('consent_expiry_days')} field="consent expiry" />
              <ResetButton field="consent_expiry_days" inheritance={inheritance} onReset={() => markReset('consent_expiry_days')} />
            </div>
          </div>

          <div>
            <div className="flex items-center">
              <FormField label="Privacy policy URL">
                <Input
                  type="url"
                  value={privacyUrl}
                  onChange={(e) => setPrivacyUrl(e.target.value)}
                  placeholder="https://example.com/privacy"
                />
              </FormField>
              <SourceBadge source={getSource('privacy_policy_url')} field="privacy policy URL" />
              <ResetButton field="privacy_policy_url" inheritance={inheritance} onReset={() => { setPrivacyUrl(''); markReset('privacy_policy_url'); }} />
            </div>
          </div>

          <div>
            <div className="flex items-center">
              <FormField label="Terms & conditions URL">
                <Input
                  type="url"
                  value={termsUrl}
                  onChange={(e) => setTermsUrl(e.target.value)}
                  placeholder="https://example.com/terms"
                />
              </FormField>
              <SourceBadge source={getSource('terms_url')} field="terms URL" />
              <ResetButton field="terms_url" inheritance={inheritance} onReset={() => { setTermsUrl(''); markReset('terms_url'); }} />
            </div>
            <p className="mt-1 text-xs text-text-secondary">
              Use <code className="rounded bg-surface px-1">{'{{privacy_policy}}'}</code> and{' '}
              <code className="rounded bg-surface px-1">{'{{terms}}'}</code> in your banner
              description with markdown links, e.g.{' '}
              <code className="rounded bg-surface px-1">{'[Privacy Policy]({{privacy_policy}})'}</code>
            </p>
          </div>
        </div>
      </Card>

      <Card className="p-6">
        <h3 className="font-heading mb-4 text-sm font-semibold text-foreground">Standards &amp; integrations</h3>

        <div className="space-y-3">
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={tcfEnabled}
              onChange={(e) => setTcfEnabled(e.target.checked)}
              className="h-4 w-4 rounded border-border text-primary"
            />
            <div className="flex items-center">
              <span className="text-sm font-medium text-text-secondary">IAB TCF v2.3</span>
              <SourceBadge source={getSource('tcf_enabled')} field="TCF" />
              <ResetButton field="tcf_enabled" inheritance={inheritance} onReset={() => markReset('tcf_enabled')} />
            </div>
          </label>
          <p className="ml-7 text-xs text-text-secondary">Enable Transparency and Consent Framework</p>

          {tcfEnabled && (
            <div className="ml-7 mt-3 space-y-4 rounded-lg border border-border bg-surface p-4">
              {/* GVL info — operators need to know which list version
                  their disclosure ships against. */}
              <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                <div>
                  <div className="text-text-secondary">GVL version</div>
                  <div className="font-mono text-foreground">
                    {gvlMeta ? gvlMeta.vendor_list_version : '—'}
                  </div>
                </div>
                <div>
                  <div className="text-text-secondary">TCF policy</div>
                  <div className="font-mono text-foreground">
                    {gvlMeta ? `v${gvlMeta.tcf_policy_version}` : '—'}
                  </div>
                </div>
                <div>
                  <div className="text-text-secondary">List updated</div>
                  <div className="font-mono text-foreground">
                    {gvlMeta ? new Date(gvlMeta.last_updated).toISOString().slice(0, 10) : '—'}
                  </div>
                </div>
                <div>
                  <div className="text-text-secondary">Synced</div>
                  <div className="font-mono text-foreground">
                    {gvlMeta ? new Date(gvlMeta.synced_at).toISOString().slice(0, 10) : '—'}
                  </div>
                </div>
              </div>
              {!gvlMeta && (
                <p className="text-xs text-text-secondary">
                  The IAB Global Vendor List has not been synced yet. The daily
                  refresh runs at 03:15 UTC; trigger it manually with{' '}
                  <code className="font-mono">celery -A src.celery_app call src.tasks.iab_gvl.refresh_gvl</code>.
                </p>
              )}

              {/* Disclosed vendors picker */}
              <div>
                <div className="mb-2 flex items-center">
                  <span className="text-sm font-medium text-text-secondary">
                    Disclosed vendors
                  </span>
                  <SourceBadge
                    source={getSource('disclosed_vendor_ids')}
                    field="disclosed vendors"
                  />
                  <ResetButton
                    field="disclosed_vendor_ids"
                    inheritance={inheritance}
                    onReset={() => {
                      markReset('disclosed_vendor_ids');
                      setDisclosedVendorIds([]);
                    }}
                  />
                </div>
                <p className="mb-3 text-xs text-text-secondary">
                  Vendors listed here are encoded into the TCF v2.3
                  DisclosedVendors segment of every TC string the banner emits.
                  These are the vendors your CMP UI is declaring it has shown
                  to the user.
                </p>
                <IabVendorPicker
                  value={disclosedVendorIds}
                  onChange={setDisclosedVendorIds}
                />
              </div>
            </div>
          )}

          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={gcmEnabled}
              onChange={(e) => setGcmEnabled(e.target.checked)}
              className="h-4 w-4 rounded border-border text-primary"
            />
            <div className="flex items-center">
              <span className="text-sm font-medium text-text-secondary">Google Consent Mode v2</span>
              <SourceBadge source={getSource('gcm_enabled')} field="GCM" />
              <ResetButton field="gcm_enabled" inheritance={inheritance} onReset={() => markReset('gcm_enabled')} />
            </div>
          </label>
          <p className="ml-7 text-xs text-text-secondary">Automatically set gtag consent signals</p>

          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={shopifyEnabled}
              onChange={(e) => setShopifyEnabled(e.target.checked)}
              className="h-4 w-4 rounded border-border text-primary"
            />
            <div className="flex items-center">
              <span className="text-sm font-medium text-text-secondary">Shopify Customer Privacy API</span>
              <SourceBadge source={getSource('shopify_privacy_enabled')} field="Shopify Privacy" />
              <ResetButton field="shopify_privacy_enabled" inheritance={inheritance} onReset={() => markReset('shopify_privacy_enabled')} />
            </div>
          </label>
          <p className="ml-7 text-xs text-text-secondary">
            Bridge consent decisions to Shopify&apos;s <code>setTrackingConsent()</code> API.
            Enable this for Shopify-hosted stores.
          </p>
        </div>
      </Card>

      {/* Privacy Signals — GPP */}
      <Card className="p-6">
        <h3 className="font-heading mb-4 text-sm font-semibold text-foreground">IAB Global Privacy Platform (GPP)</h3>
        <p className="mb-4 text-xs text-text-secondary">
          GPP provides a standardised consent string format for US state privacy laws.
          When enabled, the banner exposes the <code>__gpp()</code> API and generates GPP strings
          for the selected sections.
        </p>

        <label className="mb-4 flex items-center gap-3">
          <input
            type="checkbox"
            checked={gppEnabled}
            onChange={(e) => setGppEnabled(e.target.checked)}
            className="h-4 w-4 rounded border-border text-primary"
          />
          <div className="flex items-center">
            <span className="text-sm font-medium text-text-secondary">Enable GPP</span>
            <ResetButton field="gpp_enabled" inheritance={inheritance} onReset={() => markReset('gpp_enabled')} />
          </div>
        </label>

        {gppEnabled && (
          <div className="ml-7 space-y-2">
            <p className="mb-2 text-xs font-medium text-text-secondary">Supported sections</p>
            {GPP_SECTIONS.map((section) => (
              <label key={section.value} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={gppSupportedApis.includes(section.value)}
                  onChange={() => toggleGppSection(section.value)}
                  className="h-4 w-4 rounded border-border text-primary"
                />
                <span className="text-sm text-text-secondary">{section.label}</span>
              </label>
            ))}
          </div>
        )}
      </Card>

      {/* Privacy Signals — GPC */}
      <Card className="p-6">
        <h3 className="font-heading mb-4 text-sm font-semibold text-foreground">Global Privacy Control (GPC)</h3>
        <p className="mb-4 text-xs text-text-secondary">
          GPC is a browser signal indicating a user&apos;s intent to opt out of the sale or
          sharing of their personal data. Several US state laws (CCPA, CPA, CTDPA, TDPSA, MTCDPA)
          legally require businesses to honour this signal.
        </p>

        <label className="mb-4 flex items-center gap-3">
          <input
            type="checkbox"
            checked={gpcEnabled}
            onChange={(e) => setGpcEnabled(e.target.checked)}
            className="h-4 w-4 rounded border-border text-primary"
          />
          <div className="flex items-center">
            <span className="text-sm font-medium text-text-secondary">Detect GPC signal</span>
            <ResetButton field="gpc_enabled" inheritance={inheritance} onReset={() => markReset('gpc_enabled')} />
          </div>
        </label>

        {gpcEnabled && (
          <div className="ml-7 space-y-4">
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={gpcGlobalHonour}
                onChange={(e) => setGpcGlobalHonour(e.target.checked)}
                className="h-4 w-4 rounded border-border text-primary"
              />
              <div>
                <span className="text-sm font-medium text-text-secondary">Honour globally</span>
                <p className="text-xs text-text-secondary">
                  Apply GPC opt-out for all visitors regardless of jurisdiction
                </p>
              </div>
            </label>

            {!gpcGlobalHonour && (
              <div>
                <p className="mb-2 text-xs font-medium text-text-secondary">
                  Jurisdictions where GPC is legally required
                </p>
                {GPC_JURISDICTIONS.map((j) => (
                  <label key={j.value} className="flex items-center gap-2 py-0.5">
                    <input
                      type="checkbox"
                      checked={gpcJurisdictions.includes(j.value)}
                      onChange={() => toggleGpcJurisdiction(j.value)}
                      className="h-4 w-4 rounded border-border text-primary"
                    />
                    <span className="text-sm text-text-secondary">{j.label}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
        )}
      </Card>

      <div className="flex items-center gap-3">
        <Button
          type="submit"
          disabled={mutation.isPending}
        >
          {mutation.isPending ? 'Saving...' : 'Save configuration'}
        </Button>
        {resetFields.size > 0 && (
          <span className="text-xs text-text-secondary">
            {resetFields.size} field{resetFields.size > 1 ? 's' : ''} will be reset to default
          </span>
        )}
        {saved && <Alert variant="success" className="inline-flex w-auto p-2">Saved successfully</Alert>}
        {mutation.isError && (
          <Alert variant="error" className="inline-flex w-auto p-2">Failed to save. Please try again.</Alert>
        )}
      </div>
    </form>
  );
}
