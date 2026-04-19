import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import type { FormEvent } from 'react';
import { useParams } from 'react-router-dom';

import { getSiteGroup } from '../api/site-groups';
import { getSiteGroupConfig, updateSiteGroupConfig } from '../api/site-group-config';
import BannerBuilderTab from '../components/BannerBuilderTab';
import { Alert } from '../components/ui/alert';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { FormField } from '../components/ui/form-field';
import { Input } from '../components/ui/input';
import { LoadingState } from '../components/ui/loading-state';
import { Select } from '../components/ui/select';

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

type Tab = 'configuration' | 'banner';

export default function SiteGroupDetailPage() {
  const { groupId } = useParams<{ groupId: string }>();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<Tab>('configuration');
  const [saved, setSaved] = useState(false);

  const { data: group, isLoading: groupLoading } = useQuery({
    queryKey: ['site-groups', groupId],
    queryFn: () => getSiteGroup(groupId!),
    enabled: !!groupId,
  });

  const { data: config, isLoading: configLoading } = useQuery({
    queryKey: ['site-group-config', groupId],
    queryFn: () => getSiteGroupConfig(groupId!),
    enabled: !!groupId,
  });

  // ── Form state (all nullable — empty = inherit from org/system) ────
  const [blockingMode, setBlockingMode] = useState<string>('');
  const [tcfEnabled, setTcfEnabled] = useState<string>('');
  const [gcmEnabled, setGcmEnabled] = useState<string>('');
  const [shopifyEnabled, setShopifyEnabled] = useState<string>('');
  const [consentExpiry, setConsentExpiry] = useState<string>('');
  const [consentSharing, setConsentSharing] = useState<string>('');
  const [bridgeUrl, setBridgeUrl] = useState<string>('');
  const [privacyUrl, setPrivacyUrl] = useState<string>('');
  const [termsUrl, setTermsUrl] = useState<string>('');

  // GPP state
  const [gppEnabled, setGppEnabled] = useState<string>('');
  const [gppSupportedApis, setGppSupportedApis] = useState<string[]>([]);

  // GPC state
  const [gpcEnabled, setGpcEnabled] = useState<string>('');
  const [gpcGlobalHonour, setGpcGlobalHonour] = useState<string>('');
  const [gpcJurisdictions, setGpcJurisdictions] = useState<string[]>([]);

  // Sync local state when config loads
  const [initialised, setInitialised] = useState(false);
  if (config && !initialised) {
    setBlockingMode(config.blocking_mode ?? '');
    setTcfEnabled(config.tcf_enabled === null ? '' : config.tcf_enabled ? 'true' : 'false');
    setGcmEnabled(config.gcm_enabled === null ? '' : config.gcm_enabled ? 'true' : 'false');
    setShopifyEnabled(
      config.shopify_privacy_enabled === null ? '' : config.shopify_privacy_enabled ? 'true' : 'false',
    );
    setConsentExpiry(config.consent_expiry_days?.toString() ?? '');
    setConsentSharing(
      config.consent_sharing_enabled == null
        ? ''
        : config.consent_sharing_enabled
          ? 'true'
          : 'false',
    );
    setBridgeUrl(config.consent_bridge_url ?? '');
    setPrivacyUrl(config.privacy_policy_url ?? '');
    setTermsUrl(config.terms_url ?? '');
    setGppEnabled(config.gpp_enabled === null || config.gpp_enabled === undefined ? '' : config.gpp_enabled ? 'true' : 'false');
    setGppSupportedApis(config.gpp_supported_apis ?? []);
    setGpcEnabled(config.gpc_enabled === null || config.gpc_enabled === undefined ? '' : config.gpc_enabled ? 'true' : 'false');
    setGpcGlobalHonour(config.gpc_global_honour === null || config.gpc_global_honour === undefined ? '' : config.gpc_global_honour ? 'true' : 'false');
    setGpcJurisdictions(config.gpc_jurisdictions ?? []);
    setInitialised(true);
  }

  const mutation = useMutation({
    mutationFn: (body: Record<string, unknown>) => updateSiteGroupConfig(groupId!, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['site-group-config', groupId] });
      // Invalidate inheritance for all sites in this group
      queryClient.invalidateQueries({ queryKey: ['sites'] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    mutation.mutate({
      blocking_mode: blockingMode || null,
      tcf_enabled: tcfEnabled === '' ? null : tcfEnabled === 'true',
      gcm_enabled: gcmEnabled === '' ? null : gcmEnabled === 'true',
      shopify_privacy_enabled: shopifyEnabled === '' ? null : shopifyEnabled === 'true',
      consent_expiry_days: consentExpiry === '' ? null : Number(consentExpiry),
      consent_sharing_enabled: consentSharing === '' ? null : consentSharing === 'true',
      consent_bridge_url: bridgeUrl || null,
      privacy_policy_url: privacyUrl || null,
      terms_url: termsUrl || null,
      gpp_enabled: gppEnabled === '' ? null : gppEnabled === 'true',
      gpp_supported_apis: gppEnabled === 'true' && gppSupportedApis.length > 0 ? gppSupportedApis : null,
      gpc_enabled: gpcEnabled === '' ? null : gpcEnabled === 'true',
      gpc_global_honour: gpcGlobalHonour === '' ? null : gpcGlobalHonour === 'true',
      gpc_jurisdictions: gpcEnabled === 'true' && gpcJurisdictions.length > 0 ? gpcJurisdictions : null,
    });
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

  if (groupLoading || configLoading) {
    return <LoadingState />;
  }

  if (!group) {
    return <div className="py-12 text-center text-sm text-status-error-fg">Group not found</div>;
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: 'configuration', label: 'Configuration' },
    { key: 'banner', label: 'Banner' },
  ];

  return (
    <div>
      {/* Header */}
      <div className="mb-4 sm:mb-6">
        <h1 className="font-heading text-4xl font-semibold tracking-tight text-foreground">
          {group.name}
        </h1>
        {group.description && (
          <p className="mt-1 text-sm text-text-secondary">{group.description}</p>
        )}
        <p className="mt-1 text-xs text-text-secondary">
          Site group &middot; {group.site_count} {group.site_count === 1 ? 'site' : 'sites'}
        </p>
      </div>

      {/* Tabs */}
      <div className="mb-4 sm:mb-6">
        <div className="flex gap-8 overflow-x-auto border-b border-border-subtle">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              className={`shrink-0 whitespace-nowrap border-b-2 pb-3 font-heading text-sm transition-colors ${
                activeTab === tab.key
                  ? 'border-copper font-medium text-foreground'
                  : 'border-transparent text-text-secondary hover:text-foreground'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div>
        {activeTab === 'configuration' && (
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Cascade explanation banner */}
            <div className="rounded-lg border border-dashed border-border bg-background p-4">
              <p className="text-xs text-text-secondary">
                <strong>Configuration cascade:</strong> System defaults &rarr; Organisation defaults
                &rarr; <span className="font-semibold">Group defaults (this page)</span> &rarr;
                Site-level config &rarr; Regional overrides. Each level only overrides fields that
                are explicitly set. Leave a field empty to inherit from the organisation or system
                default.
              </p>
            </div>

            {/* Consent settings */}
            <Card className="p-6">
              <h3 className="font-heading mb-1 text-sm font-semibold text-foreground">
                Default consent settings
              </h3>
              <p className="mb-4 text-xs text-text-secondary">
                These defaults apply to all sites in this group unless overridden at site level.
                Leave a field empty to inherit from the organisation or system default.
              </p>

              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                <FormField label="Default blocking mode">
                  <Select
                    value={blockingMode}
                    onChange={(e) => setBlockingMode(e.target.value)}
                  >
                    <option value="">Inherit from org/system</option>
                    <option value="opt_in">Opt-in (GDPR)</option>
                    <option value="opt_out">Opt-out (CCPA)</option>
                    <option value="informational">Informational only</option>
                  </Select>
                </FormField>

                <FormField label="Default consent expiry (days)">
                  <Input
                    type="number"
                    min={1}
                    max={730}
                    value={consentExpiry}
                    onChange={(e) => setConsentExpiry(e.target.value)}
                    placeholder="Inherit from org/system"
                  />
                </FormField>

                <FormField label="Cross-domain consent sharing">
                  <Select
                    value={consentSharing}
                    onChange={(e) => setConsentSharing(e.target.value)}
                  >
                    <option value="">Inherit from org/system</option>
                    <option value="true">Enabled</option>
                    <option value="false">Disabled</option>
                  </Select>
                  <p className="mt-1 text-xs text-text-secondary">
                    When enabled, consent given on one site in this group is
                    automatically shared with all other sites in the group via a
                    secure iframe bridge. Works across different domains.
                  </p>
                </FormField>

                {consentSharing === 'true' && (
                  <FormField label="Bridge domain">
                    <Input
                      type="url"
                      value={bridgeUrl}
                      onChange={(e) => setBridgeUrl(e.target.value)}
                      placeholder="https://cmp.consentos.dev"
                    />
                    <p className="mt-1 text-xs text-text-secondary">
                      The shared domain all sites in this group embed the consent
                      bridge iframe from. All sites must use the same bridge domain
                      for cross-domain consent to work.
                    </p>
                  </FormField>
                )}

                <FormField label="Default privacy policy URL">
                  <Input
                    type="url"
                    value={privacyUrl}
                    onChange={(e) => setPrivacyUrl(e.target.value)}
                    placeholder="https://example.com/privacy"
                  />
                </FormField>

                <FormField label="Default terms & conditions URL">
                  <Input
                    type="url"
                    value={termsUrl}
                    onChange={(e) => setTermsUrl(e.target.value)}
                    placeholder="https://example.com/terms"
                  />
                </FormField>
              </div>
            </Card>

            {/* Standards & integrations */}
            <Card className="p-6">
              <h3 className="font-heading mb-1 text-sm font-semibold text-foreground">
                Default standards &amp; integrations
              </h3>
              <p className="mb-4 text-xs text-text-secondary">
                Control whether standards and integrations are enabled by default for sites in this
                group.
              </p>

              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                <FormField label="IAB TCF v2.2">
                  <Select
                    value={tcfEnabled}
                    onChange={(e) => setTcfEnabled(e.target.value)}
                  >
                    <option value="">Inherit from org/system</option>
                    <option value="true">Enabled</option>
                    <option value="false">Disabled</option>
                  </Select>
                </FormField>

                <FormField label="Google Consent Mode v2">
                  <Select
                    value={gcmEnabled}
                    onChange={(e) => setGcmEnabled(e.target.value)}
                  >
                    <option value="">Inherit from org/system</option>
                    <option value="true">Enabled</option>
                    <option value="false">Disabled</option>
                  </Select>
                </FormField>

                <FormField label="Shopify Customer Privacy API">
                  <Select
                    value={shopifyEnabled}
                    onChange={(e) => setShopifyEnabled(e.target.value)}
                  >
                    <option value="">Inherit from org/system</option>
                    <option value="true">Enabled</option>
                    <option value="false">Disabled</option>
                  </Select>
                </FormField>
              </div>
            </Card>

            {/* IAB Global Privacy Platform (GPP) */}
            <Card className="p-6">
              <h3 className="font-heading mb-4 text-sm font-semibold text-foreground">
                IAB Global Privacy Platform (GPP)
              </h3>
              <p className="mb-4 text-xs text-text-secondary">
                GPP provides a standardised consent string format for US state privacy laws.
                When enabled, the banner exposes the <code>__gpp()</code> API and generates GPP
                strings for the selected sections.
              </p>

              <FormField label="Enable GPP">
                <Select
                  value={gppEnabled}
                  onChange={(e) => setGppEnabled(e.target.value)}
                >
                  <option value="">Inherit from org/system</option>
                  <option value="true">Enabled</option>
                  <option value="false">Disabled</option>
                </Select>
              </FormField>

              {gppEnabled === 'true' && (
                <div className="mt-4 space-y-2">
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

            {/* Global Privacy Control (GPC) */}
            <Card className="p-6">
              <h3 className="font-heading mb-4 text-sm font-semibold text-foreground">
                Global Privacy Control (GPC)
              </h3>
              <p className="mb-4 text-xs text-text-secondary">
                GPC is a browser signal indicating a user&apos;s intent to opt out of the sale or
                sharing of their personal data. Several US state laws (CCPA, CPA, CTDPA, TDPSA, MTCDPA)
                legally require businesses to honour this signal.
              </p>

              <div className="space-y-4">
                <FormField label="Detect GPC signal">
                  <Select
                    value={gpcEnabled}
                    onChange={(e) => setGpcEnabled(e.target.value)}
                  >
                    <option value="">Inherit from org/system</option>
                    <option value="true">Enabled</option>
                    <option value="false">Disabled</option>
                  </Select>
                </FormField>

                {gpcEnabled === 'true' && (
                  <div className="space-y-4">
                    <FormField label="Honour globally">
                      <Select
                        value={gpcGlobalHonour}
                        onChange={(e) => setGpcGlobalHonour(e.target.value)}
                      >
                        <option value="">Inherit from org/system</option>
                        <option value="true">Enabled — apply GPC opt-out for all visitors regardless of jurisdiction</option>
                        <option value="false">Disabled — only honour in selected jurisdictions</option>
                      </Select>
                    </FormField>

                    {gpcGlobalHonour !== 'true' && (
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
              </div>
            </Card>

            <div className="flex items-center gap-3">
              <Button
                type="submit"
                disabled={mutation.isPending}
              >
                {mutation.isPending ? 'Saving...' : 'Save defaults'}
              </Button>
              {saved && <Alert variant="success" className="inline-flex w-auto p-2">Saved successfully</Alert>}
              {mutation.isError && (
                <Alert variant="error" className="inline-flex w-auto p-2">Failed to save. Please try again.</Alert>
              )}
            </div>
          </form>
        )}

        {activeTab === 'banner' && config && groupId && (
          <BannerBuilderTab
            configQueryKey={['site-group-config', groupId]}
            config={config}
            onSave={(body) => updateSiteGroupConfig(groupId, body)}
          />
        )}
      </div>
    </div>
  );
}
