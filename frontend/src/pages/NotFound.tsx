import React from 'react';
import { Link, useRouteError, isRouteErrorResponse } from 'react-router-dom';
import { Home, Compass } from 'lucide-react';
import { AuroraBackground } from '../components/ui/aurora-background';
import { buttonVariants } from '../components/ui/button';
import { FadeIn } from '../components/ui/motion';
import { cn } from '../lib/utils';

/** Serves both the 404 route and the router errorElement. */
export const NotFound: React.FC = () => {
  const error = useRouteError();
  const status = isRouteErrorResponse(error) ? error.status : 404;
  const title = status === 404 ? 'Page not found' : 'Something went wrong';
  const message =
    status === 404
      ? 'The page you’re looking for doesn’t exist or has moved.'
      : 'An unexpected error occurred while rendering this view.';

  return (
    <AuroraBackground className="flex items-center justify-center px-6">
      <FadeIn className="text-center">
        <div className="text-gradient text-8xl font-bold tracking-tighter">{status}</div>
        <h1 className="mt-4 text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">{message}</p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <Link to="/" className={buttonVariants({ variant: 'gradient' })}>
            <Home className="h-4 w-4" /> Home
          </Link>
          <Link to="/knowledge" className={cn(buttonVariants({ variant: 'outline' }))}>
            <Compass className="h-4 w-4" /> Console
          </Link>
        </div>
      </FadeIn>
    </AuroraBackground>
  );
};
