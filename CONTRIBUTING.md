# Contributing

Thanks for taking a look. This is a hackathon-style monorepo with three parts:

- `apps/admin` — React + Vite + TypeScript web dashboard.
- `apps/mobile` — React Native + Expo mobile app.
- `backend` — Python + FastAPI API server.

## Getting started

See [SETUP.md](SETUP.md) and [README.md](README.md) for the full setup path.
In short:

1. Start the backend (`backend/`) first — the apps talk to it.
2. Run the admin dashboard from `apps/admin/`.
3. Run the mobile app from `apps/mobile/`, with `EXPO_PUBLIC_API_BASE_URL`
   set for your target device/simulator.

## Before you open a pull request

- Keep changes scoped. This repo is small enough that one PR should do one
  clear thing.
- If you touch the API contract, update both typed clients
  (`apps/admin/src/api.ts` and `apps/mobile/src/api.ts`) so they stay in sync.
- Run the checks that are relevant to what you changed:
  - admin: `npm run build` and `npx tsc --noEmit`
  - mobile: `npx tsc --noEmit`
  - backend: `pytest` (with a fresh DB is safest — delete `backend/nyaydrishti.db`
    before running, or let the test suite do its own throwaway DB)
- Do not commit local artifacts: `node_modules/`, virtualenvs, built bundles,
  `.env` files, or the local SQLite DB. The `.gitignore` should already cover
  these, but double-check `git status` before pushing.

## A note on the rule engine and legal content

The Section 479 BNSS rule engine in `backend/rules.py` is a deterministic,
auditable Python function. It produces an internal review-status flag only —
never a bail/release decision or a guarantee of any legal outcome.

The statutory text it uses has **not** been verified against the Gazette of
India or an India Code PDF. It was captured from a bare-act reproduction and
cross-checked for structural consistency against several independent legal
commentary sources. If you touch the statutory text, rule logic, or the
documented assumptions, say so clearly in the PR description.

## Data

All case data in `backend/database.py` is fictional demonstration data. Do not
treat it as real case records.

## No AI in the pipeline

This codebase does not use AI agents or external AI/network calls for document
extraction or PDF generation. Extraction uses PyMuPDF, optional local
Tesseract, and hand-written heuristics only; the PDF is rendered locally with
reportlab. If a proposed change introduces external network calls or an AI
dependency, call it out explicitly in the PR.
