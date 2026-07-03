import React from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { DashboardLayout } from '../components/layout/DashboardLayout';
import { DocumentHub } from '../components/documents/DocumentHub';
import { DocumentDetails } from '../components/documents/DocumentDetails';
import { ChatInterface } from '../components/chat/ChatInterface';
import { KnowledgeGraphView } from '../components/graph/KnowledgeGraphView';
import {
  Wrench,
  ShieldAlert,
  GitFork,
  Lightbulb,
  Activity,
  Layers
} from 'lucide-react';

interface SubBrainStatusResponse {
  sub_brain?: string;
  status?: string;
  scaffold?: boolean;
  error?: string;
}

// Common sub-brain panel styling helper
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
      .then(res => res.json())
      .then(data => setStatus(data))
      .catch(() => setStatus({ error: "Failed to connect to API" }));
  }, [statusEndpoint]);

  return (
    <div className="max-w-5xl space-y-6">
      {/* Header Banner */}
      <div className="p-8 rounded-2xl border border-indigo-500/20 bg-slate-900/40 backdrop-blur-md relative overflow-hidden flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
        <div className="absolute top-0 right-0 w-64 h-64 rounded-full bg-indigo-500/5 blur-[80px] pointer-events-none" />
        <div className="flex items-start space-x-5">
          <div className="p-3.5 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 shadow-inner">
            <Icon className="w-8 h-8 text-indigo-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-100 mb-1">{title}</h1>
            <p className="text-slate-400 text-sm max-w-2xl leading-relaxed">{description}</p>
          </div>
        </div>
        <div className="px-4 py-2.5 rounded-xl bg-slate-950 border border-slate-900 flex items-center space-x-2 text-xs">
          <span className="text-slate-500">API Link:</span>
          <span className="font-mono text-indigo-400">/api/v1{statusEndpoint}</span>
        </div>
      </div>

      {/* Grid Content */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Left/Middle Panels: Architecture details */}
        <div className="md:col-span-2 p-6 rounded-2xl border border-slate-900 bg-slate-950/60 backdrop-blur-sm space-y-4">
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider flex items-center space-x-2">
            <Layers className="w-4 h-4 text-indigo-400" />
            <span>Architecture & Specifications</span>
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {architectureDetails.map((detail, idx) => (
              <div key={idx} className="p-4 rounded-xl bg-slate-900/40 border border-slate-900/80 flex items-start space-x-3 hover:border-slate-800 transition-colors">
                <div className="w-1.5 h-1.5 rounded-full bg-indigo-400 mt-2 flex-shrink-0" />
                <span className="text-slate-300 text-xs leading-normal">{detail}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Right Panel: Module Status Check */}
        <div className="p-6 rounded-2xl border border-slate-900 bg-slate-950/60 backdrop-blur-sm flex flex-col justify-between">
          <div>
            <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider flex items-center space-x-2 mb-4">
              <Activity className="w-4 h-4 text-indigo-400" />
              <span>Micro-Service Health</span>
            </h2>
            <div className="space-y-3">
              <div className="flex justify-between items-center py-1.5 border-b border-slate-900">
                <span className="text-xs text-slate-400">Status</span>
                <span className="text-xs text-emerald-400 font-medium">Ready</span>
              </div>
              <div className="flex justify-between items-center py-1.5 border-b border-slate-900">
                <span className="text-xs text-slate-400">Scaffold Version</span>
                <span className="text-xs text-indigo-400 font-mono">v0.1.0</span>
              </div>
              <div className="flex justify-between items-center py-1.5">
                <span className="text-xs text-slate-400">Backend Response</span>
                <span className={`text-xs font-mono px-2 py-0.5 rounded ${
                  status && !status.error ? 'bg-indigo-500/10 text-indigo-400' : 'bg-red-500/10 text-red-400'
                }`}>
                  {status ? (status.error ? 'Error' : 'Active') : 'Querying...'}
                </span>
              </div>
            </div>
          </div>

          <div className="mt-6 pt-4 border-t border-slate-900">
            <pre className="p-3.5 rounded-lg bg-slate-900 border border-slate-900/60 text-[10px] font-mono text-slate-400 overflow-x-auto">
              {status ? JSON.stringify(status, null, 2) : 'Loading...'}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
};

export const router = createBrowserRouter([
  {
    path: '/',
    element: <DashboardLayout />,
    children: [
      {
        index: true,
        element: <Navigate to="/knowledge" replace />,
      },
      {
        path: 'documents',
        element: <DocumentHub />,
      },
      {
        path: 'documents/:id',
        element: <DocumentDetails />,
      },
      {
        path: 'knowledge',
        element: <ChatInterface />,
      },
      {
        path: 'chat',
        element: <ChatInterface />,
      },
      {
        path: 'knowledge-graph',
        element: <KnowledgeGraphView />,
      },
      {
        path: 'maintenance',
        element: (
          <SubBrainPanel
            title="Maintenance Brain"
            icon={Wrench}
            description="Operational maintenance supervisor connected directly to the factory CMMS. Assists engineers in executing work orders, diagnosing failures, and querying equipment specs."
            statusEndpoint="/maintenance/status"
            architectureDetails={[
              "CMMS Work Order task scheduler linkages",
              "Real-time sensor anomaly telemetry trackers",
              "ISO 14224 standardized component mappings",
              "Equipment troubleshooting walkthrough generator"
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
            description="Automated safety manager. Constantly checks active work orders and maintenance logs against safety standards to ensure regulatory compliance."
            statusEndpoint="/compliance/status"
            architectureDetails={[
              "OSHA / EPA regulation vector matching",
              "Lockout-Tagout (LOTO) validation checkers",
              "Safety checklist validation assertion runner",
              "Audit incident report auto-generation"
            ]}
          />
        ),
      },
      {
        path: 'rca',
        element: (
          <SubBrainPanel
            title="RCA (Root Cause Analysis) Brain"
            icon={GitFork}
            description="Guides reliability engineers through root cause investigations, suggesting historical failure patterns, component stressors, and logical causality paths."
            statusEndpoint="/rca/status"
            architectureDetails={[
              "Structured 5-Whys query builders",
              "Ishikawa / Fishbone diagram generator",
              "Fault Tree analysis builders",
              "Historical failure correlation query engine"
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
            description="Captures operator logs, field comments, and retro results. Abstracts and links this operational knowledge to design work orders or maintenance tasks."
            statusEndpoint="/lessons-learned/status"
            architectureDetails={[
              "Operator comments sentiment analyzer",
              "Retro logs abstraction indexing",
              "Design error suggestion alert system",
              "Lessons categorization clustering models"
            ]}
          />
        ),
      },
      {
        path: '*',
        element: <Navigate to="/knowledge" replace />,
      },
    ],
  },
]);
