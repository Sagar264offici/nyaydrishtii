# NyayDrishti Mobile

React Native + Expo (SDK 58) + TypeScript companion app to the admin
dashboard. File-based routing via [Expo Router](https://docs.expo.dev/router/introduction/),
routes live under `src/app/`. Synthetic demo data only — see the banner in
the app and `backend/database.py` for the seed set.

## Configure the backend URL first

The app never hardcodes `localhost` as the backend address — a physical
device or an Android emulator can't reach your development machine there.
Create `apps/mobile/.env.local` (gitignored, machine-specific) with:

```bash
EXPO_PUBLIC_API_BASE_URL=http://<your-machine's-address>:8000
```

The right address depends on how you're running it:

| Target | Address to use |
|---|---|
| iOS Simulator | `http://127.0.0.1:8000` or `http://localhost:8000` (the simulator shares the Mac's network stack) |
| Android Emulator | `http://10.0.2.2:8000` (the emulator's alias for the host machine) |
| Physical device (Expo Go) | `http://<your-machine's-LAN-IP>:8000`, e.g. `http://192.168.1.42:8000` — find it with `ipconfig getifaddr en0` (macOS Wi-Fi) or `ipconfig`/`ifconfig` elsewhere. The device and your machine must be on the same network, and the backend must be started with `--host 0.0.0.0` (see below) so it accepts connections from outside localhost. |

If this isn't set, the app shows a "Backend not configured" screen instead
of silently failing with a confusing network error.

## Run it

```bash
# Terminal 1 — backend (from repo root), bound to all interfaces so a
# device/emulator on the same network can reach it, not just localhost
cd backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000

# Terminal 2 — mobile app (from repo root)
cd apps/mobile
npm install
npx expo start
```

Press `i` for the iOS simulator, `a` for an Android emulator, or scan the QR
code with [Expo Go](https://expo.dev/go) on a physical device. After
changing `.env.local`, fully reload the app (shake → Reload, or restart
`expo start`) — environment variables are only read at bundle time.

## Verify

```bash
npx tsc --noEmit    # typecheck
npx expo-doctor     # dependency/config sanity check
```

## What's here

- `src/api.ts` — typed fetch client, mirroring `apps/admin/src/api.ts`'s
  contract exactly (same backend). Mobile only needs a read-heavy subset
  plus follow-up create/status-change:
  `GET /api/cases`, `GET /api/cases/{id}`, `GET /api/metrics`,
  `GET /api/cases/{id}/facts`, `GET /api/cases/{id}/evaluations`,
  `GET /api/cases/{id}/audit-log`, `GET /api/cases/{id}/followups`,
  `POST /api/followups`, `PATCH /api/followups/{id}`.
- `src/constants.ts` — shared display labels (status/outcome/audit-event
  names), kept separate from both the API types and the UI.
- `src/utils/caseInsights.ts` — the one piece of derived "business logic":
  computing a case's outstanding issues (missing/unverified/conflicting
  facts, plus the latest evaluation's own stored blockers/escalation
  reasons) from already-fetched data. It mirrors the same logic in
  `backend/review_pack.py`'s "Outstanding Issues" section, and never
  recomputes anything the backend hasn't already computed.
- `src/components/` — `Badge`, `FactRow`, `EvaluationCard`, `AuditRow`,
  `FollowUpCard`, `CreateFollowUpForm`, `NotConfigured`, each used by both
  screens or just by case details.
- `src/app/index.tsx` — **Dashboard**: metrics summary (including real
  follow-up status counts), search (case ID/reviewer/charges), status
  filter chips, pull-to-refresh case list, loading/empty/error+retry states.
  Tapping a case navigates to its details.
- `src/app/case/[caseId].tsx` — **Case Details**: overview + custody dates;
  outstanding issues; all extracted facts with their verification status
  (read-only — editing/verifying a fact stays on the web admin); the latest
  Section 479 BNSS evaluation (outcome, calculation, explanation, blockers,
  escalation reasons, an expandable rule trace, and the Gazette-verification
  warning, always shown); recent audit history; and this case's follow-ups,
  grouped Overdue / Upcoming / Completed, with a create form and
  Start/Complete/Cancel actions (Complete/Cancel require a reviewer name;
  Start doesn't). Every action reloads the whole screen afterward, since a
  follow-up change also produces a new audit event worth showing.

## Scope, by design for this phase

- **Read-only for facts and evaluations.** Mobile shows what the backend has
  already extracted/computed; it never duplicates the Section 479 rule
  engine (that logic exists only in `backend/rules.py`) and never lets a
  reviewer edit or verify a fact from a phone. Use the web admin dashboard
  for that.
- **No PDF upload or Counsel Review Pack download on mobile** — both stay on
  the web admin dashboard, per this phase's own scope (avoids the added
  complexity of a mobile file-picker/PDF-viewer for marginal benefit).
  Documents already uploaded from the web are fully visible here.
- **No native date/time picker.** Adding one (e.g.
  `@react-native-community/datetimepicker`) would need a custom Expo dev
  build instead of plain Expo Go (see `apps/mobile/AGENTS.md`). The due-date
  field is a text input with quick "+1 day / +3 days / +1 week" presets that
  fill in a valid UTC timestamp.
- **No authentication.** This app has none, and didn't add any. Every
  "reviewer" field (assigned reviewer, the actor completing/cancelling a
  follow-up) is a free-text label the person typing it supplies — never an
  authenticated identity.
- **No case review-status change, no editing a follow-up's details** (title/
  description/due date/assignee) from mobile — only status transitions
  (start/complete/cancel). Both remain admin-dashboard-only, keeping the
  phone screens focused on review and triage rather than data entry.
