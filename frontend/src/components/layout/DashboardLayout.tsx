import React, { useState, useEffect } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  BookOpen,
  Wrench,
  ShieldAlert,
  GitFork,
  Lightbulb,
  Layers,
  LayoutDashboard,
  FlaskConical,
  FileText,
  Network,
  Menu,
  X,
  Search,
  Settings,
  Database,
  Sparkles,
} from 'lucide-react';
import { ThemeToggle } from '../ui/theme-toggle';
import { CommandPalette } from '../ui/command-palette';
import { cn } from '../../lib/utils';

interface DBStatus {
  postgres: string;
  neo4j: string;
  qdrant: string;
  redis: string;
  minio: string;
}

type Health = 'healthy' | 'unhealthy' | 'degraded';

const NAV_GROUPS = [
  {
    label: 'Workspace',
    items: [
      { name: 'Overview', path: '/overview', icon: LayoutDashboard },
      { name: 'Document Hub', path: '/documents', icon: FileText },
      { name: 'Knowledge Copilot', path: '/knowledge', icon: BookOpen },
      { name: 'Knowledge Graph', path: '/knowledge-graph', icon: Network },
    ],
  },
  {
    label: 'Intelligence Brains',
    items: [
      { name: 'Maintenance', path: '/maintenance', icon: Wrench },
      { name: 'Compliance', path: '/compliance', icon: ShieldAlert },
      { name: 'Root Cause', path: '/rca', icon: GitFork },
      { name: 'Lessons Learned', path: '/lessons-learned', icon: Lightbulb },
    ],
  },
  {
    label: 'Quality',
    items: [{ name: 'Evaluation', path: '/evaluation', icon: FlaskConical }],
  },
];

const HEALTH_DOT: Record<Health, string> = {
  healthy: 'bg-success',
  degraded: 'bg-amber-500',
  unhealthy: 'bg-destructive',
};

export const DashboardLayout: React.FC = () => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const location = useLocation();

  // Global Ctrl/Cmd+K command palette.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  const [dbStatus, setDbStatus] = useState<DBStatus>({
    postgres: 'checking',
    neo4j: 'checking',
    qdrant: 'checking',
    redis: 'checking',
    minio: 'checking',
  });
  const [systemHealth, setSystemHealth] = useState<Health>('healthy');

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const res = await fetch('/api/v1/health');
        const data = await res.json();
        setDbStatus(data.databases);
        setSystemHealth(data.status);
      } catch {
        setSystemHealth('unhealthy');
        setDbStatus({
          postgres: 'unhealthy',
          neo4j: 'unhealthy',
          qdrant: 'unhealthy',
          redis: 'unhealthy',
          minio: 'unhealthy',
        });
      }
    };
    fetchHealth();
    const interval = setInterval(fetchHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => setSidebarOpen(false), [location.pathname]);

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      'group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
      isActive
        ? 'bg-primary/10 text-foreground'
        : 'text-muted-foreground hover:bg-accent hover:text-foreground'
    );

  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      {/* Mobile backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/60 backdrop-blur-sm md:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-30 flex w-72 flex-col border-r border-border bg-card/70 backdrop-blur-xl transition-transform duration-200 md:static md:translate-x-0',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        {/* Brand */}
        <div className="flex h-16 items-center gap-2.5 border-b border-border px-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-amber-500 to-red-500 shadow-glow">
            <Layers className="h-4.5 w-4.5 text-white" />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-tight">Industrial Brain</div>
            <div className="font-mono text-[10px] text-muted-foreground">OS · v1.0</div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-5">
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              <div className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/70">
                {group.label}
              </div>
              <div className="space-y-0.5">
                {group.items.map((item) => (
                  <NavLink key={item.path} to={item.path} className={navLinkClass}>
                    {({ isActive }) => (
                      <>
                        <span
                          className={cn(
                            'absolute left-0 h-5 w-0.5 rounded-r-full bg-primary transition-all',
                            isActive ? 'opacity-100' : 'opacity-0'
                          )}
                        />
                        <item.icon
                          className={cn(
                            'h-4 w-4 shrink-0 transition-colors',
                            isActive
                              ? 'text-primary'
                              : 'text-muted-foreground group-hover:text-foreground'
                          )}
                        />
                        <span className="truncate">{item.name}</span>
                      </>
                    )}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* Infra status */}
        <div className="border-t border-border px-4 py-4">
          <div className="mb-2.5 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/70">
            <Database className="h-3 w-3" />
            Data Infrastructure
          </div>
          <div className="grid grid-cols-5 gap-1.5">
            {Object.entries(dbStatus).map(([db, status]) => (
              <div
                key={db}
                title={`${db}: ${status}`}
                className="flex flex-col items-center gap-1 rounded-md bg-secondary/60 py-1.5"
              >
                <span
                  className={cn(
                    'h-1.5 w-1.5 rounded-full',
                    status === 'healthy'
                      ? 'bg-success'
                      : status === 'checking'
                        ? 'bg-muted-foreground/50'
                        : 'bg-destructive'
                  )}
                />
                <span className="text-[9px] font-medium capitalize text-muted-foreground">
                  {db.slice(0, 4)}
                </span>
              </div>
            ))}
          </div>
        </div>

        <NavLink
          to="/settings"
          className={cn(navLinkClass({ isActive: false }), 'mx-3 mb-3')}
        >
          <Settings className="h-4 w-4 shrink-0" />
          Settings
        </NavLink>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-border bg-background/70 px-4 backdrop-blur-xl md:px-6">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen((o) => !o)}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:hidden"
              aria-label={sidebarOpen ? 'Close menu' : 'Open menu'}
              aria-expanded={sidebarOpen}
            >
              {sidebarOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </button>
            <div className="hidden items-center gap-2 rounded-full border border-border bg-card/60 px-3 py-1 text-xs sm:flex">
              <Sparkles className="h-3 w-3 text-primary" />
              <span className="text-muted-foreground">Enterprise Console</span>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={() => setPaletteOpen(true)}
              className="flex items-center gap-2 rounded-lg border border-border bg-card/60 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
              aria-label="Open command palette"
            >
              <Search className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Search</span>
              <kbd className="hidden rounded border border-border bg-secondary px-1.5 py-0.5 font-mono text-[10px] sm:inline">
                Ctrl K
              </kbd>
            </button>
            <div className="hidden items-center gap-2 rounded-full border border-border bg-card/60 px-3 py-1.5 text-xs sm:flex">
              <span className="relative flex h-2 w-2">
                <span
                  className={cn(
                    'absolute inline-flex h-full w-full animate-ping rounded-full opacity-60',
                    HEALTH_DOT[systemHealth]
                  )}
                />
                <span className={cn('relative inline-flex h-2 w-2 rounded-full', HEALTH_DOT[systemHealth])} />
              </span>
              <span className="capitalize text-muted-foreground">{systemHealth}</span>
            </div>
            <ThemeToggle />
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-amber-500 to-red-500 text-xs font-semibold text-white">
              IB
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-4 md:p-8">
          <Outlet />
        </main>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
};
