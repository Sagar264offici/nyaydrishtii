# NyayDrishti

Hackathon MVP for legal case visibility/management. Monorepo with a web admin
dashboard, a mobile app, and a Python API backend.

## Status

First functional MVP phase: the backend serves synthetic case data from
SQLite (`/api/cases`, `/api/cases/{id}`, `/api/metrics`), and **apps/admin**
is a working dashboard wired to it — case list with search/filter, a
case-details view, and live metrics. **apps/mobile** is still scaffolding
only. No AI agents and no legal-eligibility logic yet.

## Architecture

```
NyayDrishti/
├── apps/
│   ├── admin/    React + Vite + TypeScript — web dashboard
│   └── mobile/   React Native + Expo + TypeScript — mobile app
├── backend/      Python + FastAPI — API server
└── shared/       Shared TypeScript type definitions (types.ts)
```

- **apps/admin** now calls the backend's `/api/*` endpoints directly (plain
  `fetch`, see `apps/admin/src/api.ts`). **apps/mobile** doesn't talk to the
  backend or to apps/admin yet.
- **shared/types.ts** defines placeholder data shapes (`Case`, `User`) left
  over from scaffolding. apps/admin now has its own, more precise `Case`/
  `Metrics` types in `src/api.ts` that match the real API response shape;
  `shared/types.ts` isn't wired in anywhere and is unchanged by this phase.
- **backend** is called by apps/admin; apps/mobile still doesn't call it.

## Tech stack & versions (as installed)

| App | Stack | Versions |
|---|---|---|
| apps/admin | React + Vite + TS | Vite 8.3.5, React 19.3.1, TypeScript ~7.0.2 |
| apps/mobile | Expo + React Native + TS | Expo SDK 58.0.21, React Native 0.88.1, React 19.3.0, TypeScript 6.0.3 |
| backend | FastAPI + Uvicorn | Python 3.12.14, FastAPI 0.162.0, Uvicorn 0.54.0 |

Host tooling: Node v24.6.0, npm 11.5.1, git 2.54.0.

## Prerequisites

- Node.js + npm (for apps/admin and apps/mobile)
- Python 3.12+ with `venv` (for backend) — falls back to any Python 3.9+
- [Expo Go](https://expo.dev/go) on your phone, or an iOS/Android simulator,
  if you want to run apps/mobile on a device instead of the web preview

## Install & run

### Admin dashboard (web)

Start the backend first (below) — the dashboard fetches from it at
`http://localhost:8000` by default.

```bash
cd apps/admin
npm install
npm run dev        # starts Vite dev server, prints a localhost URL (default http://localhost:5173)
```

Backend running elsewhere? Point the dashboard at it with
`VITE_API_BASE_URL` (e.g. in `apps/admin/.env.local`):

```bash
echo "VITE_API_BASE_URL=http://127.0.0.1:8000" > apps/admin/.env.local
```

Verify a production build compiles:

```bash
npm run build       # tsc -b && vite build
npx tsc --noEmit    # typecheck only
```

### Mobile app

```bash
cd apps/mobile
npm install
npx expo start      # press 'a' (Android), 'i' (iOS), 'w' (web), or scan the QR code with Expo Go
```

Verify types without a simulator/device:

```bash
npx tsc --noEmit
```

### Backend API

```bash
cd backend
python3.12 -m venv venv        # use python3 if 3.12 isn't available
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Verify the health endpoint (in another terminal, with the server running):

```bash
curl http://127.0.0.1:8000/health
# -> {"status":"ok"}
```

Run the backend test suite:

```bash
cd backend && source venv/bin/activate && pytest
```

## Verifying the whole setup

Run these from the repo root to confirm everything is working:

```bash
# Admin: installs + production build
(cd apps/admin && npm install && npm run build)

# Mobile: installs + typecheck (no simulator needed)
(cd apps/mobile && npm install && npx tsc --noEmit)

# Backend: venv + install + start + health check
(cd backend && python3.12 -m venv venv && source venv/bin/activate \
  && pip install -r requirements.txt \
  && (uvicorn main:app --port 8000 &) \
  && sleep 1 && curl http://127.0.0.1:8000/health && echo)
```
