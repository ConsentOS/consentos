import { useState } from 'react';

import type { VersionInfo } from '../types/api';

const RELEASES_URL = 'https://github.com/ConsentOS/consentos/releases';
const UPGRADE_DOCS_URL = 'https://consentos.dev/docs/staying-up-to-date';
const DISMISS_KEY = 'consentos:update-dismissed';

/**
 * Dismissible "a new version is available" banner. Dismissal is stored
 * against the specific latest version, so it reappears when a newer
 * release than the dismissed one comes out.
 */
export default function UpdateBanner({ info }: { info: VersionInfo }) {
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(DISMISS_KEY) === info.latest,
  );

  if (!info.update_available || !info.latest || dismissed) return null;

  const dismiss = () => {
    localStorage.setItem(DISMISS_KEY, info.latest as string);
    setDismissed(true);
  };

  return (
    <div className="border-b border-copper/30 bg-copper/10">
      <div className="mx-auto flex max-w-7xl items-center gap-3 px-6 py-2 text-sm md:px-12">
        <span className="font-medium text-foreground">
          ConsentOS {info.latest} is available
        </span>
        <span className="text-text-secondary">you are on {info.current}.</span>
        <a
          href={RELEASES_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-action hover:underline"
        >
          Release notes
        </a>
        <a
          href={UPGRADE_DOCS_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-action hover:underline"
        >
          How to upgrade
        </a>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss update notice"
          className="ml-auto rounded p-1 text-text-tertiary hover:bg-copper/20 hover:text-foreground"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  );
}
