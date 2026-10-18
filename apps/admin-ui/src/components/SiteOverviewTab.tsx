import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { deleteSite } from '../api/sites';
import InstallGuide from './InstallGuide';
import LiveRevisionCard from './LiveRevisionCard';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { MetricCard } from './ui/metric-card';
import { Modal } from './ui/modal';
import type { Site, SiteConfig } from '../types/api';

interface Props {
  site: Site;
  config: SiteConfig | null;
}

export default function SiteOverviewTab({ site, config }: Props) {
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [confirmText, setConfirmText] = useState('');

  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const deleteMutation = useMutation({
    mutationFn: () => deleteSite(site.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sites'] });
      navigate('/sites');
    },
  });

  function closeDeleteModal() {
    setDeleteOpen(false);
    setConfirmText('');
    deleteMutation.reset();
  }

  return (
    <div className="space-y-6">
      {/* Status cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <MetricCard
          label="Status"
          value={site.is_active ? 'Active' : 'Inactive'}
          className={site.is_active ? 'text-status-success-fg' : ''}
        />
        <MetricCard
          label="Blocking mode"
          value={config?.blocking_mode?.replace('_', ' ') ?? 'Not configured'}
          className="capitalize"
        />
        <MetricCard
          label="Consent expiry"
          value={`${config?.consent_expiry_days ?? 365} days`}
        />
      </div>

      <LiveRevisionCard siteId={site.id} />

      <Card className="p-6">
        <h3 className="font-heading mb-3 text-sm font-semibold text-foreground">
          Install on your site
        </h3>
        <InstallGuide site={site} />
      </Card>

      {/* Features */}
      <Card className="p-6">
        <h3 className="font-heading mb-4 text-sm font-semibold text-foreground">Features</h3>
        <div className="grid grid-cols-2 gap-3">
          <FeatureItem label="TCF v2.3" enabled={config?.tcf_enabled ?? false} />
          <FeatureItem label="Google Consent Mode" enabled={config?.gcm_enabled ?? false} />
          <FeatureItem label="Auto-blocking" enabled={config?.blocking_mode !== 'informational'} />
          <FeatureItem label="Custom banner" enabled={!!config?.banner_config} />
        </div>
      </Card>

      <Card className="border-status-error-fg/30 p-6">
        <h3 className="font-heading mb-2 text-sm font-semibold text-status-error-fg">
          Danger zone
        </h3>
        <p className="mb-4 text-sm text-text-secondary">
          Deleting this site hides it from the dashboard and stops the banner
          from loading on the domain. Consent records are retained for audit.
          The deletion is soft, so an administrator can restore the site from
          the database if needed.
        </p>
        <Button variant="destructive" onClick={() => setDeleteOpen(true)}>
          Delete site
        </Button>
      </Card>

      <Modal
        open={deleteOpen}
        onClose={closeDeleteModal}
        title="Delete this site?"
      >
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            To confirm, type the domain{' '}
            <code className="rounded bg-mist px-1.5 py-0.5 font-mono text-xs">
              {site.domain}
            </code>{' '}
            below.
          </p>
          <input
            type="text"
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            placeholder={site.domain}
            autoFocus
            aria-label="Type the domain to confirm deletion"
            className="block w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:border-copper focus:outline-none"
          />
          {deleteMutation.isError && (
            <p className="text-sm text-status-error-fg">
              Couldn't delete the site.{' '}
              {(deleteMutation.error as Error).message ?? 'Please try again.'}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={closeDeleteModal}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={
                confirmText !== site.domain || deleteMutation.isPending
              }
              onClick={() => deleteMutation.mutate()}
            >
              {deleteMutation.isPending ? 'Deleting...' : 'Delete site'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

function FeatureItem({ label, enabled }: { label: string; enabled: boolean }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border px-3 py-2">
      <span
        className={`h-2 w-2 rounded-full ${enabled ? 'bg-status-success-fg' : 'bg-text-tertiary'}`}
      />
      <span className="text-sm text-text-secondary">{label}</span>
    </div>
  );
}
