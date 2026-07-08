import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  BarChart3,
  CheckCircle2,
  FlaskConical,
  RefreshCw,
  ShieldCheck,
  Target,
  XCircle,
} from 'lucide-react';
import { Card } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { FadeIn, Stagger, StaggerItem } from '../components/ui/motion';
import { useAuth } from '../context/AuthContext';
import { cn } from '../lib/utils';

interface EvalRun {
  run_id: string;
  run_date: string;
  retrieval_recall: number;
  context_precision: number;
  faithfulness: number;
  hallucination_rate: number;
  total_items: number;
}

interface EvalItem {
  question: string;
  category: string;
  recall_hit: boolean;
  context_precision: number;
  faithful: boolean;
  hallucinated: boolean;
  retrieved_count: number;
}

const pct = (v: number): string => `${(v * 100).toFixed(1)}%`;

/** Colour a metric where HIGH is good. */
const goodTone = (v: number): string =>
  v >= 0.8 ? 'text-success' : v >= 0.5 ? 'text-amber-400' : 'text-destructive';
/** Colour a metric where LOW is good (hallucination). */
const badTone = (v: number): string =>
  v <= 0.05 ? 'text-success' : v <= 0.15 ? 'text-amber-400' : 'text-destructive';

const MetricCard: React.FC<{
  label: string;
  value: number | null;
  icon: React.ComponentType<{ className?: string }>;
  invert?: boolean;
  hint: string;
}> = ({ label, value, icon: Icon, invert = false, hint }) => (
  <Card interactive className="p-5">
    <div className="flex items-center justify-between">
      <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <Icon className="h-4 w-4 text-primary" />
    </div>
    <div
      className={cn(
        'mt-2 text-3xl font-semibold tabular-nums tracking-tight',
        value === null ? 'text-muted-foreground' : invert ? badTone(value) : goodTone(value),
      )}
    >
      {value === null ? '—' : pct(value)}
    </div>
    <p className="mt-1 text-[11px] text-muted-foreground">{hint}</p>
    {value !== null && (
      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-secondary">
        <div
          className={cn(
            'h-full rounded-full transition-all duration-700',
            (invert ? value <= 0.05 : value >= 0.8)
              ? 'bg-success'
              : (invert ? value <= 0.15 : value >= 0.5)
                ? 'bg-amber-400'
                : 'bg-destructive',
          )}
          style={{ width: `${Math.max(3, (invert ? 1 - value : value) * 100)}%` }}
        />
      </div>
    )}
  </Card>
);

