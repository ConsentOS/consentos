import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';

import { getSite, getSiteConfig, updateSiteConfig } from '../api/sites';
import SiteCategoriesTab from '../components/SiteCategoriesTab';
import SiteComplianceTab from '../components/SiteComplianceTab';
import SiteConfigTab from '../components/SiteConfigTab';
import SiteCookiesTab from '../components/SiteCookiesTab';
import SiteOverviewTab from '../components/SiteOverviewTab';
import BannerBuilderTab from '../components/BannerBuilderTab';
import SiteScannerTab from '../components/SiteScannerTab';
import SiteTranslationsTab from '../components/SiteTranslationsTab';
import { LoadingState } from '../components/ui/loading-state.tsx';
import { getSiteDetailTabs } from '../extensions/registry';

const CORE_TABS: { id: string; label: string; order: number }[] = [
  { id: 'overview', label: 'Overview', order: 10 },
  { id: 'config', label: 'Configuration', order: 20 },
  { id: 'categories', label: 'Categories', order: 25 },
  { id: 'cookies', label: 'Cookies', order: 30 },
  { id: 'banner', label: 'Banner', order: 40 },
  { id: 'translations', label: 'Translations', order: 50 },
  { id: 'scanner', label: 'Scans', order: 60 },
  { id: 'compliance', label: 'Compliance', order: 70 },
];

export default function SiteDetailPage() {
  const { siteId } = useParams<{ siteId: string }>();
  const [activeTab, setActiveTab] = useState<string>('overview');

  const extensionTabs = useMemo(() => getSiteDetailTabs(), []);
  const allTabs = useMemo(() => {
    const ext = extensionTabs.map((t) => ({
      id: t.id,
      label: t.label,
      order: t.order ?? 200,
    }));
    return [...CORE_TABS, ...ext].sort((a, b) => a.order - b.order);
  }, [extensionTabs]);

  const { data: site, isLoading: siteLoading } = useQuery({
    queryKey: ['sites', siteId],
    queryFn: () => getSite(siteId!),
    enabled: !!siteId,
  });

  const { data: config, isLoading: configLoading } = useQuery({
    queryKey: ['sites', siteId, 'config'],
    queryFn: () => getSiteConfig(siteId!),
    enabled: !!siteId,
  });

  if (siteLoading || configLoading) {
    return <LoadingState />;
  }

  if (!site) {
    return <div className="py-12 text-center text-sm text-status-error-fg">Site not found</div>;
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-4 sm:mb-6">
        <h1 className="font-heading text-4xl font-semibold tracking-tight text-foreground">
          {site.display_name ?? site.name ?? site.domain}
        </h1>
        <p className="mt-1 text-sm text-text-secondary">{site.domain}</p>
      </div>

      {/* Tabs — horizontally scrollable on mobile, copper underline */}
      <div className="mb-4 sm:mb-6">
        <div className="flex gap-8 overflow-x-auto border-b border-border-subtle">
          {allTabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`shrink-0 whitespace-nowrap border-b-2 pb-3 font-heading text-sm transition-colors ${
                activeTab === tab.id
                  ? 'border-copper font-medium text-foreground'
                  : 'border-transparent text-text-secondary hover:text-foreground'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content — core tabs */}
      {activeTab === 'overview' && <SiteOverviewTab site={site} config={config ?? null} />}
      {activeTab === 'config' && siteId && <SiteConfigTab siteId={siteId} config={config ?? null} />}
      {activeTab === 'categories' && siteId && (
        <SiteCategoriesTab siteId={siteId} config={config ?? null} />
      )}
      {activeTab === 'cookies' && siteId && <SiteCookiesTab siteId={siteId} />}
      {activeTab === 'banner' && siteId && (
        <BannerBuilderTab
          configQueryKey={['sites', siteId, 'config']}
          config={config ?? null}
          onSave={(body) => updateSiteConfig(siteId, body)}
          siteDomain={site.domain}
        />
      )}
      {activeTab === 'translations' && siteId && <SiteTranslationsTab siteId={siteId} />}
      {activeTab === 'scanner' && siteId && <SiteScannerTab siteId={siteId} />}
      {activeTab === 'compliance' && siteId && <SiteComplianceTab siteId={siteId} config={config ?? null} />}
      {/* Extension tabs */}
      {extensionTabs.map(
        (ext) =>
          activeTab === ext.id &&
          siteId && (
            <ext.component
              key={ext.id}
              siteId={siteId}
              site={site}
              config={config ?? null}
            />
          ),
      )}
    </div>
  );
}
