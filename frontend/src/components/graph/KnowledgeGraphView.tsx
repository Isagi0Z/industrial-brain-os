import React, { useCallback, useEffect, useRef, useState } from 'react';
import cytoscape, { Core, ElementDefinition, NodeSingular } from 'cytoscape';
import { Network, Search, Loader2, Info } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../ui/button';

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
    <div className="mx-auto max-w-6xl space-y-5">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 ring-1 ring-primary/20">
          <Network className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Knowledge Graph</h1>
          <p className="text-sm text-muted-foreground">
            Interactive subgraph around an equipment/asset tag — Neo4j bounded traversal.
          </p>
        </div>
      </div>

      {/* Controls */}
      <form onSubmit={onSubmit} className="flex flex-wrap items-center gap-3">
        <label htmlFor="kg-tag" className="sr-only">
          Entity tag
        </label>
        <div className="flex min-w-[220px] flex-1 items-center rounded-lg border border-input bg-background/60 px-3 py-2 focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-ring">
          <Search className="mr-2 h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <input
            id="kg-tag"
            value={pending}
            onChange={(e) => setPending(e.target.value)}
            placeholder="Entity tag e.g. P-102A"
            className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
          />
        </div>
        <label htmlFor="kg-depth" className="text-xs text-muted-foreground">
          Depth
        </label>
        <select
          id="kg-depth"
          value={depth}
          onChange={(e) => setDepth(Number(e.target.value))}
          className="h-10 rounded-lg border border-input bg-background/60 px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value={1}>1</option>
          <option value={2}>2</option>
          <option value={3}>3</option>
        </select>
        <Button type="submit" variant="gradient">
          Explore
        </Button>
      </form>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Graph canvas — fixed dark viewport for label contrast in any theme */}
        <div className="relative overflow-hidden rounded-2xl border border-border bg-[#0a0a12] lg:col-span-2">
          <div className="absolute left-3 top-3 z-10 flex flex-wrap gap-2">
            {legendTypes.map((t) => (
              <span
                key={t}
                className="flex items-center gap-1.5 rounded-full border border-white/10 bg-black/40 px-2 py-0.5 text-[10px] text-slate-300 backdrop-blur"
              >
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: colorFor(t) }} />
                {t}
              </span>
            ))}
          </div>
          <div ref={containerRef} className="h-[520px] w-full" data-testid="kg-canvas" />
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/50">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
            </div>
          )}
          {error && !loading && (
            <div className="absolute inset-0 flex items-center justify-center p-6 text-center">
              <p className="text-sm text-amber-400">{error}</p>
            </div>
          )}
        </div>

        {/* Details panel */}
        <div className="rounded-2xl border border-border bg-card p-5">
          <h2 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            <Info className="h-4 w-4 text-primary" />
            Entity Details
          </h2>
          {selected ? (
            <div className="space-y-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="h-3 w-3 rounded-full" style={{ backgroundColor: colorFor(selected.type) }} />
                  <span className="font-mono text-foreground">{selected.id}</span>
                </div>
                <span className="text-xs text-muted-foreground">{selected.type}</span>
              </div>
              <div>
                <div className="mb-2 text-[11px] uppercase tracking-wider text-muted-foreground">
                  Relationships ({selected.relations.length})
                </div>
                <ul className="space-y-1.5">
                  {selected.relations.map((r, i) => (
                    <li
                      key={i}
                      className="rounded-lg border border-border bg-secondary/40 px-2.5 py-1.5 text-xs text-foreground/90"
                    >
                      <span className="font-mono text-primary">{r.label}</span>{' '}
                      <span className="text-muted-foreground">{r.direction === 'out' ? '→' : '←'}</span>{' '}
                      <span className="font-mono">{r.other}</span>
                    </li>
                  ))}
                  {selected.relations.length === 0 && (
                    <li className="text-xs text-muted-foreground">No direct relationships in view.</li>
                  )}
                </ul>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
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
