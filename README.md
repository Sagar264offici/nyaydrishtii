# NyayDrishti

Hackathon MVP for legal case visibility/management. Monorepo with a web admin
dashboard, a mobile app, and a Python API backend.

## Status

Scaffolding only — each app boots and shows a basic homepage/screen, and the
backend exposes a working `/health` check. No AI agents, no legal-calculation
logic, and no API wiring between the apps yet.

## Architecture

```
NyayDrishti/
├── apps/
│   ├── admin/    React + Vite + TypeScript — web dashboard
│   └── mobile/   React Native + Expo + TypeScript — mobile app
├── backend/      Python + FastAPI — API server
└── shared/       Shared TypeScript type definitions (types.ts)
```

- **apps/admin** and **apps/mobile** don't talk to each other or to the
  backend yet — each is an independent, independently-runnable scaffold.
- **shared/types.ts** defines placeholder data shapes (`Case`, `User`) both
  frontends will eventually consume. It's plain `.ts`, not wired into either
  app as a package/workspace dependency yet — that plumbing is deferred until
  an app actually needs to import it (no npm workspaces, no build step).
- **backend** is standalone, not yet called by either frontend.

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

```bash
cd apps/admin
npm install
npm run dev        # starts Vite dev server, prints a localhost URL
```

Verify a production build compiles:

```bash
npm run build
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
