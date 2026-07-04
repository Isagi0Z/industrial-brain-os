import React from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '../../lib/utils';

export const Spinner: React.FC<{ className?: string }> = ({ className }) => (
  <Loader2 className={cn('animate-spin text-primary', className)} aria-hidden="true" />
);

/** Full-surface centered loading indicator with an optional label. */
export const LoadingState: React.FC<{ label?: string; className?: string }> = ({
  label = 'Loading…',
  className,
}) => (
  <div
    className={cn('flex flex-col items-center justify-center gap-3 py-16', className)}
    role="status"
    aria-live="polite"
  >
    <Spinner className="h-6 w-6" />
    <p className="text-sm text-muted-foreground">{label}</p>
  </div>
);
