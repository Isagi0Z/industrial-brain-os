import React from 'react';
import { Sun, Moon, Monitor, Palette, User, Bell, Check } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { FadeIn } from '../components/ui/motion';
import { cn } from '../lib/utils';

const THEMES = [
  { key: 'light', label: 'Light', icon: Sun },
  { key: 'dark', label: 'Dark', icon: Moon },
  { key: 'system', label: 'System', icon: Monitor },
] as const;

export const SettingsPage: React.FC = () => {
  const { theme, setTheme } = useTheme();

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <FadeIn>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage the console appearance and your workspace preferences.
          </p>
        </div>
      </FadeIn>

      <FadeIn delay={0.05}>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Palette className="h-4 w-4 text-primary" /> Appearance
            </CardTitle>
            <CardDescription>Choose how the interface looks on this device.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-3">
              {THEMES.map((t) => {
                const active = theme === t.key;
                return (
                  <button
                    key={t.key}
                    onClick={() => setTheme(t.key)}
                    className={cn(
                      'group relative flex flex-col items-center gap-2 rounded-xl border p-4 text-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                      active
                        ? 'border-primary/50 bg-primary/5'
                        : 'border-border hover:border-primary/30 hover:bg-accent'
                    )}
                  >
                    {active && (
                      <Check className="absolute right-2 top-2 h-3.5 w-3.5 text-primary" />
                    )}
                    <t.icon
                      className={cn(
                        'h-5 w-5',
                        active ? 'text-primary' : 'text-muted-foreground'
                      )}
                    />
                    <span className={active ? 'font-medium text-foreground' : 'text-muted-foreground'}>
                      {t.label}
                    </span>
                  </button>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </FadeIn>

      <FadeIn delay={0.1}>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <User className="h-4 w-4 text-primary" /> Account
            </CardTitle>
            <CardDescription>Your workspace identity.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between rounded-lg border border-border bg-secondary/40 px-4 py-3">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-primary to-violet-500 text-xs font-semibold text-white">
                  IB
                </div>
                <div>
                  <div className="text-sm font-medium">Operator</div>
                  <div className="text-xs text-muted-foreground">Industrial Brain workspace</div>
                </div>
              </div>
              <Badge variant="success">Active</Badge>
            </div>
          </CardContent>
        </Card>
      </FadeIn>

      <FadeIn delay={0.15}>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bell className="h-4 w-4 text-primary" /> Notifications
            </CardTitle>
            <CardDescription>Alerting preferences (coming soon).</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Ingestion, evaluation, and compliance alerts will be configurable here.
            </p>
          </CardContent>
        </Card>
      </FadeIn>
    </div>
  );
};
