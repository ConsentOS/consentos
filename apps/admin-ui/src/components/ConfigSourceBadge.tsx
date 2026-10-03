import type { ConfigSource } from '../types/api';

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

/** Badge showing which cascade level a field's value came from. Hidden for site-level values. */
export function SourceBadge({ source, field }: { source: ConfigSource; field: string }) {
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
 * Button to reset a field to its inherited default. Only shown when
 * the field is currently overridden at the level being edited.
 */
export function ResetButton({
  source,
  parentSource,
  onReset,
}: {
  source: ConfigSource | undefined;
  parentSource: ConfigSource | null;
  onReset: () => void;
}) {
  if (source !== 'site') return null;

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
