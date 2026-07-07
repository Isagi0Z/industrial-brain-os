import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  FileText,
  Flame,
  GitFork,
  Layers,
  Lightbulb,
  Network,
  RefreshCw,
  ShieldAlert,
  Wrench,
  XCircle,
} from 'lucide-react';
import { Card } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { FadeIn, Stagger, StaggerItem } from '../components/ui/motion';
import { useAuth } from '../context/AuthContext';
import { cn } from '../lib/utils';

interface DocumentRow {
  id: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
  job_status: string | null;
}

interface HealthResponse {
  status: string;
  databases: Record<string, string>;
}

const DONE_STATES = new Set(['COMPLETED']);
const FAILED_STATES = new Set(['FAILED', 'PARSE_FAILED', 'ERROR']);

const BRAIN_LINKS = [
  {
    to: '/knowledge',
    icon: BookOpen,
    title: 'Knowledge Copilot',
    blurb: 'Grounded Q&A over the whole document library',
  },
  {
    to: '/maintenance',
    icon: Wrench,
    title: 'Maintenance Brain',
    blurb: 'Work orders, failure history, troubleshooting',
  },
  {
    to: '/compliance',
    icon: ShieldAlert,
    title: 'Compliance Brain',
    blurb: 'Regulation-vs-procedure gap detection',
  },
  {
    to: '/rca',
    icon: GitFork,
    title: 'Root Cause Analysis',
    blurb: 'Guided 5-Whys investigations with reports',
  },
  {
    to: '/lessons-learned',
    icon: Lightbulb,
    title: 'Lessons Learned',
    blurb: 'Answers from captured incident knowledge',
  },
  {
    to: '/knowledge-graph',
    icon: Network,
    title: 'Knowledge Graph',
    blurb: 'Travel the live asset ontology',
  },
];

const statusTone = (s: string | null): 'success' | 'warning' | 'destructive' | 'secondary' => {
  if (!s) return 'secondary';
  if (DONE_STATES.has(s)) return 'success';
  if (FAILED_STATES.has(s)) return 'destructive';
  return 'warning';
};

const fmtBytes = (n: number): string =>
  n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;

