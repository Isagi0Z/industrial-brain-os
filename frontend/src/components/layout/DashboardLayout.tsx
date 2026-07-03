import React, { useState, useEffect } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import {
  BookOpen,
  Wrench,
  ShieldAlert,
  GitFork,
  Lightbulb,
  Sun,
  Moon,
  Terminal,
  Activity,
  Layers,
  ChevronRight,
  FileText,
  Network,
  Menu,
  X
} from 'lucide-react';
import { useTheme } from '../../context/ThemeContext';

interface DBStatus {
  postgres: string;
  neo4j: string;
  qdrant: string;
  redis: string;
  minio: string;
}

export const DashboardLayout: React.FC = () => {
  const { theme, setTheme } = useTheme();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dbStatus, setDbStatus] = useState<DBStatus>({
    postgres: 'checking',
    neo4j: 'checking',
    qdrant: 'checking',
    redis: 'checking',
    minio: 'checking'
  });
  const [systemHealth, setSystemHealth] = useState<'healthy' | 'unhealthy' | 'degraded'>('healthy');

  // Fetch health check status
  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const res = await fetch('/api/v1/health');
        const data = await res.json();
        setDbStatus(data.databases);
        setSystemHealth(data.status);
      } catch (err) {
        setSystemHealth('unhealthy');
        setDbStatus({
          postgres: 'unhealthy',
          neo4j: 'unhealthy',
          qdrant: 'unhealthy',
          redis: 'unhealthy',
          minio: 'unhealthy'
        });
      }
    };

    fetchHealth();
    const interval = setInterval(fetchHealth, 10000); // Check every 10 seconds
    return () => clearInterval(interval);
  }, []);

  const navItems = [
    { name: 'Document Hub', path: '/documents', icon: FileText, desc: 'Central document management and storage' },
    { name: 'Knowledge Copilot', path: '/knowledge', icon: BookOpen, desc: 'Chat with indexed documents — cited answers' },
    { name: 'Knowledge Graph', path: '/knowledge-graph', icon: Network, desc: 'Interactive Neo4j subgraph explorer' },
    { name: 'Maintenance Brain', path: '/maintenance', icon: Wrench, desc: 'CMMS loop, Work Orders & anomalies' },
    { name: 'Compliance Brain', path: '/compliance', icon: ShieldAlert, desc: 'OSHA/EPA compliance & safety validation' },
    { name: 'RCA Brain', path: '/rca', icon: GitFork, desc: '5-Whys, Fishbone diagrams & fault trees' },
    { name: 'Lessons Learned', path: '/lessons-learned', icon: Lightbulb, desc: 'Knowledge logs & operational feedback' },
  ];

  return (
    <div className="min-h-screen flex bg-slate-950 text-slate-100 font-sans selection:bg-indigo-500/30">
      {/* BACKGROUND DECORATIONS (Glassmorphism blobs) */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-900/10 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full bg-violet-900/10 blur-[120px] pointer-events-none" />

      {/* MOBILE BACKDROP */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-20 md:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* SIDEBAR — static on md+, slide-over drawer on mobile */}
      <aside
        className={`w-80 border-r border-slate-900 bg-slate-950/95 md:bg-slate-950/80 backdrop-blur-md flex flex-col z-30 fixed inset-y-0 left-0 transform transition-transform duration-200 md:static md:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}>
        {/* Header Logo */}
        <div className="h-16 px-6 border-b border-slate-900 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-500 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <Layers className="w-4 h-4 text-white animate-pulse" />
            </div>
            <div>
              <span className="font-semibold text-sm tracking-wide bg-gradient-to-r from-indigo-200 to-slate-200 bg-clip-text text-transparent">
                INDUSTRIAL BRAIN
              </span>
              <span className="text-[10px] text-indigo-400 font-mono block leading-none">OS v0.1.0</span>
            </div>
          </div>
          {/* Status Indicator Dot */}
          <div className="flex items-center space-x-1.5 bg-slate-900/60 border border-slate-800 rounded-full px-2 py-0.5">
            <span className={`w-2 h-2 rounded-full ${
              systemHealth === 'healthy' ? 'bg-emerald-500 shadow-emerald-500/50' : 
              systemHealth === 'degraded' ? 'bg-amber-500 shadow-amber-500/50' : 'bg-red-500 shadow-red-500/50'
            } animate-ping absolute w-2 h-2`} />
            <span className={`w-2 h-2 rounded-full z-10 ${
              systemHealth === 'healthy' ? 'bg-emerald-500' : 
              systemHealth === 'degraded' ? 'bg-amber-500' : 'bg-red-500'
            }`} />
            <span className="text-[9px] font-mono text-slate-400 capitalize">{systemHealth}</span>
          </div>
        </div>

        {/* Navigation Menu */}
        <nav className="flex-1 px-4 py-6 space-y-1.5 overflow-y-auto">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold px-2 mb-2">
            Sub-Brain Modules
          </div>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={() => setSidebarOpen(false)}
                className={({ isActive }) =>
                  `flex items-start space-x-3 px-3.5 py-3 rounded-xl transition-all duration-200 group border ${
                    isActive
                      ? 'bg-gradient-to-r from-indigo-950/40 to-slate-900/40 border-indigo-500/30 text-indigo-200 shadow-md shadow-indigo-950/20'
                      : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/40 hover:border-slate-800/40'
                  }`
                }
              >
                <div className="mt-0.5 p-1 rounded-lg bg-slate-900 border border-slate-800 group-hover:border-slate-700 transition-colors">
                  <Icon className="w-4 h-4 text-indigo-400 group-hover:scale-110 transition-transform" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium leading-none mb-1 flex items-center justify-between">
                    <span>{item.name}</span>
                    <ChevronRight className="w-3 h-3 text-slate-600 opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all" />
                  </div>
                  <p className="text-[10px] text-slate-500 line-clamp-1 group-hover:text-slate-400 transition-colors">{item.desc}</p>
                </div>
              </NavLink>
            );
          })}
        </nav>

        {/* Database Status Monitor Panel */}
        <div className="p-4 border-t border-slate-900 bg-slate-950/40">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2 flex items-center justify-between">
            <span>Data Infrastructure</span>
            <Activity className="w-3 h-3 text-slate-600" />
          </div>
          <div className="space-y-1.5 text-[11px] font-mono">
            {Object.entries(dbStatus).map(([db, status]) => (
              <div key={db} className="flex items-center justify-between px-2.5 py-1 rounded bg-slate-900/40 border border-slate-900/60">
                <span className="text-slate-400 capitalize">{db}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded leading-none ${
                  status === 'healthy' 
                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
                    : status === 'checking'
                    ? 'bg-slate-800 text-slate-400 border border-slate-700'
                    : 'bg-red-500/10 text-red-400 border border-red-500/20'
                }`}>
                  {status}
                </span>
              </div>
            ))}
          </div>
        </div>
      </aside>

      {/* MAIN CONTAINER */}
      <div className="flex-1 flex flex-col min-w-0 z-10">
        {/* HEADER */}
        <header className="h-16 border-b border-slate-900 px-4 md:px-8 flex items-center justify-between bg-slate-950/40 backdrop-blur-md">
          {/* Header Title */}
          <div className="flex items-center space-x-3">
            <button
              onClick={() => setSidebarOpen((o) => !o)}
              className="md:hidden p-2 rounded-lg border border-slate-900 bg-slate-950/60 text-slate-300 hover:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-400"
              aria-label={sidebarOpen ? 'Close navigation menu' : 'Open navigation menu'}
              aria-expanded={sidebarOpen}
            >
              {sidebarOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
            </button>
            <span className="text-slate-500 font-medium text-xs hidden sm:inline">Environment:</span>
            <span className="px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-mono text-[10px]">
              DEVELOPMENT
            </span>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center space-x-4">
            {/* Theme Toggle */}
            <button
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              className="p-2 rounded-xl border border-slate-900 bg-slate-950/60 hover:bg-slate-900 hover:border-slate-800 transition-all text-slate-400 hover:text-slate-200"
              title="Toggle theme"
            >
              {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
            
            {/* Terminal indicator */}
            <div className="hidden sm:flex items-center space-x-2 px-3 py-1.5 rounded-xl border border-slate-900 bg-slate-950/60 text-slate-400 text-xs">
              <Terminal className="w-3.5 h-3.5 text-indigo-400" />
              <span className="font-mono text-[10px]">d:\industrial-brain</span>
            </div>
          </div>
        </header>

        {/* WORKSPACE CONTENT */}
        <main className="flex-1 p-4 md:p-8 overflow-y-auto bg-slate-950/20">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