export const EvaluationPage: React.FC = () => {
  const { token } = useAuth();
  const [latest, setLatest] = useState<EvalRun | null>(null);
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [items, setItems] = useState<EvalItem[]>([]);
  const [ranking, setRanking] = useState<{ mrr: number; ndcg: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    const headers: Record<string, string> = token
      ? { Authorization: `Bearer ${token}` }
      : {};
    try {
      const [reportRes, runsRes, baselineRes] = await Promise.all([
        fetch('/api/v1/eval/report', { headers }),
        fetch('/api/v1/eval/runs?limit=12', { headers }),
        fetch('/api/v1/eval/baseline', { headers }),
      ]);
      if (reportRes.ok) setLatest(await reportRes.json());
      else if (reportRes.status === 404)
        setError('No evaluation run yet — run `make eval` to produce one.');
      if (runsRes.ok) setRuns(await runsRes.json());
      if (baselineRes.ok) {
        const b = await baselineRes.json();
        setItems((b.items as EvalItem[]) ?? []);
        if (typeof b.mrr === 'number' && typeof b.ndcg === 'number') {
          setRanking({ mrr: b.mrr, ndcg: b.ndcg });
        }
      }
    } catch {
      setError('Failed to reach the evaluation service.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  const categories = useMemo(() => {
    const by: Record<string, { total: number; hits: number }> = {};
    for (const it of items) {
      by[it.category] = by[it.category] || { total: 0, hits: 0 };
      by[it.category].total += 1;
      if (it.recall_hit) by[it.category].hits += 1;
    }
    return Object.entries(by).sort((a, b) => b[1].total - a[1].total);
  }, [items]);

  // Oldest -> newest for the trend strip.
  const trend = useMemo(() => [...runs].reverse(), [runs]);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      {/* Header */}
      <FadeIn>
        <Card className="relative overflow-hidden p-6">
          <div className="pointer-events-none absolute -right-20 -top-24 h-56 w-56 rounded-full bg-primary/15 blur-3xl" />
          <div className="relative flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 ring-1 ring-primary/20">
                <FlaskConical className="h-6 w-6 text-primary" />
              </div>
              <div>
                <h1 className="text-xl font-semibold tracking-tight">Evaluation Dashboard</h1>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  Continuous RAG quality measurement over the golden industrial QA dataset —
                  refreshed by <code className="rounded bg-secondary px-1 font-mono text-xs">make eval</code>.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {latest && (
                <Badge variant="outline" className="font-mono text-[10px]">
                  run {latest.run_id.slice(0, 8)} · {new Date(latest.run_date).toLocaleString()}
                </Badge>
              )}
              <button
                onClick={load}
                aria-label="Refresh metrics"
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:text-primary"
              >
                <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
              </button>
            </div>
          </div>
        </Card>
      </FadeIn>

      {error && (
        <Card className="border-amber-500/40 p-4">
          <p className="text-sm text-amber-500">{error}</p>
        </Card>
      )}

      {/* Headline metrics */}
      <Stagger className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        {[
          {
            label: 'Retrieval Recall@K',
            value: latest?.retrieval_recall ?? null,
            icon: Target,
            hint: 'Golden source found in top-K retrieved chunks',
          },
          {
            label: 'Context Precision',
            value: latest?.context_precision ?? null,
            icon: BarChart3,
            hint: 'Retrieved chunks judged relevant (LLM judge)',
          },
          {
            label: 'Faithfulness',
            value: latest?.faithfulness ?? null,
            icon: ShieldCheck,
            hint: 'Answers derivable from retrieved context only',
          },
          {
            label: 'Hallucination Rate',
            value: latest?.hallucination_rate ?? null,
            icon: Activity,
            invert: true,
            hint: 'Answers citing non-retrieved sources (lower is better)',
          },
          {
            label: 'MRR',
            value: ranking?.mrr ?? null,
            icon: Target,
            hint: 'Mean reciprocal rank of the first golden source',
          },
          {
            label: 'nDCG',
            value: ranking?.ndcg ?? null,
            icon: BarChart3,
            hint: 'Ranking quality of golden sources in the top-K',
          },
        ].map((m) => (
          <StaggerItem key={m.label}>
            <MetricCard {...m} />
          </StaggerItem>
        ))}
      </Stagger>

      {/* Run history trend */}
      {trend.length > 1 && (
        <FadeIn delay={0.1}>
          <Card className="p-5">
            <div className="mb-4 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              Run history — recall / precision / faithfulness
            </div>
            <div className="flex h-28 items-end gap-2">
              {trend.map((r) => (
                <div
                  key={r.run_id}
                  className="group flex h-full flex-1 items-end justify-center gap-0.5"
                  title={`${new Date(r.run_date).toLocaleString()} — recall ${pct(r.retrieval_recall)}, precision ${pct(r.context_precision)}, faithfulness ${pct(r.faithfulness)}`}
                >
                  <div
                    className="w-2 rounded-t bg-primary/80 transition-all group-hover:bg-primary"
                    style={{ height: `${Math.max(4, r.retrieval_recall * 100)}%` }}
                  />
                  <div
                    className="w-2 rounded-t bg-amber-400/70"
                    style={{ height: `${Math.max(4, r.context_precision * 100)}%` }}
                  />
                  <div
                    className="w-2 rounded-t bg-success/70"
                    style={{ height: `${Math.max(4, r.faithfulness * 100)}%` }}
                  />
                </div>
              ))}
            </div>
          </Card>
        </FadeIn>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Per-question results */}
        <div className="lg:col-span-2">
          <div className="mb-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Per-question results {items.length > 0 && `(${items.length})`}
          </div>
          <Card className="divide-y divide-border p-0">
            {items.length === 0 && (
              <p className="p-5 text-sm text-muted-foreground">
                {loading
                  ? 'Loading…'
                  : 'No per-question detail yet — the next `make eval` run will include it.'}
              </p>
            )}
            {items.map((it, i) => (
              <div key={i} className="flex items-start gap-3 px-4 py-3">
                {it.recall_hit && it.faithful && !it.hallucinated ? (
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                ) : (
                  <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-foreground/90">{it.question}</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <Badge variant="outline" className="text-[10px]">
                      {it.category}
                    </Badge>
                    <Badge variant={it.recall_hit ? 'success' : 'destructive'} className="text-[10px]">
                      recall {it.recall_hit ? 'hit' : 'miss'}
                    </Badge>
                    <Badge variant={it.faithful ? 'success' : 'warning'} className="text-[10px]">
                      {it.faithful ? 'faithful' : 'unfaithful'}
                    </Badge>
                    {it.hallucinated && (
                      <Badge variant="destructive" className="text-[10px]">
                        hallucinated
                      </Badge>
                    )}
                    <span className="text-[10px] text-muted-foreground">
                      precision {pct(it.context_precision)} · {it.retrieved_count} chunks
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </Card>
        </div>

        {/* Category breakdown */}
        <div>
          <div className="mb-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Recall by category
          </div>
          <Card className="space-y-3 p-5">
            {categories.length === 0 && (
              <p className="text-sm text-muted-foreground">No category data yet.</p>
            )}
            {categories.map(([cat, s]) => (
              <div key={cat}>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <span className="font-medium capitalize">{cat.replace(/_/g, ' ')}</span>
                  <span className="text-muted-foreground">
                    {s.hits}/{s.total}
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
                  <div
                    className={cn(
                      'h-full rounded-full',
                      s.hits / s.total >= 0.8
                        ? 'bg-success'
                        : s.hits / s.total >= 0.5
                          ? 'bg-amber-400'
                          : 'bg-destructive',
                    )}
                    style={{ width: `${Math.max(3, (s.hits / s.total) * 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </Card>
        </div>
      </div>
    </div>
  );
};
