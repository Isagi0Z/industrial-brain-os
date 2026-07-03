import React, { useCallback, useEffect, useRef, useState } from 'react';
import cytoscape, { Core, ElementDefinition, NodeSingular } from 'cytoscape';
import { Network, Search, Loader2, Info } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

// Ontology type -> colour (checklist: Asset=blue, Equipment=green,
// Sensor=yellow, FailureMode=red; the rest extend the same palette).
const TYPE_COLORS: Record<string, string> = {
  Asset: '#3b82f6',
  Equipment: '#22c55e',
  Sensor: '#eab308',
  FailureMode: '#ef4444',
  Procedure: '#a855f7',
  Document: '#64748b',
  Regulation: '#f97316',
  Maintenance: '#14b8a6',
  Inspection: '#06b6d4',
  Personnel: '#ec4899',
  Process: '#8b5cf6',
  LessonLearned: '#f59e0b',
  Unknown: '#94a3b8',
};

const colorFor = (type: string): string => TYPE_COLORS[type] ?? TYPE_COLORS.Unknown;

interface SubgraphNode {
  data: { id: string; label: string; type: string; seed: boolean };
}
interface SubgraphEdge {
  data: { id: string; source: string; target: string; label: string };
}
interface SubgraphResponse {
  seed: string;
  depth: number;
  nodes: SubgraphNode[];
  edges: SubgraphEdge[];
  stats: { node_count: number; edge_count: number };
}

interface SelectedNode {
  id: string;
  type: string;
  relations: { label: string; other: string; direction: 'out' | 'in' }[];
}

