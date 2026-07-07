import React, { useCallback, useState } from 'react';
import {
  GitFork,
  Loader2,
  HelpCircle,
  CheckCircle2,
  RotateCcw,
  Fish,
} from 'lucide-react';
import { Card } from '../ui/card';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';

interface WhyStep {
  question: string;
  answer: string | null;
}

interface RCAReport {
  problem_statement: string;
  root_cause: string;
  contributing_factors: string[];
  recommended_actions: string[];
  evidence_citations: string[];
  fishbone: Record<string, string[]>;
  generated_at: string;
}

interface RCASession {
  session_id: string;
  asset_tag: string;
  incident_description: string;
  status: string;
  whys: WhyStep[];
  next_why: string | null;
  report: RCAReport | null;
}

const ENDPOINT = '/api/v1/brain/rca/session';

export const RcaBrainPage: React.FC = () => {
  const [assetTag, setAssetTag] = useState('');
  const [incident, setIncident] = useState('');
  const [session, setSession] = useState<RCASession | null>(null);
  const [answer, setAnswer] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const post = useCallback(async (body: Record<string, unknown>) => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail || data?.message || `Request failed (${res.status})`);
      }
      const data = (await res.json()) as RCASession;
      setSession(data);
      setAnswer('');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Request failed');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const start = () => {
    if (!assetTag.trim() || !incident.trim()) return;
    post({ asset_tag: assetTag.trim(), incident_description: incident.trim() });
  };

  const advance = () => {
    if (!answer.trim() || !session) return;
    post({ session_id: session.session_id, answer: answer.trim() });
  };

  const reset = () => {
    setSession(null);
    setAssetTag('');
    setIncident('');
    setAnswer('');
    setError(null);
  };

  const report = session?.report ?? null;

  return (
    <div className="mx-auto max-w-4xl space-y-4 pb-10">
      {/* Header */}
      <Card className="relative overflow-hidden p-5">
        <div className="pointer-events-none absolute -right-16 -top-16 h-40 w-40 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 ring-1 ring-primary/20">
            <GitFork className="h-6 w-6 text-primary" />
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="text-xl font-semibold tracking-tight">
              Root Cause Analysis Brain
            </h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Guided 5-Whys investigation with a structured root-cause report and
              Ishikawa (fishbone) breakdown.
            </p>
          </div>
          {session && (
            <Button variant="ghost" size="sm" onClick={reset} disabled={isLoading}>
              <RotateCcw className="h-4 w-4" /> New
            </Button>
          )}
        </div>
      </Card>

      {error && (
        <Card className="border-destructive/40 p-4">
          <p className="text-sm text-destructive">⚠️ {error}</p>
        </Card>
      )}

      {/* Start form */}
      {!session && (
        <Card className="space-y-4 p-6">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
              Asset tag
            </label>
            <input
              value={assetTag}
              onChange={(e) => setAssetTag(e.target.value)}
              placeholder="e.g. P-102A"
              className="w-full rounded-lg border border-input bg-background/60 px-3 py-2 text-sm focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
              Incident description
            </label>
            <textarea
              value={incident}
              onChange={(e) => setIncident(e.target.value)}
              placeholder="Describe what failed, when, and the observed symptoms…"
              rows={4}
              className="w-full resize-none rounded-lg border border-input bg-background/60 px-3 py-2 text-sm focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <Button
            variant="gradient"
            onClick={start}
            disabled={!assetTag.trim() || !incident.trim() || isLoading}
          >
            {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <GitFork className="h-4 w-4" />}
            Begin 5-Whys investigation
          </Button>
        </Card>
      )}

      {/* Active investigation */}
      {session && (
        <>
          <Card className="p-5">
            <div className="mb-2 flex items-center gap-2">
              <Badge variant="default" className="font-mono">
                {session.asset_tag}
              </Badge>
              <Badge variant={report ? 'success' : 'warning'}>
                {report ? 'Complete' : session.status}
              </Badge>
            </div>
            <p className="text-sm text-foreground/90">{session.incident_description}</p>
          </Card>

          {/* Whys chain */}
          <Card className="space-y-4 p-5">
            <div className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              5-Whys Chain
            </div>
            <ol className="space-y-3">
              {session.whys.map((w, i) => (
                <li key={i} className="flex gap-3">
                  <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary ring-1 ring-primary/20">
                    {i + 1}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="flex items-start gap-1.5 text-sm text-foreground">
                      <HelpCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                      {w.question}
                    </p>
                    {w.answer && (
                      <p className="mt-1 rounded-lg border border-border bg-secondary/40 px-3 py-2 text-sm text-foreground/80">
                        {w.answer}
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ol>

            {/* Answer input for the pending why */}
            {session.next_why && !report && (
              <div className="space-y-2 border-t border-border pt-4">
                <p className="text-sm font-medium text-foreground">
                  Answer to continue:
                </p>
                <textarea
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  placeholder="Your answer to the question above…"
                  rows={2}
                  className="w-full resize-none rounded-lg border border-input bg-background/60 px-3 py-2 text-sm focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-ring"
                />
                <Button
                  variant="gradient"
                  onClick={advance}
                  disabled={!answer.trim() || isLoading}
                >
                  {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Submit answer
                </Button>
              </div>
            )}
          </Card>

          {/* Final report */}
          {report && (
            <Card className="space-y-5 p-6">
              <div className="flex items-center gap-2 text-success">
                <CheckCircle2 className="h-5 w-5" />
                <span className="text-sm font-semibold">Root Cause Analysis Report</span>
              </div>

              <div>
                <div className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                  Root Cause
                </div>
                <p className="mt-1 rounded-lg border border-primary/30 bg-primary/5 px-4 py-3 text-sm text-foreground">
                  {report.root_cause}
                </p>
              </div>

              {report.contributing_factors.length > 0 && (
                <div>
                  <div className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                    Contributing Factors
                  </div>
                  <ul className="mt-2 space-y-1.5">
                    {report.contributing_factors.map((f, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-foreground/90">
                        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                        {f}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {report.recommended_actions.length > 0 && (
                <div>
                  <div className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                    Recommended Actions
                  </div>
                  <ul className="mt-2 space-y-1.5">
                    {report.recommended_actions.map((a, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-foreground/90">
                        <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />
                        {a}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {Object.keys(report.fishbone).length > 0 && (
                <div>
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                    <Fish className="h-3.5 w-3.5 text-primary" /> Ishikawa (Fishbone)
                  </div>
                  <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {Object.entries(report.fishbone).map(([category, causes]) => (
                      <div
                        key={category}
                        className="rounded-lg border border-border bg-secondary/40 p-3"
                      >
                        <p className="text-xs font-semibold text-primary">{category}</p>
                        <ul className="mt-1.5 space-y-1">
                          {causes.map((c, i) => (
                            <li key={i} className="text-[13px] text-foreground/80">
                              • {c}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Card>
          )}
        </>
      )}
    </div>
  );
};
