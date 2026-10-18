import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { getSiteInstall } from '../api/sites';
import type { Site } from '../types/api';
import { installSnippet, resolveInstallUrls } from '../utils/installSnippet';
import { TabGroup } from './ui/tab-group';

type Platform = 'any' | 'wordpress' | 'shopify';

const PLATFORMS: { value: Platform; label: string }[] = [
  { value: 'any', label: 'Any site' },
  { value: 'wordpress', label: 'WordPress' },
  { value: 'shopify', label: 'Shopify' },
];

interface Props {
  site: Site;
}

/** How to add the banner to a site, with the snippet for this deployment. */
export default function InstallGuide({ site }: Props) {
  const [platform, setPlatform] = useState<Platform>('any');
  const { data: install } = useQuery({
    queryKey: ['sites', site.id, 'install'],
    queryFn: () => getSiteInstall(site.id),
  });

  const snippet = installSnippet(site.id, resolveInstallUrls(install, window.location.origin));
  const domains = install?.domains ?? [site.domain, ...(site.additional_domains ?? [])];

  return (
    <div className="space-y-4">
      <TabGroup
        options={PLATFORMS}
        value={platform}
        onChange={(value) => setPlatform(value as Platform)}
      />

      {platform === 'any' && (
        <Steps>
          <li>Copy this script tag.</li>
          <li>
            Paste it into the {'<head>'} of every page, as the first {'<script>'}, so it runs
            before anything that sets cookies.
          </li>
          <li>
            Leave it exactly as it is: don't add <code>async</code> or <code>defer</code>, or other
            scripts will load before the banner can hold them back.
          </li>
        </Steps>
      )}

      {platform === 'wordpress' && (
        <Steps>
          <li>
            Install a plugin for adding code to your site's header, such as <em>WPCode</em>, and
            open its header section. Or, if you edit your theme directly, open{' '}
            <code>header.php</code>.
          </li>
          <li>
            Paste this script tag as the first thing in the header, straight after the{' '}
            {'<head>'} tag.
          </li>
          <li>
            If you use a caching or optimisation plugin that delays or combines JavaScript, exclude{' '}
            <code>consent-loader.js</code> from it.
          </li>
        </Steps>
      )}

      {platform === 'shopify' && (
        <Steps>
          <li>
            In your Shopify admin, go to <strong>Online Store</strong> then{' '}
            <strong>Themes</strong>, open the menu next to your live theme and choose{' '}
            <strong>Edit code</strong>.
          </li>
          <li>
            Open <code>layout/theme.liquid</code> and paste this script tag on the line straight
            after {'<head>'}.
          </li>
          <li>Save. Repeat for any other theme you publish.</li>
        </Steps>
      )}

      <CopyableCode code={snippet} />

      <div className="rounded-lg border border-border px-4 py-3 text-sm text-text-secondary">
        <p>
          <strong className="text-foreground">Check it worked:</strong> open your site in a
          private window. You should see your banner, or the built-in banner if you haven't
          published yet.
        </p>
        <p className="mt-2">
          The banner only works on {domains.length === 1 ? 'this domain' : 'these domains'} and
          their subdomains:{' '}
          {domains.map((domain, i) => (
            <span key={domain}>
              {i > 0 && ', '}
              <code className="rounded bg-mist px-1.5 py-0.5 font-mono text-xs">{domain}</code>
            </span>
          ))}
          .
        </p>
      </div>
    </div>
  );
}

function Steps({ children }: { children: React.ReactNode }) {
  return <ol className="list-decimal space-y-1 pl-5 text-sm text-text-secondary">{children}</ol>;
}

function CopyableCode({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <div className="flex items-stretch">
      <pre
        aria-label="Install snippet"
        className="block w-full min-w-0 overflow-x-auto rounded-l-lg border border-r-0 border-border bg-mist px-3 py-2.5 font-mono text-xs text-foreground"
      >
        {code}
      </pre>
      <button
        type="button"
        onClick={() => {
          navigator.clipboard.writeText(code).then(() => {
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
  );
}
