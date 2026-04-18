import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { listSites } from '../api/sites';
import SiteConsentTab from '../components/SiteConsentTab';
import { Select } from '../components/ui/select';
import type { Site } from '../types/api';

export default function ConsentRecordsPage() {
  const [selectedSiteId, setSelectedSiteId] = useState<string>('');

  const { data: sites, isLoading: sitesLoading } = useQuery<Site[]>({
    queryKey: ['sites'],
    queryFn: listSites,
  });

  return (
    <div>
      <div className="mb-6">
        <h1 className="font-heading text-4xl font-semibold tracking-tight text-foreground">
          Consent Records
        </h1>
        <p className="mt-1 text-sm text-text-secondary">
          View and search consent records across your sites.
        </p>
      </div>

      <div className="mb-6 max-w-xs">
        <label className="mb-1.5 block text-sm font-medium text-text-secondary">
          Site
        </label>
        <Select
          value={selectedSiteId}
          onChange={(e) => setSelectedSiteId(e.target.value)}
          disabled={sitesLoading}
        >
          <option value="">Select a site…</option>
          {sites?.map((site) => (
            <option key={site.id} value={site.id}>
              {site.display_name ?? site.domain}
            </option>
          ))}
        </Select>
      </div>

      {selectedSiteId ? (
        <SiteConsentTab siteId={selectedSiteId} />
      ) : (
        <div className="py-12 text-center text-sm text-text-secondary">
          Select a site to view its consent records.
        </div>
      )}
    </div>
  );
}
