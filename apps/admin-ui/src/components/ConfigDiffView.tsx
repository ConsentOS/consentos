import { SOURCE_LABELS, changeLabel, formatValue } from './configDiff';
import { Badge } from './ui/badge';
import type { DiffChange } from '../types/api';

const AREAS: { id: DiffChange['area']; label: string }[] = [
  { id: 'settings', label: 'Settings' },
  { id: 'banner', label: 'Banner' },
  { id: 'translations', label: 'Translations' },
  { id: 'categories', label: 'Categories' },
  { id: 'cookies', label: 'Cookie rules' },
  { id: 'other', label: 'Other' },
];

interface Props {
  changes: DiffChange[];
}

export default function ConfigDiffView({ changes }: Props) {
  if (changes.length === 0) {
    return <p className="text-sm text-text-secondary">No differences.</p>;
  }
  return (
    <div className="space-y-4">
      {AREAS.map(({ id, label }) => {
        const inArea = changes.filter((change) => change.area === id);
        if (inArea.length === 0) return null;
        return (
          <section key={id}>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-secondary">
              {label}
            </h4>
            <ul className="space-y-2">
              {inArea.map((change) => (
                <li key={change.key} className="rounded-md border border-border-subtle p-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-foreground">{changeLabel(change)}</span>
                    {change.source !== 'site' && (
                      <Badge variant="info">{SOURCE_LABELS[change.source]}</Badge>
                    )}
                  </div>
                  <div className="mt-1 break-words text-text-secondary">
                    <span className="line-through">{formatValue(change, change.before)}</span>
                    {' → '}
                    <span className="text-foreground">{formatValue(change, change.after)}</span>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
