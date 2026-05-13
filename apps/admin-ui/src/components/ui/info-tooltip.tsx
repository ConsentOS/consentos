import { useId, useState, type ReactNode } from 'react';

import { cn } from '../../lib/utils.ts';

interface Props {
  content: ReactNode;
  label?: string;
  className?: string;
  width?: string;
}

/**
 * Small `?` trigger that reveals contextual help on hover or focus.
 * Tap-to-focus opens it on touch devices.
 */
export function InfoTooltip({
  content,
  label = 'More information',
  className,
  width = 'w-80',
}: Props) {
  const [open, setOpen] = useState(false);
  const id = useId();

  return (
    <span className={cn('relative ml-2 inline-flex items-center', className)}>
      <button
        type="button"
        aria-label={label}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-border bg-surface text-[10px] font-semibold leading-none text-text-secondary transition-colors hover:border-copper hover:text-copper focus:outline-none focus:ring-2 focus:ring-copper/40"
      >
        ?
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className={cn(
            'absolute left-6 top-1/2 z-50 -translate-y-1/2 rounded-lg border border-border bg-card p-3 text-xs leading-relaxed text-text-secondary shadow-lg',
            width,
          )}
        >
          {content}
        </span>
      )}
    </span>
  );
}