export const OverviewPage: React.FC = () => {
  const { token } = useAuth();
  const [docs, setDocs] = useState<DocumentRow[]>([]);
  const [total, setTotal] = useState(0);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [docsRes, healthRes] = await Promise.all([
        // Explicit auth header: on first mount this fetch can fire before the
        // global interceptor is installed (child effects run before parents').
        fetch('/api/v1/documents/?limit=100', {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        }),
        fetch('/api/v1/health'),
      ]);
      if (docsRes.ok) {
        const d = await docsRes.json();
        setDocs(d.documents ?? []);
        setTotal(d.total ?? 0);
      }
      if (healthRes.ok) setHealth(await healthRes.json());
    } catch {
      /* surfaces via the health chip */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const stats = useMemo(() => {
    const done = docs.filter((d) => DONE_STATES.has(d.job_status ?? '')).length;
    const failed = docs.filter((d) => FAILED_STATES.has(d.job_status ?? '')).length;
    const processing = docs.length - done - failed;
    return { done, failed, processing };
  }, [docs]);

  const healthy = health?.status === 'healthy';
  const dbsUp = health ? Object.values(health.databases).filter((s) => s === 'healthy').length : 0;
  const dbsTotal = health ? Object.keys(health.databases).length : 5;
  const recent = docs.slice(0, 5);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      {/* Hero */}
      <FadeIn>
        <Card className="relative overflow-hidden p-7">
          <div className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-primary/15 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-24 left-1/3 h-56 w-56 rounded-full bg-red-500/10 blur-3xl" />
          <div className="relative flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-amber-500 to-red-500 shadow-glow">
                <Flame className="h-7 w-7 text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-semibold tracking-tight">Operations Overview</h1>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  Your facility's knowledge, live — ingestion, intelligence brains, and infrastructure at a glance.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={healthy ? 'success' : 'warning'} className="gap-1.5">
                <Activity className="h-3 w-3" />
                {health ? `${dbsUp}/${dbsTotal} systems online` : 'checking…'}
              </Badge>
              <button
                onClick={load}
                aria-label="Refresh overview"
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:text-primary"
              >
                <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
              </button>
            </div>
          </div>
        </Card>
      </FadeIn>

      {/* Stats */}
      <Stagger className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          { label: 'Documents', value: total, icon: FileText, tone: 'text-primary' },
          { label: 'Fully processed', value: stats.done, icon: CheckCircle2, tone: 'text-success' },
          { label: 'In pipeline', value: stats.processing, icon: Layers, tone: 'text-amber-400' },
          { label: 'Failed', value: stats.failed, icon: XCircle, tone: 'text-destructive' },
        ].map((s) => (
          <StaggerItem key={s.label}>
            <Card interactive className="p-5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {s.label}
                </span>
                <s.icon className={cn('h-4 w-4', s.tone)} />
              </div>
              <div className="mt-2 text-3xl font-semibold tabular-nums tracking-tight">
                {loading ? '—' : s.value}
              </div>
            </Card>
          </StaggerItem>
        ))}
      </Stagger>

      {/* Ingestion pipeline bar */}
      {total > 0 && (
        <FadeIn delay={0.1}>
          <Card className="p-5">
            <div className="mb-3 flex items-center justify-between text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              <span>Ingestion pipeline</span>
              <span className="font-normal normal-case">
                {stats.done}/{docs.length} complete
              </span>
            </div>
            <div className="flex h-2.5 w-full gap-0.5 overflow-hidden rounded-full bg-secondary">
              {stats.done > 0 && (
                <div
                  className="rounded-full bg-success transition-all duration-700"
                  style={{ width: `${(stats.done / docs.length) * 100}%` }}
                />
              )}
              {stats.processing > 0 && (
                <div
                  className="ai-shimmer rounded-full transition-all duration-700"
                  style={{ width: `${(stats.processing / docs.length) * 100}%` }}
                />
              )}
              {stats.failed > 0 && (
                <div
                  className="rounded-full bg-destructive transition-all duration-700"
                  style={{ width: `${(stats.failed / docs.length) * 100}%` }}
                />
              )}
            </div>
          </Card>
        </FadeIn>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Brains launcher */}
        <div className="lg:col-span-2">
          <div className="mb-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Intelligence
          </div>
          <Stagger className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {BRAIN_LINKS.map((b) => (
              <StaggerItem key={b.to}>
                <Link to={b.to} className="group block">
                  <Card
                    interactive
                    className="flex h-full items-start gap-3.5 p-4 transition-shadow group-hover:shadow-card-hover"
                  >
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 ring-1 ring-primary/20 transition-colors group-hover:bg-primary/20">
                      <b.icon className="h-5 w-5 text-primary" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-semibold">{b.title}</span>
                        <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground">{b.blurb}</p>
                    </div>
                  </Card>
                </Link>
              </StaggerItem>
            ))}
          </Stagger>
        </div>

        {/* Recent documents */}
        <div>
          <div className="mb-3 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              Recent documents
            </span>
            <Link to="/documents" className="text-xs text-primary underline-offset-2 hover:underline">
              view all
            </Link>
          </div>
          <Card className="divide-y divide-border p-0">
            {recent.length === 0 && (
              <div className="p-5 text-sm text-muted-foreground">
                {loading ? 'Loading…' : 'No documents yet — upload some in the Document Hub.'}
              </div>
            )}
            {recent.map((d) => (
              <Link
                key={d.id}
                to={`/documents/${d.id}`}
                className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-accent/50"
              >
                <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{d.original_filename}</p>
                  <p className="text-[11px] text-muted-foreground">{fmtBytes(d.size_bytes)}</p>
                </div>
                <Badge variant={statusTone(d.job_status)} className="shrink-0 text-[10px]">
                  {(d.job_status ?? 'UNKNOWN').toLowerCase().replace(/_/g, ' ')}
                </Badge>
              </Link>
            ))}
          </Card>
        </div>
      </div>
    </div>
  );
};
