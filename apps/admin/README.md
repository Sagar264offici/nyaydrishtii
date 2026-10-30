# NyayDrishti Admin Dashboard

React + Vite + TypeScript case-review dashboard. Synthetic demo data only —
see the banner in the app and `backend/database.py` for the seed set.

## Run it

The dashboard reads from the FastAPI backend, so start that first.

```bash
# Terminal 1 — backend (from repo root)
cd ../../backend
source venv/bin/activate   # create it first if needed: python3.12 -m venv venv && pip install -r requirements.txt
uvicorn main:app --port 8000

# Terminal 2 — admin dashboard (from repo root)
cd apps/admin
npm install
npm run dev
```

Open the URL Vite prints (default `http://localhost:5173`). The dashboard
expects the backend at `http://localhost:8000` by default; override with a
`VITE_API_BASE_URL` env var (e.g. in `apps/admin/.env.local`) if the backend
runs elsewhere.

## Verify

```bash
npx tsc --noEmit   # typecheck
npm run build      # production build (tsc -b && vite build)
npm run lint       # oxlint
```

## What's here

- `src/api.ts` — typed fetch client for `GET /api/cases`, `GET /api/cases/{id}`,
  `GET /api/metrics`, `POST /api/documents/preview`, `GET /api/cases/{id}/facts`,
  `PATCH /api/cases/{id}/facts/{fact_id}`, `POST /api/cases/{id}/evaluations`,
  `GET /api/cases/{id}/evaluations`, `GET /api/cases/{id}/review-pack`,
  `POST /api/followups`, `GET /api/followups`, `GET /api/cases/{id}/followups`,
  `PATCH /api/followups/{id}`, `GET /api/cases/{id}/audit-log`,
  `PATCH /api/cases/{id}` (review-status only).
- `src/App.tsx` — the dashboard: demo-data banner, metrics summary (now
  including real follow-up status counts), a top-level **Cases / Follow-ups**
  tab toggle, a searchable/filterable case table, and a case-details view (no
  router — plain component state toggles between views). The "Cases" tab
  behaves exactly as before; "Follow-ups" is new (see below).

  The case-details view includes:
  - A compact review-status control next to the status badge: pick a new
    status, enter a reviewer name, Save. Requires a non-empty reviewer name;
    updates the badge immediately on success.
  - A "Download Counsel Review Pack" button that fetches the generated PDF
    as a blob and saves it as `NyayDrishti-ReviewPack-{case_id}.pdf`, with
    its own loading/error state. It only downloads whatever is already on
    record — it never triggers a new evaluation.
  - A PDF upload box and the resulting extracted facts (custody dates,
    charges, max punishment + source + years, death/life-punishment flag,
    other pending cases, exception flags, accused-caused delay days), each
    showing its source filename/page, extraction method, and a status badge
    (unknown / unverified / verified / conflict) with inline edit and
    verify/flag controls.
  - A "Section 479 BNSS Evaluation" panel: a reviewer-name field and a "Run
    Evaluation" button (a reviewer must explicitly trigger each run), and
    the case's full evaluation history — outcome badge, explanation,
    blockers/escalation reasons, the calculation, and an expandable rule
    trace + statutory text. Re-running never overwrites a past evaluation.
  - A **Follow-up Tasks** section scoped to this case: create form, and all
    of its follow-ups grouped into Overdue / Upcoming / Completed, each with
    inline edit and Start/Complete/Cancel actions (Complete/Cancel require a
    reviewer name; Start doesn't).
  - An **Audit History** table: the case's most recent events (timestamp,
    event type, actor, description, with changed before/after values
    available in a collapsed `<details>`), read-only.

  The new top-level **Follow-ups** view lists every follow-up across all
  cases, with the same Overdue / Upcoming / Completed grouping, a status
  filter (server-side) and a reviewer filter (client-side), a create form
  (case ID entered as plain text — there's no case picker), and the same
  row-level edit/action controls as the case-scoped section.

No AI-based extraction (PyMuPDF text + optional local Tesseract OCR + a
hand-written keyword/regex heuristic only, fully offline). The Section 479
evaluation is a deterministic, auditable rule engine (`backend/rules.py`,
documented in the root README) — no ML/LLM involved, and it never outputs a
bail/release decision, only an internal review-status flag. The Counsel
Review Pack PDF (`backend/review_pack.py`, reportlab) is rendered locally
and only ever formats what's already on record — it never fabricates a
value and never runs a new evaluation. Extracted facts are candidates for
a human reviewer, never auto-verified. This app has no login — every
reviewer-name field (fact verification, evaluations, follow-up assignment/
completion, case-status changes) is a free-text label, never an
authenticated identity.
