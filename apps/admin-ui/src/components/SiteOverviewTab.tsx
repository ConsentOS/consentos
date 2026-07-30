import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { getConsentRates } from '../api/analytics';
import { deleteSite } from '../api/sites';
import ConsentBreakdownCards from './ConsentBreakdownCards';
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
  const scriptTag = `<script src="${window.location.origin}/consent-loader.js" data-site-id="${site.id}" data-api-base="${window.location.origin}"></script>`;
  const [copied, setCopied] = useState(false);
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

  // Consent summary mirrors the Dashboard tab's 30-day window; the shared
  // query key means no duplicate fetch when both are viewed.
  const { data: rates } = useQuery({
    queryKey: ['consent-rates', site.id, 30],
    queryFn: () => getConsentRates(site.id, { days: 30 }),
  });
  const breakdown = rates?.action_breakdown;
  const decisions = breakdown
    ? breakdown.accept_all + breakdown.custom + breakdown.reject_all
    : 0;

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

      {/* Consent summary — links into the full Dashboard tab */}
      {breakdown && decisions > 0 && (
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-heading text-sm font-semibold text-foreground">
              Consent (last 30 days)
            </h3>
            <button
              type="button"
              onClick={() => navigate({ hash: 'dashboard' })}
              className="text-sm font-medium text-copper hover:underline"
            >
              View dashboard →
            </button>
          </div>
          <ConsentBreakdownCards breakdown={breakdown} rangeLabel="Last 30 days" />
        </div>
      )}

      {/* Integration snippet */}
      <Card className="p-6">
        <h3 className="font-heading mb-3 text-sm font-semibold text-foreground">Integration snippet</h3>
        <p className="mb-3 text-sm text-text-secondary">
          Add this script tag to the {'<head>'} of your website, before any other scripts.
        </p>
        <div className="flex items-stretch">
          <input
            type="text"
            readOnly
            value={scriptTag}
            className="block w-full min-w-0 rounded-l-lg border border-r-0 border-border bg-mist px-3 py-2.5 font-mono text-xs text-foreground focus:outline-none"
          />
          <button
            type="button"
            onClick={() => {
              navigator.clipboard.writeText(scriptTag).then(() => {
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
              });
            }}
            className="inline-flex shrink-0 items-center gap-2 rounded-r-lg border border-copper bg-copper px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-copper/90 focus:outline-none focus:ring-2 focus:ring-copper/50"
          >
            {copied ? (
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 6 9 17l-5-5" />
              </svg>
            ) : (
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 4h3a1 1 0 0 1 1 1v15a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h3m0 3h6m-3 5h3m-6 0h.01M12 16h3m-6 0h.01M10 3v4h4V3h-4Z" />
              </svg>
            )}
            {copied ? 'Copied!' : 'Copy'}
          </button>
        </div>
        <p className="mt-2 text-xs text-text-secondary">
          Must be the first {'<script>'} in {'<head>'}, with no <code>async</code> or <code>defer</code>.
        </p>
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