export const KnowledgeGraphView: React.FC = () => {
  const { token } = useAuth();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);

  const [entityTag, setEntityTag] = useState('P-102A');
  const [depth, setDepth] = useState(1);
  const [pending, setPending] = useState('P-102A');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState<SubgraphResponse | null>(null);
  const [selected, setSelected] = useState<SelectedNode | null>(null);

  const fetchSubgraph = useCallback(async () => {
    if (!entityTag.trim()) return;
    setLoading(true);
    setError('');
    setSelected(null);
    try {
      const res = await fetch(
        `/api/v1/graph/subgraph?entity_tag=${encodeURIComponent(entityTag)}&depth=${depth}`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
      );
      if (!res.ok) {
        setError(`No subgraph found for "${entityTag}" (status ${res.status}).`);
        setData(null);
        return;
      }
      setData((await res.json()) as SubgraphResponse);
    } catch {
      setError('Failed to reach the knowledge graph service.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [entityTag, depth, token]);

  useEffect(() => {
    fetchSubgraph();
  }, [fetchSubgraph]);

  // (Re)render the Cytoscape graph whenever the data changes.
  useEffect(() => {
    if (!containerRef.current || !data) return;
    const elements: ElementDefinition[] = [
      ...data.nodes.map((n) => ({ data: n.data })),
      ...data.edges.map((e) => ({ data: e.data })),
    ];

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: 'node',
          style: {
            'background-color': (ele: NodeSingular) => colorFor(ele.data('type')),
            label: 'data(label)',
            color: '#e2e8f0',
            'font-size': '10px',
            'text-valign': 'bottom',
            'text-margin-y': 4,
            width: 26,
            height: 26,
            'border-width': 2,
            'border-color': '#0f172a',
          },
        },
        {
          selector: 'node[?seed]',
          style: { width: 40, height: 40, 'border-color': '#f8fafc', 'border-width': 3 },
        },
        {
          selector: 'edge',
          style: {
            width: 1.5,
            'line-color': '#475569',
            'target-arrow-color': '#475569',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            label: 'data(label)',
            'font-size': '8px',
            color: '#94a3b8',
            'text-rotation': 'autorotate',
          },
        },
        { selector: 'node:selected', style: { 'border-color': '#818cf8', 'border-width': 4 } },
      ],
      layout: { name: 'cose', animate: false, padding: 30 },
      minZoom: 0.2,
      maxZoom: 3,
    });

    cy.on('tap', 'node', (evt) => {
      const node = evt.target as NodeSingular;
      const id = node.id();
      const relations = node.connectedEdges().map((edge) => {
        const isOut = edge.source().id() === id;
        return {
          label: edge.data('label') as string,
          other: (isOut ? edge.target().id() : edge.source().id()) as string,
          direction: (isOut ? 'out' : 'in') as 'out' | 'in',
        };
      });
      setSelected({ id, type: node.data('type') as string, relations });
    });

    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [data]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setEntityTag(pending);
  };

  const legendTypes = ['Asset', 'Equipment', 'Sensor', 'FailureMode'];

  return (
    <div className="max-w-6xl space-y-4">
      <div className="flex items-center space-x-3">
        <div className="p-2.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20">
          <Network className="w-6 h-6 text-indigo-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-slate-100">Knowledge Graph</h1>
          <p className="text-slate-400 text-sm">
            Interactive subgraph around an equipment/asset tag (Neo4j, bounded traversal).
          </p>
        </div>
      </div>

      {/* Controls */}
      <form onSubmit={onSubmit} className="flex flex-wrap items-center gap-3">
        <label htmlFor="kg-tag" className="sr-only">
          Entity tag
        </label>
        <div className="flex items-center bg-slate-900/60 border border-slate-800 rounded-xl px-3 py-2 flex-1 min-w-[220px]">
          <Search className="w-4 h-4 text-slate-500 mr-2" aria-hidden="true" />
          <input
            id="kg-tag"
            value={pending}
            onChange={(e) => setPending(e.target.value)}
            placeholder="Entity tag e.g. P-102A"
            className="bg-transparent outline-none text-sm text-slate-200 flex-1 placeholder:text-slate-600"
          />
        </div>
        <label htmlFor="kg-depth" className="text-xs text-slate-400">
          Depth
        </label>
        <select
          id="kg-depth"
          value={depth}
          onChange={(e) => setDepth(Number(e.target.value))}
          className="bg-slate-900/60 border border-slate-800 rounded-xl px-3 py-2 text-sm text-slate-200"
        >
          <option value={1}>1</option>
          <option value={2}>2</option>
          <option value={3}>3</option>
        </select>
        <button
          type="submit"
          className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-400"
        >
          Explore
        </button>
      </form>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Graph canvas */}
        <div className="lg:col-span-2 rounded-2xl border border-slate-900 bg-slate-950/60 relative overflow-hidden">
          <div className="absolute top-3 left-3 z-10 flex flex-wrap gap-2">
            {legendTypes.map((t) => (
              <span
                key={t}
                className="flex items-center gap-1.5 text-[10px] text-slate-400 bg-slate-900/70 border border-slate-800 rounded-full px-2 py-0.5"
              >
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: colorFor(t) }}
                />
                {t}
              </span>
            ))}
          </div>
          <div ref={containerRef} className="w-full h-[520px]" data-testid="kg-canvas" />
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center bg-slate-950/60">
              <Loader2 className="w-6 h-6 text-indigo-400 animate-spin" />
            </div>
          )}
          {error && !loading && (
            <div className="absolute inset-0 flex items-center justify-center p-6 text-center">
              <p className="text-sm text-amber-400">{error}</p>
            </div>
          )}
        </div>

        {/* Details panel */}
        <div className="rounded-2xl border border-slate-900 bg-slate-950/60 p-5">
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-2 mb-4">
            <Info className="w-4 h-4 text-indigo-400" />
            Entity Details
          </h2>
          {selected ? (
            <div className="space-y-4">
              <div>
                <div className="flex items-center gap-2">
                  <span
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: colorFor(selected.type) }}
                  />
                  <span className="font-mono text-slate-100">{selected.id}</span>
                </div>
                <span className="text-xs text-slate-500">{selected.type}</span>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">
                  Relationships ({selected.relations.length})
                </div>
                <ul className="space-y-1.5">
                  {selected.relations.map((r, i) => (
                    <li
                      key={i}
                      className="text-xs text-slate-300 bg-slate-900/50 border border-slate-900 rounded-lg px-2.5 py-1.5"
                    >
                      <span className="text-indigo-400 font-mono">{r.label}</span>{' '}
                      <span className="text-slate-500">{r.direction === 'out' ? '→' : '←'}</span>{' '}
                      <span className="font-mono">{r.other}</span>
                    </li>
                  ))}
                  {selected.relations.length === 0 && (
                    <li className="text-xs text-slate-500">No direct relationships in view.</li>
                  )}
                </ul>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-500">
              {data
                ? `${data.stats.node_count} nodes, ${data.stats.edge_count} edges. Click a node to inspect it.`
                : 'Enter an entity tag to explore its neighbourhood.'}
            </p>
          )}
        </div>
      </div>
    </div>
  );
};
