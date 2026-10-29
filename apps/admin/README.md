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
  `GET /api/metrics`.
- `src/App.tsx` — the dashboard: demo-data banner, metrics summary, searchable
  /filterable case table, and a case-details view (no router — plain
  component state toggles between table and details).

No AI extraction or legal-eligibility logic yet — this phase only displays
case facts and review status.
