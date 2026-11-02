# Setting up NyayDrishti from a fresh clone

This is the shortest path to a working checkout. The full reference lives in
[README.md](README.md); this file is just the "get it running" checklist.

## 1. Backend

```bash
cd backend
python3.12 -m venv venv        # or: python3 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

The API starts at `http://localhost:8000`. Confirm it with:

```bash
curl http://127.0.0.1:8000/health
# -> {"status":"ok"}
```

There is no separate database setup step: `backend/database.py` creates and
seeds `nyaydrishti.db` on first startup. The seed data is synthetic
demonstration data only.

## 2. Admin dashboard (web)

```bash
cd apps/admin
npm install
npm run dev
```

The dashboard opens at `http://localhost:5173` and talks to the backend at
`http://localhost:8000` by default.

If your backend runs somewhere else, set `VITE_API_BASE_URL` before starting
the dashboard:

```bash
echo "VITE_API_BASE_URL=http://127.0.0.1:8000" > apps/admin/.env.local
```

## 3. Mobile app

Start the backend **bound to all interfaces** first, so a device or emulator
can reach it:

```bash
cd backend && source venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 8000
```

Then configure the backend address for your target and start the app:

```bash
cd apps/mobile
echo "EXPO_PUBLIC_API_BASE_URL=http://127.0.0.1:8000" > .env.local   # iOS Simulator example
npm install
npx expo start
```

The correct `EXPO_PUBLIC_API_BASE_URL` depends on your target
(iOS Simulator, Android Emulator, or a physical device). See
[README.md](README.md) and `apps/mobile/README.md` for the exact address to
use for each.

## What is in this repo

- `apps/admin` — React + Vite + TypeScript web dashboard.
- `apps/mobile` — React Native + Expo mobile app.
- `backend` — Python + FastAPI API server, SQLite storage, Section 479 BNSS
  rule engine, PDF review-pack generator, follow-up tasks, and an append-only
  audit trail.
- `shared` — leftover scaffold types; not wired into either app today.

## Useful checks

From the repo root:

```bash
(cd apps/admin && npm install && npm run build)
(cd apps/mobile && npm install && npx tsc --noEmit)
(cd backend && python3.12 -m venv venv && source venv/bin/activate \
  && pip install -r requirements.txt \
  && rm -f nyaydrishti.db && pytest \
  && (uvicorn main:app --port 8000 &) \
  && sleep 1 && curl http://127.0.0.1:8000/health && echo)
```

## Notes

- This app has no authentication/login. Every "reviewer" field anywhere in the
  API is a free-text label the caller supplied, not a verified identity.
- The Section 479 BNSS rule engine is a deterministic Python function. It
  produces an internal review-status flag only — never a bail/release decision
  or a guarantee of any legal outcome. The statutory text it uses has not been
  verified against the Gazette of India; see [README.md](README.md) for the
  full warning.
- All case data is fictional demonstration data.
