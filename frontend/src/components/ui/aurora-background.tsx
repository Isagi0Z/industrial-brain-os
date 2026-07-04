import React from 'react';
import { cn } from '../../lib/utils';

/**
 * Ambient aurora + grid backdrop (Aceternity-style). Purely decorative —
 * animated gradient blobs behind frosted content. Respects reduced motion.
 */
export const AuroraBackground: React.FC<{
  children: React.ReactNode;
  className?: string;
}> = ({ children, className }) => (
  <div className={cn('relative min-h-screen w-full overflow-hidden bg-background', className)}>
    {/* Grid */}
    <div className="pointer-events-none absolute inset-0 bg-grid [mask-image:radial-gradient(ellipse_at_center,black,transparent_75%)] opacity-40" />
    {/* Aurora blobs */}
    <div
      aria-hidden="true"
      className="pointer-events-none absolute -top-40 left-1/2 h-[36rem] w-[36rem] -translate-x-1/2 rounded-full bg-primary/25 blur-[130px] motion-safe:animate-pulse-slow"
    />
    <div
      aria-hidden="true"
      className="pointer-events-none absolute -bottom-40 -right-20 h-[30rem] w-[30rem] rounded-full bg-fuchsia-500/20 blur-[130px] motion-safe:animate-pulse-slow"
    />
    <div
      aria-hidden="true"
      className="pointer-events-none absolute -bottom-32 -left-24 h-[26rem] w-[26rem] rounded-full bg-violet-600/20 blur-[130px] motion-safe:animate-pulse-slow"
    />
    <div className="relative z-10">{children}</div>
  </div>
);
