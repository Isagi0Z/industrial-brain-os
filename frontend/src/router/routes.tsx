import React from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { DashboardLayout } from '../components/layout/DashboardLayout';
import { DocumentHub } from '../components/documents/DocumentHub';
import { DocumentDetails } from '../components/documents/DocumentDetails';
import { ChatInterface } from '../components/chat/ChatInterface';
import { KnowledgeGraphView } from '../components/graph/KnowledgeGraphView';
import { LandingPage } from '../pages/LandingPage';
import { LoginPage } from '../pages/LoginPage';
import { SettingsPage } from '../pages/SettingsPage';
import { NotFound } from '../pages/NotFound';
import { Card } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { FadeIn, Stagger, StaggerItem } from '../components/ui/motion';
import { Wrench, ShieldAlert, GitFork, Lightbulb, Activity, CheckCircle2 } from 'lucide-react';

interface SubBrainStatusResponse {
  sub_brain?: string;
  status?: string;
  scaffold?: boolean;
  error?: string;
}

const SubBrainPanel: React.FC<{
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
  architectureDetails: string[];
  statusEndpoint: string;
}> = ({ title, icon: Icon, description, architectureDetails, statusEndpoint }) => {
  const [status, setStatus] = React.useState<SubBrainStatusResponse | null>(null);

  React.useEffect(() => {
    fetch(`/api/v1${statusEndpoint}`)
      .then((res) => res.json())
      .then((data) => setStatus(data))
      .catch(() => setStatus({ error: 'Failed to connect to API' }));
  }, [statusEndpoint]);

  const online = status && !status.error;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <FadeIn>
        <Card className="relative overflow-hidden p-8">
          <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-primary/10 blur-3xl" />
          <div className="relative flex flex-col items-start justify-between gap-5 md:flex-row md:items-center">
            <div className="flex items-start gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 ring-1 ring-primary/20">
                <Icon className="h-7 w-7 text-primary" />
              </div>
              <div>
                <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
                <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>
              </div>
            </div>
            <Badge variant={online ? 'success' : 'warning'} className="shrink-0">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-60" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
              </span>
              {status ? (online ? 'Online' : 'Error') : 'Connecting…'}
            </Badge>
          </div>
        </Card>
      </FadeIn>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            <Activity className="h-3.5 w-3.5 text-primary" /> Architecture &amp; Capabilities
          </div>
          <Stagger className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {architectureDetails.map((detail) => (
              <StaggerItem key={detail}>
                <Card interactive className="flex h-full items-start gap-3 p-4">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <span className="text-sm text-foreground/90">{detail}</span>
                </Card>
              </StaggerItem>
            ))}
          </Stagger>
        </div>

        <FadeIn delay={0.1}>
          <Card className="p-5">
            <div className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              <Activity className="h-3.5 w-3.5 text-primary" /> Service Health
            </div>
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between border-b border-border pb-2">
                <span className="text-muted-foreground">Status</span>
                <Badge variant={online ? 'success' : 'warning'}>
                  {online ? 'Ready' : 'Offline'}
                </Badge>
              </div>
              <div className="flex items-center justify-between border-b border-border pb-2">
                <span className="text-muted-foreground">Endpoint</span>
                <span className="font-mono text-xs text-primary">/api/v1{statusEndpoint}</span>
              </div>
              <pre className="mt-2 overflow-x-auto rounded-lg border border-border bg-secondary/50 p-3 font-mono text-[10px] text-muted-foreground">
                {status ? JSON.stringify(status, null, 2) : 'Loading…'}
              </pre>
            </div>
          </Card>
        </FadeIn>
      </div>
    </div>
  );
};

export const router = createBrowserRouter([
  { path: '/', element: <LandingPage /> },
  { path: '/login', element: <LoginPage /> },
  {
    element: <DashboardLayout />,
    errorElement: <NotFound />,
    children: [
      { path: 'documents', element: <DocumentHub /> },
      { path: 'documents/:id', element: <DocumentDetails /> },
      { path: 'knowledge', element: <ChatInterface /> },
      { path: 'chat', element: <Navigate to="/knowledge" replace /> },
      { path: 'knowledge-graph', element: <KnowledgeGraphView /> },
      { path: 'settings', element: <SettingsPage /> },
      {
        path: 'maintenance',
        element: (
          <SubBrainPanel
            title="Maintenance Brain"
            icon={Wrench}
            description="Operational maintenance supervisor connected to the factory CMMS. Executes work orders, diagnoses failures, and queries equipment specs."
            statusEndpoint="/maintenance/status"
            architectureDetails={[
              'CMMS work-order task scheduler linkages',
              'Real-time sensor anomaly telemetry trackers',
              'ISO 14224 standardized component mappings',
              'Equipment troubleshooting walkthrough generator',
            ]}
          />
        ),
      },
      {
        path: 'compliance',
        element: (
          <SubBrainPanel
            title="Compliance Brain"
            icon={ShieldAlert}
            description="Automated safety manager. Continuously checks work orders and maintenance logs against safety standards for regulatory compliance."
            statusEndpoint="/compliance/status"
            architectureDetails={[
              'OSHA / EPA regulation vector matching',
              'Lockout-Tagout (LOTO) validation checkers',
              'Safety checklist assertion runner',
              'Audit incident report auto-generation',
            ]}
          />
        ),
      },
      {
        path: 'rca',
        element: (
          <SubBrainPanel
            title="Root Cause Analysis Brain"
            icon={GitFork}
            description="Guides reliability engineers through root-cause investigations with historical failure patterns and logical causality paths."
            statusEndpoint="/rca/status"
            architectureDetails={[
              'Structured 5-Whys query builders',
              'Ishikawa / Fishbone diagram generator',
              'Fault-tree analysis builders',
              'Historical failure correlation engine',
            ]}
          />
        ),
      },
      {
        path: 'lessons-learned',
        element: (
          <SubBrainPanel
            title="Lessons Learned Brain"
            icon={Lightbulb}
            description="Captures operator logs and field comments, abstracting operational knowledge into reusable lessons linked to assets."
            statusEndpoint="/lessons-learned/status"
            architectureDetails={[
              'Operator comment sentiment analyzer',
              'Retro log abstraction indexing',
              'Design-error suggestion alerts',
              'Lessons categorization clustering',
            ]}
          />
        ),
      },
    ],
  },
  { path: '*', element: <NotFound /> },
]);
