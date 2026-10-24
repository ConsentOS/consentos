import type { ReactNode } from "react";

import { cn } from "../../lib/utils.ts";

interface EmptyStateProps {
  message: string;
  className?: string;
  action?: ReactNode;
}

function EmptyState({ message, className, action }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "rounded-lg border border-dashed border-border-subtle p-8 text-center",
        className,
      )}
    >
      <p className="text-sm text-muted-foreground">{message}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export { EmptyState };
export type { EmptyStateProps };
