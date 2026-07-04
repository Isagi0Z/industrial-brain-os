import React from 'react';
import { cn } from '../../lib/utils';

/** Shimmering placeholder for loading states. */
export const Skeleton: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({
  className,
  ...props
}) => (
  <div
    className={cn(
      'relative overflow-hidden rounded-md bg-muted/60',
      'before:absolute before:inset-0 before:-translate-x-full before:animate-shimmer',
      'before:bg-gradient-to-r before:from-transparent before:via-foreground/10 before:to-transparent',
      className
    )}
    {...props}
  />
);
