import React from 'react';
import { Sun, Moon, Monitor } from 'lucide-react';
import { useTheme } from '../../context/ThemeContext';
import { cn } from '../../lib/utils';

const ORDER = ['light', 'dark', 'system'] as const;
const ICON = { light: Sun, dark: Moon, system: Monitor } as const;
const LABEL = { light: 'Light', dark: 'Dark', system: 'System' } as const;

export const ThemeToggle: React.FC<{ className?: string }> = ({ className }) => {
  const { theme, setTheme } = useTheme();
  const current = (['light', 'dark', 'system'] as const).includes(
    theme as (typeof ORDER)[number]
  )
    ? (theme as (typeof ORDER)[number])
    : 'system';
  const Icon = ICON[current];

  const cycle = () => {
    const next = ORDER[(ORDER.indexOf(current) + 1) % ORDER.length];
    setTheme(next);
  };

  return (
    <button
      onClick={cycle}
      title={`Theme: ${LABEL[current]}`}
      aria-label={`Switch theme (currently ${LABEL[current]})`}
      className={cn(
        'inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-card/60 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        className
      )}
    >
      <Icon className="h-4 w-4" />
    </button>
  );
};
