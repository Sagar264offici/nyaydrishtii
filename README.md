# NyayDrishti

Hackathon MVP for legal case visibility/management. Monorepo with a web admin
dashboard, a mobile app, and a Python API backend.

## Status

First functional MVP phase: the backend serves synthetic case data from
SQLite (`/api/cases`, `/api/cases/{id}`, `/api/metrics`), and **apps/admin**
is a working dashboard wired to it — case list with search/filter, a
case-details view, and live metrics.

Second phase: document upload and fact extraction, so a reviewer can upload
a case PDF and verify the facts it suggests instead of retyping them.

- Backend: `POST /api/documents/preview` accepts a PDF, extracts text with
  PyMuPDF (falling back to Tesseract OCR if the text layer is empty and
  OCR is installed), and runs a small keyword/regex heuristic over the text
  to suggest candidate facts — custody dates, current charges, maximum
  punishment + source, other pending cases, and a fixed set of exception
  keywords (juvenile, first-time offender, medical ground, senior citizen).
  `GET /api/cases/{id}/facts` and `PATCH /api/cases/{id}/facts/{fact_id}`
  let a reviewer read, edit, and verify or flag each one.
- Admin: each case's detail page has an upload box and a list of the
  extracted facts, each showing its source filename/page, extraction
  method, and a status badge (unknown / unverified / verified / conflict),
  with inline edit + verify/flag controls.

Third phase: a deterministic rule engine for **Section 479, Bharatiya
Nagarik Suraksha Sanhita (BNSS), 2023** — the maximum-undertrial-detention
provision — that turns a case's reviewer-verified facts into an **internal
review-status flag**. See "Section 479 BNSS rule engine" below for the full
statutory source, logic, assumptions, and limitations — in short: it never
infers a missing fact, never auto-verifies anything, never overwrites
evaluation history, and never outputs a bail/release decision.

- Backend: three new `FactType`s (`max_punishment_years`,
  `death_or_life_punishment`, `accused_caused_delay_days`) feed the engine,
  reusing the existing fact-verification machinery end to end — no new
  verification workflow was needed. `POST /api/cases/{id}/evaluations` runs
  one evaluation (reviewer required) and appends it to that case's
  evaluation history; `GET /api/cases/{id}/evaluations` lists it, newest
  first. Evaluations are append-only — there is no update/delete path.
- Admin: each case's detail page now also has a "Section 479 BNSS
  Evaluation" panel — a reviewer-name field, a "Run Evaluation" button, and
  the full history of past evaluations (outcome badge, explanation,
  blockers/escalation reasons, the calculation, and an expandable rule
  trace + statutory text).

Fourth phase (this one): a **Counsel Review Pack** — a downloadable PDF that
packages a case's current facts and most recent Section 479 evaluation (if
any) into one document for human counsel to read offline. See "Counsel
Review Pack (PDF)" below. It only formats data already on record — it never
runs a new evaluation, never invents a missing value, and is clearly marked
throughout as a draft aid, not a judicial determination.

- Backend: `GET /api/cases/{id}/review-pack` renders the PDF on demand with
  [reportlab](https://www.reportlab.com/) (the one new dependency this phase
  needed — stdlib has no PDF writer).
- Admin: each case's detail page has a "Download Counsel Review Pack" button.

Fifth phase (this one): persistent **follow-up tasks** linked to a case, and
an **append-only audit trail** covering fact verification, evaluations,
follow-up changes, and case-status changes. See "Follow-up tasks" and
"Audit trail" below.

- Backend: `follow_ups` and `audit_log` are new SQLite tables. Follow-ups
  have a full status lifecycle (`pending` → `in_progress` → `completed` /
  `cancelled`, the latter two terminal) with overdue computed from `due_at`
  vs. the current time in UTC (never a naive/local-time comparison). Every
  write that should be logged (a fact edit, an evaluation run, a follow-up
  change, a case-status change) inserts its audit row in the **same SQLite
  transaction** as the underlying change, so the two can never drift apart.
  A true no-op request (identical values resubmitted) logs nothing.
- Admin: a new "Follow-ups" top-level view (Overdue / Upcoming / Completed,
  with status + reviewer filters, create/edit forms, and Start/Complete/
  Cancel actions), a case-scoped follow-up section and audit-history list on
  each case's detail page, and a small control to change a case's review
  status. Dashboard metrics now include real follow-up status counts.
