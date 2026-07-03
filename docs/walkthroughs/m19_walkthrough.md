# M19 — UI Polish, Knowledge Graph Visualizer & Demo Dataset

## What this milestone delivers

A judge-ready frontend: an interactive **Knowledge Graph visualizer** (Cytoscape)
backed by a new subgraph API, a **PDF document viewer** (react-pdf) with citation
bounding-box overlays, a **mobile-responsive** multi-brain shell, and a
**demo dataset** loader that seeds the knowledge graph and generates 10 industrial
PDFs. It also fixes a pre-existing gap where Tailwind was never actually compiled.

```
Knowledge Graph flow
────────────────────
KnowledgeGraphView (Cytoscape)
   └─ GET /api/v1/graph/subgraph?entity_tag=P-102A&depth=1
        └─ container.get_kg_traversal_service().traverse()  (M8/M17 APOC, bounded)
        └─ KGPath[] → Cytoscape { nodes[{id,label,type,seed}], edges[{source,target,label}] }
   ← nodes colour-coded by ontology type; click a node → details panel
```

## Backend — subgraph endpoint

`app/presentation/api/v1/endpoints/graph.py` → `GET /api/v1/graph/subgraph`:

- Params: `entity_tag` (seed), `depth` (1–3), `limit` (≤200) — bounds mirror the
  GraphRAG traversal guard (Engineering Bible §36, no unbounded scans).
- Reuses `Neo4jKGTraversalService.traverse()` — **no new Cypher**.
- Transforms `KGPath[]` into Cytoscape elements: nodes de-duplicated by tag, each
  carrying its ontology `type`; the seed node flagged `seed: true`; edges labelled
  with the relation type. Auth via `get_current_user`.
- Registered in `router.py`.

## Frontend

| Component | Purpose |
|-----------|---------|
| `components/graph/KnowledgeGraphView.tsx` | Cytoscape graph; nodes colour-coded by ontology type (Asset=blue, Equipment=green, Sensor=yellow, FailureMode=red, +others); tag/depth controls; click a node → details panel with its relationships; legend |
| `components/documents/DocumentViewer.tsx` | `react-pdf` page renderer with page nav; overlays citation bounding boxes scaled from PDF points — **gold = vector-matched, blue = KG-traversal** (checklist); typed `CitationHighlight[]` prop |
| `components/layout/DashboardLayout.tsx` | Multi-brain sidebar (Knowledge / Graph / Maintenance / Compliance / RCA / Lessons) made **mobile-responsive**: static on md+, slide-over drawer with hamburger + backdrop below md; a11y labels + focus rings |
| `router/routes.tsx` | new `/knowledge-graph` route |
| `components/documents/DocumentDetails.tsx` | embeds `DocumentViewer` as a PDF preview for PDF documents |

Node colours map every ontology type (`industrial_ontology.yaml`) to a distinct
hue; the seed node is enlarged and white-bordered.

## Tailwind fix (pre-existing gap, resolved here)

The frontend shipped **no `tailwind.config.js` / `postcss.config.js`**, so the
`@tailwind` directives in `index.css` were never expanded — every utility class
in the app was inert (production CSS was 1.4 kB). M19 adds both configs
(`content: ['./index.html','./src/**/*.{ts,tsx}']`, `darkMode: 'class'`). The
build's CSS grew to **35 kB** and the whole UI — including the responsive
breakpoints M19 relies on — now renders as authored. This is the "UI Polish"
foundation.

## Demo dataset — `scripts/load_demo_data.py` / `make demo-data`

- **`seed_graph()`** MERGEs a Refining-Unit-03 subgraph into Neo4j: 15 nodes
  (Asset / Equipment / Sensor / FailureMode / Procedure / Document / Regulation /
  Maintenance) and 15 relationships, matching `datasets/golden_qa.json` entities
  (P-102A, FT-101, TE-202, VLV-501, M-330, FM-BRG-01, …). Idempotent. This powers
  the KG visualizer out of the box.
- **`generate_pdfs()`** writes 10 industrial demo PDFs into `demo_data/` via
  PyMuPDF (already a dependency): 2 OEM manuals, 2 SOPs, 2 inspection reports,
  2 P&ID descriptions, 1 regulatory excerpt, 1 maintenance log.
- **`--upload`** pushes the PDFs through the ingestion API (M2→M3→M4→M7) when the
  backend + Celery worker are up (`DEMO_USER`/`DEMO_PASSWORD`).

## Dependencies added

`cytoscape` 3.34, `@types/cytoscape` (dev), `react-pdf` 10.4, `pdfjs-dist` 5.4.296
(pinned to react-pdf's bundled version so the Vite worker URL resolves under pnpm).

## Deviations (documented, not defects)

- **Brain URL scheme**: existing routes already encode the brain in the path
  (`/knowledge`, `/maintenance`, …); the KG view adds `/knowledge-graph`. The
  checklist's `/brain/<x>` prefix is a cosmetic difference — the brain is already
  URL-persisted.
- **Demo PDF indexing**: `make demo-data` seeds the graph and generates the PDFs;
  full vector/chunk indexing runs via `--upload` against a live backend + Celery
  worker (heavy), documented rather than run in this environment.
- **Citation bbox overlays** render from `bbox_json` ({x0,y0,x1,y1} PDF points)
  scaled to the rendered page; the overlay is exercised by the chat citation flow
  which supplies `CitationHighlight[]`.
