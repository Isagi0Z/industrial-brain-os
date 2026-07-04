# Coverage

## Requested-capability matrix

Legend: ✅ exercised · ⚠️ partial / environment-limited · ❌ not testable in current build.

| Capability | Status | Evidence |
|-----------|:------:|----------|
| Launch Chrome + start/health-gate services | ✅ | globalSetup gates backend health; Playwright webServer starts the frontend |
| Authentication (login) | ✅ | UI login happy-path + bad-credential rejection |
| Authorization (route guard) | ✅ | Anonymous deep-link bounced to /login; session-end re-guards |
| Signup | ✅ | Duplicate-email 409 + min-length validation |
| Navigate every page | ✅ | All 7 sidebar routes + Settings |
| Upload documents | ✅ | Real multipart upload of an industrial PDF via the browser |
| Wait for ingestion | ⚠️ | Bounded poll for PROCESSED (worker-dependent — see warnings) |
| Search | ✅ | Document library search + empty state |
| Chat with copilot | ✅ | WebSocket connect + streamed answer observed on the wire |
| Citations | ✅ | Citation UI validated when present; grounding gap noted otherwise |
| Knowledge graph | ✅ | Seeded P-102A subgraph render + depth + error state |
| Dark mode | ✅ | Toggle applies to <html> and persists across reload |
| Error handling | ✅ | 404 route + aborted-API graceful degradation |
| Empty states | ✅ | Document library empty state on no match |
| Loading states | ⚠️ | Skeleton/loader present; not separately asserted |
| Browser console errors | ✅ | Console/pageerror observed on every test (auto fixture) |
| Network failures | ✅ | Route-abort resilience test |
| Performance | ✅ | 12 timing metric(s) captured |
| Accessibility | ✅ | axe-core scan of core pages |
| Responsiveness | ✅ | Mobile off-canvas sidebar + tablet overflow check |
| Multiple browser tabs | ✅ | Parallel copilot + graph tabs |
| Human-like behaviour | ✅ | Mouse arcs, variable-cadence typing, scrolling, think-time (utils/human) |
| Screenshots / videos / traces | ✅ | trace/video/screenshot = "on" in config; curated stills in screenshots/ |
| Work orders / compliance / RCA / maintenance / lessons workflows | ⚠️ | Brains are status scaffolds only — no interactive workflow UI exists yet (see suggestions) |

## All exercised checks (47)

- 404 / NotFound route
- Accessibility scan of core pages
- Brain panel online: Compliance
- Brain panel online: Lessons Learned
- Brain panel online: Maintenance
- Brain panel online: Root Cause
- Brains capability-gap documented
- Chat "New conversation" resets to the empty state
- Chat WebSocket connects (authenticated)
- Chat answer carried citations on the wire
- Chat completed a streamed answer
- Chat send disabled while composer is empty
- Chat sends a query and renders both turns
- Chat suggestion populates composer
- Dark mode applies to <html>
- Document delete (with confirm dialog)
- Document details view
- Document library: search + status filter + empty state
- Document upload (multipart, through UI)
- Graceful API / network-failure handling
- Infra health widget (5 datastores)
- KG depth control expands traversal
- KG handles unknown tag gracefully
- KG node selection → entity details panel
- KG renders seeded subgraph
- Landing page + CTAs
- Login happy-path (UI)
- Login rejects bad credentials
- Multi-tab parallel authenticated sessions
- Navigate: Compliance
- Navigate: Document Hub
- Navigate: Knowledge Copilot
- Navigate: Knowledge Graph
- Navigate: Lessons Learned
- Navigate: Maintenance
- Navigate: Root Cause
- Navigate: Settings
- Responsive: mobile off-canvas sidebar
- Responsive: tablet layout
- Route guard (RequireAuth)
- Session-end re-guards protected routes
- Settings page renders all cards
- Signup duplicate-email handling
- Signup password min-length validation
- Theme persists across reload
- Theme switch via Settings controls
- Uploaded document appears in library