- No new backend dependency and no new admin dependency were needed.

Eighth phase (this one): **apps/mobile** is now a functional companion app
(Expo Router, file-based routes under `src/app/`) — a case dashboard and a
case-details screen, talking to the same backend as the admin dashboard. See
`apps/mobile/README.md` for full setup. It's deliberately read-heavy: facts
and evaluations are view-only (no duplicate rule engine, no fact editing),
and PDF upload / the Counsel Review Pack stay web-only. The one write path
is follow-up create and status changes (start/complete/cancel), reusing the
exact same backend endpoints the admin dashboard uses. No new backend
changes were needed for this phase.

No AI agents anywhere in this codebase. No external AI/network calls for
extraction (PyMuPDF + optional local Tesseract + hand-written heuristics
only, fully offline) or for the PDF (reportlab renders locally; nothing
about a case is ever sent to an external service). The rule engine is
plain, auditable Python — no ML, no LLM call, nothing probabilistic. It
never outputs a bail/release decision or a release-eligibility label; see
the dedicated sections below.

This application has **no authentication/login system**. Every "reviewer"
field anywhere in the API (`assigned_reviewer`, `reviewed_by`, an
evaluation's `reviewer`, a follow-up's `completed_by`, an audit event's
`actor`) is a free-text label the caller supplied, never a verified
identity — nothing in this codebase treats it as one.

## Architecture

```
NyayDrishti/
├── apps/
│   ├── admin/    React + Vite + TypeScript — web dashboard
│   └── mobile/   React Native + Expo + TypeScript — mobile app
├── backend/      Python + FastAPI — API server
└── shared/       Shared TypeScript type definitions (types.ts)
```

- **apps/admin** and **apps/mobile** each call the backend's `/api/*`
  endpoints directly over plain `fetch` (`apps/admin/src/api.ts` and
  `apps/mobile/src/api.ts` respectively) — they don't call each other, and
  each has its own typed client mirroring the same backend contract (mobile's
  is a read-heavy subset; see `apps/mobile/README.md`).
- **shared/types.ts** defines placeholder data shapes (`Case`, `User`) left
  over from scaffolding. Neither app's own `api.ts` is wired to it — both
  define their own, more precise types matching the real API response shape.
- **backend** is called by both apps/admin and apps/mobile.

## Tech stack & versions (as installed)

| App | Stack | Versions |
|---|---|---|
| apps/admin | React + Vite + TS | Vite 8.3.5, React 19.3.1, TypeScript ~7.0.2 |
| apps/mobile | Expo + React Native + TS | Expo SDK 58.0.21, Expo Router ~58.0.28, React Native 0.88.1, React 19.3.0, TypeScript 6.0.3 |
| backend | FastAPI + Uvicorn | Python 3.12.14, FastAPI 0.162.0, Uvicorn 0.54.0, PyMuPDF 2.0, pytesseract 0.3.13, Pillow 13.0.0, reportlab 5.1.0 |

Host tooling: Node v24.6.0, npm 11.5.1, git 2.54.0.

## Prerequisites

