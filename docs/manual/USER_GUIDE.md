# End-User Manual

A guide to using the Industrial Brain OS web console — no engineering
background required.

---

## 1. Signing In

Open the console in your browser (ask your administrator for the URL —
locally this is `http://localhost:3000`). You'll land on the **home page**,
which introduces the platform. Click **Launch Console** or **Sign in** to go
to the login screen.

Enter your email and password and click **Sign in**. If your credentials are
rejected, double-check them, or contact your administrator — there is
currently no self-service "forgot password" flow (see
[`ADMIN_GUIDE.md`](ADMIN_GUIDE.md) if you *are* the administrator).

### Creating an account

If you don't have an account yet, click **Sign up** on the sign-in page (or
go directly to the console's `/signup` route). Enter your name, a valid
email, and a password (at least 8 characters), then click **Sign up** — you
are signed in immediately, no email confirmation required. If the email is
already registered, sign in instead.

---

## 2. The Console Layout

Once signed in, you'll see:

- **Left sidebar** — navigation, grouped into **Workspace** (Document Hub,
  Knowledge Copilot, Knowledge Graph) and **Intelligence Brains**
  (Maintenance, Compliance, Root Cause, Lessons Learned). On phones/tablets,
  tap the ☰ menu icon top-left to open this as a slide-over panel.
- **Top bar** — a live system-health indicator, a light/dark/system theme
  toggle, and your account icon.
- **Main area** — whatever page you're on.

---

## 3. Document Hub

This is where source documents (manuals, SOPs, P&IDs, inspection reports,
regulations, maintenance logs) live.

### Uploading a document

1. Go to **Document Hub → Upload**.
2. Drag a file onto the drop zone, or click **Browse files**.
3. Accepted types: PDF, DOCX, DOC, XLSX, XLS, PNG, JPEG — up to 100 MB.
4. Click **Upload**. You'll see a progress bar, then a confirmation once it's
   queued.

Behind the scenes, the document is parsed, split into searchable chunks,
embedded for semantic search, and its equipment/procedure mentions are added
to the Knowledge Graph. This runs in the background — it does not block you.

### Tracking processing status

Switch to **Document Hub → Library**. Each row shows a status badge:

| Status | Meaning |
|---|---|
| `UPLOADED` / `VALIDATED` | Received, not yet processing |
| `READY_FOR_PROCESSING` / `QUEUED` | Waiting for a worker |
| `PROCESSING` | Actively being parsed/indexed |
| `PROCESSED` / `COMPLETED` | Done — searchable and chat-ready |
| `FAILED` | Something went wrong — a retry (↻) icon appears; click it to try again |

The list refreshes automatically while anything is in progress.

### Viewing a document

Click the eye icon on any row to open its detail page: metadata, version
history, and — for PDFs — an inline page-by-page preview with citation
highlights (gold = matched by search, blue = matched via the Knowledge
Graph) when you arrive here from a cited chat answer.

### Searching, filtering, downloading, deleting

Use the search box to filter by filename, the status dropdown to filter by
processing state, the download icon to retrieve the original file, and the
trash icon to soft-delete a document (recoverable — see its detail page).

---

## 4. Knowledge Copilot (Chat)

Go to **Knowledge Copilot** in the sidebar. This is a conversational
assistant that answers questions **only from your uploaded document
library** — it will tell you plainly if it doesn't have the information
rather than guessing.

1. Type a question (e.g. *"What is the rated discharge pressure of pump
   P-102A?"*) or click one of the suggested starter questions.
2. Press **Enter** to send (Shift+Enter for a new line without sending).
3. The answer streams in token by token. When it finishes, look for a
   **N sources** panel below the answer — click it to expand the exact
   passages the answer was grounded in, with a relevance percentage for each.
4. Click **View document →** under any source to jump to that document,
   highlighted at the cited page.

Use the ↻ icon in the chat header to start a fresh conversation.

---

## 5. Knowledge Graph

Go to **Knowledge Graph** to visually explore how your equipment, sensors,
failure modes, procedures, and documents relate to each other.

1. Type an equipment/asset tag (e.g. `P-102A`) into the search box.
2. Choose a **Depth** (1–3) — how many relationship "hops" out from that tag
   to show. Start with 1; increase if you want a wider view.
3. Click **Explore**.
4. The graph renders as colored nodes connected by labeled relationship
   lines. Colors follow a consistent legend shown above the graph
   (Asset = blue, Equipment = green, Sensor = yellow, FailureMode = red, and
   so on).
5. **Click any node** to see its details and every relationship it has in
   the current view, listed in the panel on the right.

This is read-only exploration — it doesn't modify any data.

---

## 6. The Intelligence Brains

Each brain in the sidebar (Maintenance, Compliance, Root Cause, Lessons
Learned) is a specialist assistant:

- **Maintenance Brain** — ask about work orders, failure history, and
  equipment procedures for a specific asset.
- **Compliance Brain** — ask it to check a procedure against a regulation;
  it identifies gaps and generates reviewer-ready evidence, citing sources.
- **Root Cause (RCA) Brain** — walks you through a structured 5-Whys
  investigation for an incident, and can generate a Fishbone/Ishikawa-style
  cause breakdown.
- **Lessons Learned Brain** — surfaces relevant past incidents and their
  takeaways so you don't repeat a known mistake.

Each brain's page shows its live connection status and a summary of its
capabilities. Interaction patterns mirror the Knowledge Copilot: ask a
question in plain language, get a cited, grounded answer.

---

## 7. Settings

Go to **Settings** to:

- **Appearance** — switch between Light, Dark, or System (follows your OS
  setting) theme.
- **Account** — see your workspace identity and account status.

---

## 8. Tips

- Answers are only as good as what's been uploaded and finished processing —
  if the copilot says it doesn't have information on a topic, check whether
  the relevant document has finished processing in the Document Hub.
- Every cited answer traces back to a real document and page — if something
  looks off, click through to the source and verify.
- The system respects role-based access scoping for documents (ask your
  administrator if you believe you're missing access you should have).
