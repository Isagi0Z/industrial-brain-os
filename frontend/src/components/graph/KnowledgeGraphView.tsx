import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import cytoscape, { Core, ElementDefinition, NodeSingular } from 'cytoscape';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Network,
  Search,
  Info,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Shuffle,
  MousePointerClick,
  Share2,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';

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

// Seeded demo entities — one-click exploration starters.
const SUGGESTED_TAGS = ['P-102A', 'M-330', 'VLV-501', 'FT-101', 'TE-202'];

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
  const [depth, setDepth] = useState(2);
  const [pending, setPending] = useState('P-102A');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState<SubgraphResponse | null>(null);
  const [selected, setSelected] = useState<SelectedNode | null>(null);
  // Bumped to force a refetch even when the tag is unchanged (e.g. retrying
  // the same entity after a transient backend error).
  const [refetchNonce, setRefetchNonce] = useState(0);

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
        setError(`No subgraph found for "${entityTag}".`);
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
    // refetchNonce forces a re-run for same-tag retries.
  }, [fetchSubgraph, refetchNonce]);

  // Explore a node in-place (double-click navigation / suggestion chips).
  const exploreNode = useCallback((id: string) => {
    setPending(id);
    setEntityTag(id);
    setRefetchNonce((n) => n + 1);
  }, []);

  // (Re)render the Cytoscape graph whenever the data changes.
  useEffect(() => {
    if (!containerRef.current || !data) return;
    const elements: ElementDefinition[] = [
      ...data.nodes.map((n) => ({
        data: n.data,
        classes: n.data.seed ? 'seed' : undefined,
      })),
      ...data.edges.map((e) => ({ data: e.data })),
    ];

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      // Extended visual properties (underlay glow, transitions) are valid at
      // runtime but missing from cytoscape's TS stylesheet types.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      style: [
        {
          selector: 'node',
          style: {
            'background-color': (ele: NodeSingular) => colorFor(ele.data('type')),
            label: 'data(label)',
            color: '#e2e8f0',
            'font-size': '10px',
            'font-weight': 600,
            'text-valign': 'bottom',
            'text-margin-y': 6,
            'text-background-color': '#05050c',
            'text-background-opacity': 0.65,
            'text-background-padding': '2px',
            'text-background-shape': 'roundrectangle',
            width: (ele: NodeSingular) => 22 + Math.min(ele.degree(false), 8) * 3,
            height: (ele: NodeSingular) => 22 + Math.min(ele.degree(false), 8) * 3,
            'border-width': 2,
            'border-color': 'rgba(255,255,255,0.25)',
            // Soft neon halo around every node, tinted by its ontology colour.
            'underlay-color': (ele: NodeSingular) => colorFor(ele.data('type')),
            'underlay-opacity': 0.22,
            'underlay-padding': 8,
            'transition-property': 'underlay-opacity, underlay-padding, opacity, border-color',
            'transition-duration': 180,
          },
        },
        {
          selector: 'node.seed',
          style: {
            width: 54,
            height: 54,
            'font-size': '12px',
            'border-width': 3,
            'border-color': '#f8fafc',
            'underlay-opacity': 0.4,
            'underlay-padding': 14,
            'z-index': 10,
          },
        },
        {
          selector: 'edge',
          style: {
            width: 1.6,
            'line-color': 'rgba(251,146,60,0.35)',
            'target-arrow-color': 'rgba(251,146,60,0.55)',
            'target-arrow-shape': 'triangle',
            'arrow-scale': 0.8,
            'curve-style': 'bezier',
            label: 'data(label)',
            'font-size': '8px',
            color: '#fed7aa',
            'text-rotation': 'autorotate',
            'text-opacity': 0, // labels appear on hover/selection only
            'transition-property': 'line-color, text-opacity, opacity, width',
            'transition-duration': 180,
          },
        },
        // Hover spotlight: everything outside the hovered neighbourhood fades.
        { selector: '.faded', style: { opacity: 0.12 } },
        {
          selector: 'node.spot',
          style: { 'underlay-opacity': 0.5, 'underlay-padding': 12 },
        },
        {
          selector: 'edge.spot',
          style: {
            'line-color': 'rgba(253,186,116,0.95)',
            'target-arrow-color': '#fdba74',
            width: 2.4,
            'text-opacity': 1,
          },
        },
        {
          selector: 'node:selected',
          style: {
            'border-color': '#fdba74',
            'border-width': 4,
            'underlay-opacity': 0.55,
            'underlay-padding': 16,
          },
        },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ] as any,
      layout: {
        name: 'cose',
        animate: true,
        animationDuration: 900,
        animationEasing: 'ease-out',
        padding: 40,
        nodeRepulsion: () => 8000,
        idealEdgeLength: () => 90,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      } as any,
      minZoom: 0.2,
      maxZoom: 3,
      wheelSensitivity: 0.25,
    });

    // Hover: spotlight the node + its neighbourhood, show its edge labels.
    cy.on('mouseover', 'node', (evt) => {
      const node = evt.target as NodeSingular;
      const hood = node.closedNeighborhood();
      cy.elements().not(hood).addClass('faded');
      hood.addClass('spot');
    });
    cy.on('mouseout', 'node', () => {
      cy.elements().removeClass('faded').removeClass('spot');
    });

    // Click: inspect in the side panel.
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

    // Double-click: re-centre the exploration on that node.
    cy.on('dbltap', 'node', (evt) => {
      exploreNode((evt.target as NodeSingular).id());
    });

    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [data, exploreNode]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setEntityTag(pending.trim());
    setRefetchNonce((n) => n + 1);
  };

  const zoomBy = (factor: number) => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.animate(
      { zoom: cy.zoom() * factor, center: { eles: cy.elements() } },
      { duration: 220, easing: 'ease-out' }
    );
  };
  const fit = () => cyRef.current?.animate({ fit: { eles: cyRef.current.elements(), padding: 40 } }, { duration: 350, easing: 'ease-in-out' });
  const relayout = () =>
    cyRef.current
      ?.layout({
        name: 'cose',
        animate: true,
        animationDuration: 900,
        padding: 40,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      } as any)
      .run();

  // Legend derived from the types actually present in the current subgraph.
  const presentTypes = useMemo(() => {
    if (!data) return [];
    return Array.from(new Set(data.nodes.map((n) => n.data.type))).sort();
  }, [data]);

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 ring-1 ring-primary/20">
            <Network className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Knowledge Graph</h1>
            <p className="text-sm text-muted-foreground">
              Live ontology around any asset — hover to spotlight, double-click to travel.
            </p>
          </div>
        </div>
        {data && (
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="gap-1.5 font-mono">
              <Share2 className="h-3 w-3 text-primary" />
              {data.stats.node_count} nodes
            </Badge>
            <Badge variant="outline" className="font-mono">
              {data.stats.edge_count} edges
            </Badge>
          </div>
        )}
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
        <div className="flex items-center gap-1 rounded-lg border border-input bg-background/60 p-1" role="group" aria-label="Traversal depth">
          {[1, 2, 3].map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDepth(d)}
              className={
                depth === d
                  ? 'rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground shadow-glow'
                  : 'rounded-md px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground'
              }
            >
              Depth {d}
            </button>
          ))}
        </div>
        <Button type="submit" variant="gradient">
          Explore
        </Button>
      </form>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Graph canvas — animated aurora + grid atmosphere */}
        <div className="kg-aurora relative overflow-hidden rounded-2xl border border-border bg-[#05050c] lg:col-span-2">
          <div
            className="pointer-events-none absolute inset-0 opacity-40"
            style={{
              backgroundImage: 'radial-gradient(rgba(148,163,184,0.18) 1px, transparent 1px)',
              backgroundSize: '26px 26px',
            }}
          />

          {/* Legend (auto from present types) */}
          <div className="absolute left-3 top-3 z-10 flex max-w-[70%] flex-wrap gap-1.5">
            {presentTypes.map((t) => (
              <span
                key={t}
                className="flex items-center gap-1.5 rounded-full border border-white/10 bg-black/50 px-2 py-0.5 text-[10px] text-slate-300 backdrop-blur"
              >
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: colorFor(t), boxShadow: `0 0 6px ${colorFor(t)}` }}
                />
                {t}
              </span>
            ))}
          </div>

          {/* Canvas toolbar */}
          <div className="absolute right-3 top-3 z-10 flex flex-col gap-1.5">
            {[
              { icon: ZoomIn, action: () => zoomBy(1.3), label: 'Zoom in' },
              { icon: ZoomOut, action: () => zoomBy(0.75), label: 'Zoom out' },
              { icon: Maximize2, action: fit, label: 'Fit graph' },
              { icon: Shuffle, action: relayout, label: 'Re-run layout' },
            ].map(({ icon: Icon, action, label }) => (
              <button
                key={label}
                type="button"
                onClick={action}
                title={label}
                aria-label={label}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-black/50 text-slate-300 backdrop-blur transition-all hover:border-primary/50 hover:text-primary hover:shadow-glow"
              >
                <Icon className="h-4 w-4" />
              </button>
            ))}
          </div>

          {/* Interaction hint */}
          <div className="pointer-events-none absolute bottom-3 left-3 z-10 flex items-center gap-1.5 rounded-full border border-white/10 bg-black/50 px-2.5 py-1 text-[10px] text-slate-400 backdrop-blur">
            <MousePointerClick className="h-3 w-3" />
            hover: spotlight · click: inspect · double-click: travel
          </div>

          <div ref={containerRef} className="relative z-[5] h-[540px] w-full" data-testid="kg-canvas" />

          <AnimatePresence>
            {loading && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-4 bg-black/60 backdrop-blur-sm"
              >
                <div className="kg-radar" />
                <p className="text-xs tracking-widest text-slate-400">TRAVERSING GRAPH…</p>
              </motion.div>
            )}
          </AnimatePresence>

          {error && !loading && (
            <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-4 p-6 text-center">
              <p className="text-sm text-amber-400">{error}</p>
              <div className="flex flex-wrap justify-center gap-2">
                {SUGGESTED_TAGS.map((t) => (
                  <button
                    key={t}
                    onClick={() => exploreNode(t)}
                    className="rounded-full border border-primary/40 bg-primary/10 px-3 py-1 font-mono text-xs text-primary transition-all hover:bg-primary/20 hover:shadow-glow"
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Details panel */}
        <div className="rounded-2xl border border-border bg-card p-5">
          <h2 className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            <Info className="h-4 w-4 text-primary" />
            Entity Details
          </h2>
          <AnimatePresence mode="wait">
            {selected ? (
              <motion.div
                key={selected.id}
                initial={{ opacity: 0, x: 14 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -10 }}
                transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                className="space-y-4"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span
                      className="h-3 w-3 rounded-full"
                      style={{
                        backgroundColor: colorFor(selected.type),
                        boxShadow: `0 0 10px ${colorFor(selected.type)}`,
                      }}
                    />
                    <span className="font-mono text-foreground">{selected.id}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">{selected.type}</span>
                    <button
                      onClick={() => exploreNode(selected.id)}
                      className="text-xs text-primary underline-offset-2 hover:underline"
                    >
                      explore from here →
                    </button>
                  </div>
                </div>
                <div>
                  <div className="mb-2 text-[11px] uppercase tracking-wider text-muted-foreground">
                    Relationships ({selected.relations.length})
                  </div>
                  <ul className="space-y-1.5">
                    {selected.relations.map((r, i) => (
                      <motion.li
                        key={`${r.label}-${r.other}-${i}`}
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.04 }}
                        className="rounded-lg border border-border bg-secondary/40 px-2.5 py-1.5 text-xs text-foreground/90"
                      >
                        <span className="font-mono text-primary">{r.label}</span>{' '}
                        <span className="text-muted-foreground">
                          {r.direction === 'out' ? '→' : '←'}
                        </span>{' '}
                        <button
                          onClick={() => exploreNode(r.other)}
                          className="font-mono underline-offset-2 hover:text-primary hover:underline"
                          title={`Explore ${r.other}`}
                        >
                          {r.other}
                        </button>
                      </motion.li>
                    ))}
                    {selected.relations.length === 0 && (
                      <li className="text-xs text-muted-foreground">
                        No direct relationships in view.
                      </li>
                    )}
                  </ul>
                </div>
              </motion.div>
            ) : (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="space-y-4"
              >
                <p className="text-sm text-muted-foreground">
                  {data
                    ? `${data.stats.node_count} nodes and ${data.stats.edge_count} edges around `
                    : 'Pick a starting entity to explore its neighbourhood: '}
                  {data && <span className="font-mono text-primary">{data.seed}</span>}
                  {data && '. Click any node to inspect it.'}
                </p>
                <div className="flex flex-wrap gap-2">
                  {SUGGESTED_TAGS.map((t) => (
                    <button
                      key={t}
                      onClick={() => exploreNode(t)}
                      className="rounded-full border border-border bg-secondary/40 px-3 py-1 font-mono text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary"
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
};
