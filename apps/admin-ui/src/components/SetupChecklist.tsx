import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { apiErrorMessage } from '../api/revisions';
import { triggerScan } from '../api/scanner';
import { confirmBanner, dismissSetup } from '../api/setup';
import { setupQueryKey, useSiteSetup } from '../hooks/useSiteSetup';
import { useAuthStore } from '../stores/auth';
import type { SetupStep, SetupStepKey, Site, SiteSetup } from '../types/api';
import InstallationStatus from './InstallationStatus';
import InstallGuide from './InstallGuide';
import { canEdit, canPublish } from './permissions';
import PublishDialog from './PublishDialog';
import { Alert } from './ui/alert';
import { Button } from './ui/button';
import { Card } from './ui/card';

const TITLES: Record<SetupStepKey, string> = {
  scan: 'Scan your site',
  review: 'Review cookies',
  banner: 'Set up your banner',
  publish: 'Preview and publish',
  install: 'Install on your site',
  verify: "Check it's working",
};

interface Props {
  site: Site;
}

/** Guides a new site from its first scan to a working banner. */
export default function SetupChecklist({ site }: Props) {
  const { data: setup } = useSiteSetup(site.id);
  const queryClient = useQueryClient();
  const firstOpen = setup?.steps.find((s) => s.status !== 'done')?.key ?? null;
  const [chosen, setChosen] = useState<SetupStepKey | null>(null);
  const expanded = chosen ?? firstOpen;

  const dismiss = useMutation({
    mutationFn: () => dismissSetup(site.id),
    onSuccess: (result) => {
      queryClient.setQueryData(setupQueryKey(site.id), result);
      queryClient.invalidateQueries({ queryKey: ['setup-summaries'] });
    },
  });

  if (!setup || setup.dismissed) return null;

  return (
    <Card className="p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="font-heading text-sm font-semibold text-foreground">
            {setup.complete ? "You're all set" : 'Set up your site'}
          </h3>
          <p className="text-xs text-text-secondary">
            {setup.done} of {setup.total} steps done
          </p>
        </div>
        {setup.complete && (
          <Button variant="secondary" onClick={() => dismiss.mutate()} disabled={dismiss.isPending}>
            Dismiss
          </Button>
        )}
      </div>
      <ProgressBar setup={setup} />

      <ol className="mt-4 divide-y divide-border">
        {setup.steps.map((step, i) => (
          <StepRow
            key={step.key}
            number={i + 1}
            step={step}
            site={site}
            open={expanded === step.key}
            onToggle={() => setChosen(expanded === step.key ? null : step.key)}
          />
        ))}
      </ol>
    </Card>
  );
}

function ProgressBar({ setup }: { setup: SiteSetup }) {
  const percent = Math.round((setup.done / setup.total) * 100);
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-mist"
      role="progressbar"
      aria-label="Setup progress"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
    >
      <div className="h-full rounded-full bg-copper" style={{ width: `${percent}%` }} />
    </div>
  );
}

function StepRow({
  number,
  step,
  site,
  open,
  onToggle,
}: {
  number: number;
  step: SetupStep;
  site: Site;
  open: boolean;
  onToggle: () => void;
}) {
  const statusLabel = { todo: 'To do', in_progress: 'In progress', done: 'Done' }[step.status];
  return (
    <li className="py-3">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center gap-3 text-left"
      >
        <StepMark number={number} status={step.status} label={statusLabel} />
        <span className="flex-1">
          <span className="block text-sm font-medium text-foreground">{TITLES[step.key]}</span>
          <span className="block text-xs text-text-secondary">{step.detail}</span>
        </span>
      </button>
      {open && (
        <div className="mt-3 pl-9">
          <StepAction step={step} site={site} />
        </div>
      )}
    </li>
  );
}

function StepMark({
  number,
  status,
  label,
}: {
  number: number;
  status: SetupStep['status'];
  label: string;
}) {
  const style = {
    done: 'border-status-success-fg bg-status-success-bg text-status-success-fg',
    in_progress: 'border-copper text-copper',
    todo: 'border-border text-text-secondary',
  }[status];
  return (
    <span
      aria-label={label}
      className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold ${style}`}
    >
      {status === 'done' ? '✓' : number}
    </span>
  );
}

function StepAction({ step, site }: { step: SetupStep; site: Site }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const [publishing, setPublishing] = useState(false);
  const goTo = (tab: string) => navigate({ hash: tab });

  const startScan = useMutation({
    mutationFn: () => triggerScan(site.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: setupQueryKey(site.id) });
      queryClient.invalidateQueries({ queryKey: ['scans', site.id] });
    },
  });
  const confirm = useMutation({
    mutationFn: () => confirmBanner(site.id),
    onSuccess: (result) => queryClient.setQueryData(setupQueryKey(site.id), result),
  });

  switch (step.key) {
    case 'scan':
      return (
        <div className="flex flex-wrap items-center gap-2">
          {step.status === 'todo' && canEdit(user) && (
            <Button size="sm" onClick={() => startScan.mutate()} disabled={startScan.isPending}>
              Start scan
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => goTo('scanner')}>
            View scans
          </Button>
          {startScan.isError && (
            <Alert variant="error">
              {apiErrorMessage(startScan.error, "The scan couldn't start. Try again shortly.")}
            </Alert>
          )}
        </div>
      );
    case 'review':
      return (
        <Button size="sm" variant="outline" onClick={() => goTo('cookies')}>
          Review cookies
        </Button>
      );
    case 'banner':
      return (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => goTo('banner')}>
            Edit banner
          </Button>
          <Button size="sm" variant="outline" onClick={() => goTo('categories')}>
            Edit categories
          </Button>
          {step.status !== 'done' && canEdit(user) && (
            <Button size="sm" onClick={() => confirm.mutate()} disabled={confirm.isPending}>
              Looks good
            </Button>
          )}
        </div>
      );
    case 'publish':
      if (step.status === 'done') return null;
      if (!canPublish(user)) {
        return (
          <p className="text-sm text-text-secondary">
            Ask an owner or admin to publish. You can still preview the changes.
          </p>
        );
      }
      return (
        <>
          <Button size="sm" onClick={() => setPublishing(true)}>
            Review and publish
          </Button>
          {publishing && <PublishDialog siteId={site.id} onClose={() => setPublishing(false)} />}
        </>
      );
    case 'install':
      return <InstallGuide site={site} />;
    case 'verify':
      return <InstallationStatus siteId={site.id} />;
  }
}
