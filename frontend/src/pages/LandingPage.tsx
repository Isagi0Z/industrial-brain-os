import React from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  Layers,
  Network,
  BookOpen,
  Wrench,
  ShieldAlert,
  GitFork,
  Lightbulb,
  Sparkles,
  FileSearch,
  Gauge,
} from 'lucide-react';
import { AuroraBackground } from '../components/ui/aurora-background';
import { buttonVariants } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { FadeIn, Stagger, StaggerItem } from '../components/ui/motion';
import { ThemeToggle } from '../components/ui/theme-toggle';
import { cn } from '../lib/utils';

const FEATURES = [
  { icon: FileSearch, title: 'Universal Ingestion', desc: 'P&IDs, SOPs, manuals, inspection & maintenance records — parsed, chunked, and indexed.' },
  { icon: Network, title: 'Hybrid GraphRAG', desc: 'Vector + BM25 + knowledge-graph traversal with cross-encoder reranking and citation validation.' },
  { icon: BookOpen, title: 'Engineering Copilot', desc: 'Cited, grounded answers over your facility’s own document library — never hallucinated.' },
  { icon: Wrench, title: 'Maintenance Intelligence', desc: 'Work orders, failure history, and OEM procedures unified into one operational brain.' },
  { icon: GitFork, title: 'Root Cause Analysis', desc: 'Structured 5-Whys and Ishikawa investigations grounded in real evidence.' },
  { icon: ShieldAlert, title: 'Compliance Intelligence', desc: 'Regulation-to-procedure gap detection with reviewer-ready evidence.' },
];

const BRAINS = [
  { icon: BookOpen, label: 'Knowledge' },
  { icon: Wrench, label: 'Maintenance' },
  { icon: ShieldAlert, label: 'Compliance' },
  { icon: GitFork, label: 'Root Cause' },
  { icon: Lightbulb, label: 'Lessons' },
];

export const LandingPage: React.FC = () => (
  <AuroraBackground>
    {/* Nav */}
    <header className="mx-auto flex max-w-7xl items-center justify-between px-6 py-6">
      <div className="flex items-center gap-2.5">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-amber-500 to-red-500 shadow-glow">
          <Layers className="h-4.5 w-4.5 text-white" />
        </div>
        <span className="text-sm font-semibold tracking-tight">Industrial Brain OS</span>
      </div>
      <div className="flex items-center gap-3">
        <ThemeToggle />
        <Link to="/knowledge" className={cn(buttonVariants({ variant: 'ghost', size: 'sm' }), 'hidden sm:inline-flex')}>
          Sign in
        </Link>
        <Link to="/knowledge" className={buttonVariants({ variant: 'gradient', size: 'sm' })}>
          Launch Console
        </Link>
      </div>
    </header>

    {/* Hero */}
    <section className="mx-auto max-w-4xl px-6 pt-16 pb-20 text-center sm:pt-24">
      <FadeIn>
        <div className="mx-auto mb-6 inline-flex items-center gap-2 rounded-full border border-border bg-card/60 px-3 py-1 text-xs text-muted-foreground backdrop-blur">
          <Sparkles className="h-3 w-3 text-primary" />
          Industrial Knowledge Intelligence · Production-grade
        </div>
      </FadeIn>
      <FadeIn delay={0.05}>
        <h1 className="text-balance text-4xl font-semibold leading-[1.05] tracking-tight sm:text-6xl">
          The unified <span className="text-gradient">Asset &amp; Operations</span> brain for industry
        </h1>
      </FadeIn>
      <FadeIn delay={0.1}>
        <p className="mx-auto mt-6 max-w-2xl text-pretty text-base text-muted-foreground sm:text-lg">
          Ingest heterogeneous engineering documents and turn them into an enterprise
          knowledge platform — hybrid GraphRAG, an expert copilot, and five specialised
          intelligence brains.
        </p>
      </FadeIn>
      <FadeIn delay={0.15}>
        <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link to="/knowledge" className={buttonVariants({ variant: 'gradient', size: 'lg' })}>
            Launch Console <ArrowRight className="h-4 w-4" />
          </Link>
          <Link to="/knowledge-graph" className={buttonVariants({ variant: 'outline', size: 'lg' })}>
            Explore the Graph
          </Link>
        </div>
      </FadeIn>
      <FadeIn delay={0.25}>
        <div className="mt-14 flex flex-wrap items-center justify-center gap-2">
          {BRAINS.map((b) => (
            <div
              key={b.label}
              className="flex items-center gap-1.5 rounded-full border border-border bg-card/50 px-3 py-1.5 text-xs text-muted-foreground backdrop-blur"
            >
              <b.icon className="h-3.5 w-3.5 text-primary" />
              {b.label}
            </div>
          ))}
        </div>
      </FadeIn>
    </section>

    {/* Features */}
    <section className="mx-auto max-w-6xl px-6 pb-24">
      <Stagger className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((f) => (
          <StaggerItem key={f.title}>
            <Card interactive className="h-full p-6">
              <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 ring-1 ring-primary/20">
                <f.icon className="h-5 w-5 text-primary" />
              </div>
              <h3 className="text-sm font-semibold">{f.title}</h3>
              <p className="mt-1.5 text-sm text-muted-foreground">{f.desc}</p>
            </Card>
          </StaggerItem>
        ))}
      </Stagger>
    </section>

    {/* CTA */}
    <section className="mx-auto max-w-5xl px-6 pb-28">
      <FadeIn>
        <Card className="relative overflow-hidden border-primary/20 p-10 text-center sm:p-14">
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary/10 via-transparent to-red-500/10" />
          <div className="relative">
            <Gauge className="mx-auto mb-4 h-8 w-8 text-primary" />
            <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
              Operational intelligence, grounded in your data
            </h2>
            <p className="mx-auto mt-3 max-w-xl text-sm text-muted-foreground">
              Observability-instrumented, evaluation-gated, and built on clean architecture.
            </p>
            <Link
              to="/knowledge"
              className={cn(buttonVariants({ variant: 'gradient', size: 'lg' }), 'mt-7')}
            >
              Open the Console <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </Card>
      </FadeIn>
    </section>

    <footer className="border-t border-border/60 py-8 text-center text-xs text-muted-foreground">
      Industrial Brain OS · Research-grade AI platform
    </footer>
  </AuroraBackground>
);