- Node.js + npm (for apps/admin and apps/mobile)
- Python 3.12+ with `venv` (for backend) — falls back to any Python 3.9+
- [Expo Go](https://expo.dev/go) on your phone, or an iOS/Android
  simulator/emulator, to run apps/mobile (it targets Android/iOS only — no
  web target is configured)

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

Start the backend first, bound to all interfaces so a device/emulator can
reach it (not just `localhost`):

```bash
cd backend && source venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 8000
```

Configure the backend address **before** starting the app — see
`apps/mobile/README.md` for the exact value per target (iOS Simulator,
Android Emulator, or a physical device each need a different address; the
app never hardcodes `localhost` and shows a clear setup screen if this isn't
set):

```bash
cd apps/mobile
echo "EXPO_PUBLIC_API_BASE_URL=http://127.0.0.1:8000" > .env.local   # iOS Simulator example
npm install
npx expo start      # press 'a' (Android), 'i' (iOS), or scan the QR code with Expo Go
```

Verify types without a simulator/device:

```bash
npx tsc --noEmit
npx expo-doctor     # dependency/config sanity check
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

#### Optional: OCR for scanned PDFs

Document upload works without this — PyMuPDF extracts the text layer, and if
a PDF has no text layer at all (a pure scan) and OCR isn't available, the
API returns a clear "enter facts manually" response instead of failing.
If you want OCR to actually run for scanned PDFs, install the Tesseract
binary separately (it's a system package, not a pip package — the Python
side, `pytesseract`, is already in `requirements.txt`):

```bash
brew install tesseract        # macOS
# or: apt-get install tesseract-ocr   (Debian/Ubuntu)
```

#### Document upload & fact verification

```
POST  /api/documents/preview          multipart/form-data: case_id, file (PDF)
GET   /api/cases/{case_id}/facts      -> list of extracted facts for the case
PATCH /api/cases/{case_id}/facts/{id} -> edit a fact's value and/or verify/flag it
```

#### Section 479 BNSS evaluations

```
POST /api/cases/{case_id}/evaluations  body: {"reviewer": "..."}  -> run one evaluation, append to history
GET  /api/cases/{case_id}/evaluations  -> this case's evaluation history, newest first
```

#### Counsel Review Pack

```
GET /api/cases/{case_id}/review-pack  -> PDF (application/pdf), Content-Disposition: attachment
```

No request body or query params — it renders whatever is currently on
record for that case. See "Counsel Review Pack (PDF)" below for exactly
what's in it.

#### Follow-up tasks

```
POST  /api/followups                  -> create a follow-up (case_id, title, assigned_reviewer, due_at required)
GET   /api/followups                  -> list/filter: ?status=&reviewer=&case_id=&overdue=true|false
GET   /api/cases/{case_id}/followups  -> this case's follow-ups
PATCH /api/followups/{id}             -> edit details/assignment/due date, and/or change status
```

`due_at` accepts any ISO 8601 datetime; a naive one (no UTC offset — e.g.
from an `<input type="datetime-local">`) is treated as already being UTC.
`completed` and `cancelled` are terminal — a further status change away
from either is rejected with 422. Completing or cancelling requires a
`reviewer` in the PATCH body (then recorded as `completed_by`); a plain
detail edit does not. Editing a completed/cancelled follow-up's title,
description, due date, or assignee is still allowed and never clears its
`completed_at`/`completed_by`.

#### Case review-status changes

```
PATCH /api/cases/{case_id}  body: {"review_status": "...", "reviewer": "..."}
```

The only case field this can change; custody dates, charges, etc. stay
read-only seed data. A request that doesn't actually change the status is a
no-op (no write, no audit event).

#### Audit trail

```
GET /api/cases/{case_id}/audit-log  -> ?limit=50&offset=0 (limit capped at 200), newest first
```

Limitations, by design for this phase:

- Extraction is a **naive keyword/regex heuristic** (see
  `backend/extraction.py`), not NLP or AI — no external AI/network calls are
  made anywhere in this flow, and none should be added. It matches a trigger
  phrase ("custody start", "maximum punishment", "Section ... IPC", etc.) and
  reads the rest of that line; it will miss facts phrased unusually or split
  across lines. `current_charges` requires the word "charge" or the phrase
  "accused of" on the line (bare "section"/"ipc" were removed as triggers
  after a Phase 7 review found they could misattribute a punishment-citation
  line, e.g. "Section 379 IPC provides for...", as a charges line).
  `death_or_life_punishment` has a basic negation guard ("not", "no",
  "without", "excluding", "except" anywhere on the matched line suppresses
  the candidate) so an obviously negated sentence doesn't assert a wrong
  `True` — it's a naive, line-level guard, not real negation parsing, so
  unusual phrasing can still slip through either direction. Every extracted
  value is unverified either way until a reviewer confirms it.
- A fact extracted from a document is **never** automatically "verified" —
  it starts "unverified" (found) or "unknown" (not found in any upload) until
  a reviewer explicitly verifies or flags it via the PATCH endpoint.
- Re-uploading a document never overwrites a fact a reviewer already
  verified or flagged as conflicting.
- Uploaded PDF bytes are processed in memory only — never written to disk,
  never exposed via any route.
- 10 MB upload limit, enforced by reading at most one byte over that limit
  rather than buffering the whole upload first; non-PDF files and
  corrupted/unparseable PDFs are rejected with a clear error instead of
  crashing.
- `max_punishment_years` must be a finite number between 0 and 200
  (exclusive/inclusive) — NaN/Infinity are rejected (a Phase 7 review found
  they used to pass validation and then crash the rule engine's rounding
  with an unhandled exception instead of a clean error).
- No legal-eligibility or release-decision logic existed in this phase —
  facts were just data for a human reviewer, not a verdict. (The rule
  engine, added next, still never outputs a release decision — see below.)
- Use synthetic/test documents only; this phase isn't wired to any real
  case-record source.

## Section 479 BNSS rule engine

`backend/rules.py` is a single pure function,
`evaluate_section_479(facts, as_of_date) -> EvaluationResult`. It is
deterministic (no randomness, no ML/LLM call) and produces an **internal
review-status flag**, never a bail/release decision or a guarantee of any
legal outcome. A reviewer must explicitly click "Run Evaluation" — it never
runs automatically — and every run is appended to that case's evaluation
history; there is no code path that updates or deletes a past evaluation.

### Statutory source

- **Act:** Bharatiya Nagarik Suraksha Sanhita, 2023 (Act No. 46 of 2023),
  Section 479 — "Maximum period for which an undertrial prisoner can be
  detained." Effective 1 July 2024 (it replaces old CrPC Section 436A).
- **Official sources** (as given for this task): the
  [India Code entry](https://www.indiacode.nic.in/indiacode/handle/123456789/20099)
  and the [MHA new-criminal-laws page](https://www.mha.gov.in/en/commoncontent/new-criminal-laws).
  Both returned HTTP 403 to automated fetches while building this phase.
- **What was actually used:** the section text in `rules.py`
  (`STATUTORY_SOURCE["text"]`) was captured from a bare-act reproduction
  (apnilaw.com) and cross-checked for structural consistency against several
  independent legal-commentary sources (LiveLaw, writinglaw.com,
  latestlaws.com, advocatemanishjha.com), all of which described the same
  three sub-sections, the same two provisos and two thresholds, and the same
  exclusions. **It has not been verified against the Gazette of India or an
  India Code PDF directly** — `STATUTORY_SOURCE["verified_against_gazette"]`
  is `False` for exactly this reason, and the admin UI surfaces that flag
  next to the statutory text on every evaluation. **A legal reviewer should
  confirm this text against an official copy before this engine is used for
  anything beyond an internal, informational review-status flag.**

### Logic

Every evaluation first checks five facts are reviewer-**verified**
(`custody_start_date`, `max_punishment_years`, `death_or_life_punishment`,
`exception_flags`, `other_pending_cases`) — "missing", "unverified"
(extracted but unreviewed), and "conflict" are all treated as unusable and
all produce `BLOCKED_MISSING_FACTS`, naming exactly which fact(s) and why.
Nothing is ever inferred or assumed.

Once all five are verified, in order:

1. **Death/life exclusion** — if `death_or_life_punishment` is true, Section
   479(1)'s own opening clause excludes the offence entirely →
   `ESCALATED_LEGAL_REVIEW` (the engine makes no determination either way).
2. **Outer cap (third proviso)** — if custody so far has reached the full
   maximum punishment period, that proviso applies "in any case," overriding
   the multiple-cases bar below → `REVIEW_THRESHOLD_REACHED`.
3. **Multiple pending cases (sub-section 2)** — if `other_pending_cases` is
   non-empty, sub-section (2) bars release. *What counts as "multiple
   cases" under (2) is a genuinely contested interpretive question* (raised
   independently by legal commentary found while researching this phase) —
   this engine does not decide it, it escalates →
   `ESCALATED_LEGAL_REVIEW`.
4. **One-half / one-third thresholds** — if custody has reached one-half of
   the maximum punishment, or one-third **and** the accused is a verified
   first-time offender, → `REVIEW_THRESHOLD_REACHED` (first proviso).
   Otherwise → `THRESHOLD_NOT_REACHED`.

`custody_end_date`, if verified and set, is used as the "as of" date instead
of today (for a case whose custody period already ended).
`accused_caused_delay_days`, if verified, is subtracted from the raw custody
count per the Explanation to Section 479(1); if never verified, the engine
defaults to **not** excluding any delay (the conservative direction — it
only ever reduces counted custody, so a missing value can't manufacture a
threshold crossing that isn't backed by evidence).

### Implementation assumptions (not statutory text)

- **Years → days:** `max_punishment_years` (a reviewer-entered number) is
  converted to a day threshold using `365.25` days/year
  (`rules.DAYS_PER_YEAR`). The custody side of every comparison is always a
  real calendar-day count (`date` subtraction), so leap years are already
  handled correctly there — this constant only scales the statutory
  duration input, which was an approximation to begin with. Flagged for
  legal review if a more precise definition of "year" matters here.
- **"First-time offender"** is read from the existing `exception_flags`
  fact (exact, case-insensitive string match) rather than a new dedicated
  fact type — it reuses the phrase the extraction heuristic already looks
  for, so no new verification workflow was needed.
- **"Other pending cases"** reuses the existing `other_pending_cases` fact
  as the sub-section (2) trigger. Charges *within* the same case/FIR are
  not treated as "multiple cases" for this purpose — only a non-empty,
  reviewer-verified list of genuinely separate other cases does.

### Tests

`backend/test_main.py` covers: one-half and one-third thresholds (including
exact-boundary and leap-year date math), thresholds not reached, death/life
exclusion, multiple-pending-cases escalation, the outer cap overriding that
escalation, accused-caused-delay exclusion changing the outcome, blocked
evaluations for missing/unverified/conflicting facts, a required reviewer,
and that re-evaluating a case appends to history rather than overwriting it
(both runs are still retrievable, in order, each tagged with its
`rule_version`).

## Counsel Review Pack (PDF)

`GET /api/cases/{case_id}/review-pack` (`backend/review_pack.py`) renders a
case's **current recorded state** into a PDF for human counsel to read
offline. It is a pure formatter: it reads the case record, that case's
facts, and its evaluation history exactly as already persisted, and
**never computes or infers anything new** — in particular, it never runs a
Section 479 evaluation. Downloading the same case's pack repeatedly never
changes its evaluation history.

Clicking "Download Counsel Review Pack" on a case's detail page in the
admin dashboard fetches this endpoint as a blob and saves it as
`NyayDrishti-ReviewPack-{case_id}.pdf`.

What's in it:

1. **Case overview** — case ID, review status, assigned reviewer, report
   generation timestamp.
2. **Custody timeline** — the `custody_start_date`/`custody_end_date`
   facts (value *and* verification status, side by side) and a custody
   duration figure computed only for display (plain date arithmetic as of
   the report's generation time, or the verified custody end date if one
   is on record) — explicitly labelled as not a legal-threshold
   calculation, to avoid being confused with the rule engine's own numbers.
3. **Facts on record** — all ten fact types, each with its value *and*
   verification status shown together (a value next to UNVERIFIED,
   UNKNOWN, or CONFLICT is always visibly a candidate, never presented as
   established), plus source filename/page and reviewer.
4. **Legal rule evaluation** — the most recent evaluation only (`GET
   .../evaluations` sorted newest-first, index 0), with its outcome, rule
   version, calculation, and full rule-by-rule trace. If no evaluation has
   ever been run for the case, this section says so plainly instead of
   showing any outcome.
5. **Outstanding issues** — every missing/unverified/conflicting fact, plus
   (if an evaluation exists) its stored blockers and escalation reasons,
   verbatim.
6. **Review history** — every evaluation on record for the case (not just
   the latest), timestamp + reviewer + rule version + outcome.
7. **Sources and limitations** — the extraction method's limitations, and
   (if an evaluation exists) its statutory source text, official source
   links, and the `verified_against_gazette` flag, prominently labelled
   when still unverified.
8. **Disclaimer** — appears on every page's header (a fixed banner) and
   again as its own final section: this is a draft counsel-review aid, not
   a judicial determination, bail order, or release authorization.

Layout: reportlab `platypus` tables with `repeatRows=1` (headers repeat if
a table spans a page break) and all variable-length text wrapped in
`Paragraph` flowables (not raw strings) so long explanations or note text
wrap instead of overflowing or being silently cut off. Page numbers
("Page X of Y") and the case ID + generation timestamp are drawn in a
footer via a custom canvas, using reportlab's standard two-pass "buffer
every page, draw the footer once the total count is known" recipe.

Tests (`backend/test_main.py`) cover: a case with an evaluation (outcome,
rule version, trace all present in the extracted text), a case with facts
but no evaluation ("not been performed" message, no outcome string
present), a case with no document uploaded at all, verified/unverified/
unknown/conflict facts all appearing with their status and a conflict
note, source filename + page references, the Gazette-verification warning
and all three disclaimer clauses, an unknown case ID (404), and that
downloading the same pack three times in a row leaves the evaluation
history byte-for-byte unchanged.

## Follow-up tasks

A follow-up is a persistent task linked to a case: title, optional
description, assigned reviewer, a due date/time, and a status
(`pending` → `in_progress` → `completed`/`cancelled`). `backend/database.py`
holds the `follow_ups` table; validation and the status-transition rules
live in `main.py` (consistent with how fact/evaluation validation already
lives there rather than in the database layer).

- **Overdue** = `due_at` earlier than the current time, for a task that is
  neither `completed` nor `cancelled`. `due_at` is always normalized to a
  UTC ISO string on write (`main._normalize_due_at`); a naive input with no
  offset is assumed to already be UTC. The comparison against "now" always
  happens in UTC, so a `due_at` submitted with an explicit non-UTC offset is
  still compared correctly rather than by raw/local wall-clock numbers —
  see `test_follow_up_overdue_timezone_boundary` for the exact scenario
  this guards against.
- `completed` and `cancelled` are **terminal** — `PATCH .../followups/{id}`
  rejects (422) any further status change away from either. Non-status
  edits (title, description, due date, assignee) remain allowed afterward
  and never touch `completed_at`/`completed_by` — those two fields are only
  ever written by the transition into `completed` or `cancelled` itself, so
  completion history survives later edits.
- Completing or cancelling requires a `reviewer` in the request body (who
  is recorded as `completed_by`); every other edit's `reviewer` field is
  optional (used only to attribute the audit event — see below).
- `GET /api/metrics`'s `overdue_follow_ups` and new
  `follow_up_status_counts` are computed from this table directly, replacing
  the old placeholder that derived `overdue_follow_ups` from each case's
  single static `next_follow_up` seed date (that field and its column in the
  admin case table are unchanged and still present — they just no longer
  feed the metrics calculation).

## Audit trail

`audit_log` is an append-only table (`backend/database.py` — there is
deliberately no update/delete function for it). An event is logged for:
fact verification/correction, a fact being flagged or resolved out of
conflict, an evaluation run (with its rule version and outcome), a
follow-up's creation/edit/reassignment/start/completion/cancellation, and a
case's review-status change.

- **Atomicity.** Every one of those writes logs its audit row in the exact
  same SQLite transaction as the change it describes (one `get_connection()`
  block, one `conn.commit()` — see `update_fact`, `insert_evaluation`,
  `create_follow_up`, `update_follow_up`, `update_case_status` in
  `database.py`). The change and its audit entry can't drift apart.
- **No duplicate events.** Each endpoint computes whether anything
  *semantically* changed before logging — a true no-op request (identical
  values resubmitted, or an explicit-null field that changes nothing) logs
  nothing. A bookkeeping-only field like a fact's `reviewed_at` timestamp
  updating on its own doesn't count as a semantic change either.
- **Before/after values.** Where practical, the event's `before`/`after`
  only contain the fields that actually changed (not the whole record) —
  both to keep the log focused on what changed and to avoid logging more
  than necessary.
- **Not an authenticated identity.** `actor` (and every other reviewer-style
  field in this app: `assigned_reviewer`, `reviewed_by`, an evaluation's
  `reviewer`, a follow-up's `completed_by`) is a free-text label the caller
  supplied — this application has no login system, so none of these fields
  should ever be treated as a verified identity.
- `GET /api/cases/{case_id}/audit-log?limit=&offset=` returns events newest
  first, `limit` capped at 200 (default 50).

## Verifying the whole setup

Run these from the repo root to confirm everything is working:

```bash
# Admin: installs + production build
(cd apps/admin && npm install && npm run build)

# Mobile: installs + typecheck (no simulator needed)
(cd apps/mobile && npm install && npx tsc --noEmit)

# Backend: venv + install + tests + start + health check
(cd backend && python3.12 -m venv venv && source venv/bin/activate \
  && pip install -r requirements.txt \
  && rm -f nyaydrishti.db && pytest \
  && (uvicorn main:app --port 8000 &) \
  && sleep 1 && curl http://127.0.0.1:8000/health && echo)
```
# nyaydrishtii
# nyaydrishtii
