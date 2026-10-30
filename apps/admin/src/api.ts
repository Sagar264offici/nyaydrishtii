// Typed client for the NyayDrishti backend API.
// All data returned here is synthetic demo data (see backend/database.py seed set).

export type ReviewStatus = 'pending' | 'in_review' | 'reviewed' | 'escalated'

export interface Case {
  case_id: string
  custody_start_date: string
  custody_end_date: string | null
  charges: string[]
  review_status: ReviewStatus
  assigned_reviewer: string
  next_follow_up: string | null
}

export interface Metrics {
  total_cases: number
  status_counts: Record<ReviewStatus, number>
  overdue_follow_ups: number
  follow_up_status_counts: Record<FollowUpStatus, number>
}

// --- Document upload / extracted-fact verification ---
// Facts are candidates extracted from an uploaded PDF. They always start
// "unverified" (or "unknown" if nothing was found) — only a reviewer PATCH
// can mark one "verified" or "conflict". See backend/schemas.py.

export type FactType =
  | 'custody_start_date'
  | 'custody_end_date'
  | 'current_charges'
  | 'max_punishment'
  | 'max_punishment_source'
  | 'other_pending_cases'
  | 'exception_flags'
  | 'max_punishment_years'
  | 'death_or_life_punishment'
  | 'accused_caused_delay_days'

export type ExtractionMethod = 'text' | 'ocr' | 'unavailable' | 'manual'
export type VerificationStatus = 'unknown' | 'unverified' | 'verified' | 'conflict'

export type FactValue = string | string[] | number | boolean | null

export interface Fact {
  id: number
  case_id: string
  fact_type: FactType
  value: FactValue
  original_value: FactValue
  source_filename: string | null
  source_page: number | null
  extraction_method: ExtractionMethod
  verification_status: VerificationStatus
  reviewed_by: string | null
  reviewed_at: string | null
  verification_note: string | null
}

export interface DocumentPreviewResponse {
  filename: string
  case_id: string
  page_count: number
  extraction_method: ExtractionMethod
  message: string | null
  facts: Fact[]
}

export interface FactUpdate {
  value?: FactValue
  verification_status?: VerificationStatus
  reviewer?: string
  verification_note?: string
}

// --- Section 479 BNSS rule-engine evaluations ---
// Internal review-status flags only — never a bail/release decision. See
// backend/rules.py and the README. A reviewer must explicitly trigger each
// run; re-evaluating a case never overwrites its evaluation history.

export type EvaluationOutcome =
  | 'REVIEW_THRESHOLD_REACHED'
  | 'THRESHOLD_NOT_REACHED'
  | 'BLOCKED_MISSING_FACTS'
  | 'ESCALATED_LEGAL_REVIEW'

export interface RuleTraceEntry {
  rule: string
  result: string
  detail: string
}

export interface Evaluation {
  id: number
  case_id: string
  created_at: string
  reviewer: string
  rule_version: string
  outcome: EvaluationOutcome
  statutory_source: {
    act: string
    section: string
    title: string
    effective_date: string
    official_sources: string[]
    text: string
    verified_against_gazette: boolean
  }
  as_of_date: string
  inputs: Record<string, unknown>
  calculation: Record<string, number>
  trace: RuleTraceEntry[]
  blockers: string[]
  escalation_reasons: string[]
  explanation: string
  facts_snapshot: Fact[]
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

async function readErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string }
    return body?.detail ?? fallback
  } catch {
    return fallback // response body wasn't JSON — fall back to the generic message
  }
}

async function apiGet<T>(path: string): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`)
  } catch {
    throw new Error('Could not reach the backend. Is it running?')
  }
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, `Request failed (${res.status})`))
  }
  return res.json() as Promise<T>
}

export function fetchCases(): Promise<Case[]> {
  return apiGet<Case[]>('/api/cases')
}

export function fetchCase(caseId: string): Promise<Case> {
  return apiGet<Case>(`/api/cases/${encodeURIComponent(caseId)}`)
}

export function fetchMetrics(): Promise<Metrics> {
  return apiGet<Metrics>('/api/metrics')
}

export function fetchFacts(caseId: string): Promise<Fact[]> {
  return apiGet<Fact[]>(`/api/cases/${encodeURIComponent(caseId)}/facts`)
}

export async function uploadDocument(caseId: string, file: File): Promise<DocumentPreviewResponse> {
  const form = new FormData()
  form.append('case_id', caseId)
  form.append('file', file)

  let res: Response
  try {
    res = await fetch(`${API_BASE}/api/documents/preview`, { method: 'POST', body: form })
  } catch {
    throw new Error('Could not reach the backend. Is it running?')
  }
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, `Upload failed (${res.status})`))
  }
  return res.json() as Promise<DocumentPreviewResponse>
}

export async function patchFact(caseId: string, factId: number, update: FactUpdate): Promise<Fact> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/api/cases/${encodeURIComponent(caseId)}/facts/${factId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    })
  } catch {
    throw new Error('Could not reach the backend. Is it running?')
  }
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, `Update failed (${res.status})`))
  }
  return res.json() as Promise<Fact>
}

export function fetchEvaluations(caseId: string): Promise<Evaluation[]> {
  return apiGet<Evaluation[]>(`/api/cases/${encodeURIComponent(caseId)}/evaluations`)
}

export async function downloadReviewPack(caseId: string): Promise<Blob> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/api/cases/${encodeURIComponent(caseId)}/review-pack`)
  } catch {
    throw new Error('Could not reach the backend. Is it running?')
  }
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, `Could not generate the review pack (${res.status})`))
  }
  return res.blob()
}

export async function runEvaluation(caseId: string, reviewer: string): Promise<Evaluation> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/api/cases/${encodeURIComponent(caseId)}/evaluations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reviewer }),
    })
  } catch {
    throw new Error('Could not reach the backend. Is it running?')
  }
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, `Evaluation failed (${res.status})`))
  }
  return res.json() as Promise<Evaluation>
}

// --- Follow-up tasks ---
// Persistent tasks linked to a case. `due_at` accepts any ISO 8601 datetime;
// an <input type="datetime-local"> value (no UTC offset) is treated by the
// backend as already being UTC. `completed`/`cancelled` are terminal states
// — the backend rejects any further status change away from them.

export type FollowUpStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled'

export interface FollowUp {
  id: number
  case_id: string
  title: string
  description: string | null
  assigned_reviewer: string
  due_at: string
  status: FollowUpStatus
  created_at: string
  updated_at: string
  completed_at: string | null
  completed_by: string | null
  is_overdue: boolean
}

export interface FollowUpCreate {
  case_id: string
  title: string
  description?: string | null
  assigned_reviewer: string
  due_at: string
}

export interface FollowUpUpdate {
  title?: string
  description?: string | null
  assigned_reviewer?: string
  due_at?: string
  status?: FollowUpStatus
  // The reviewer making THIS change — required when setting status to
  // 'completed' or 'cancelled'. A supplied label, not an authenticated
  // identity (this app has no login).
  reviewer?: string
}

export interface FollowUpFilters {
  status?: FollowUpStatus
  reviewer?: string
  case_id?: string
  overdue?: boolean
}

async function apiMutate<T>(path: string, method: 'POST' | 'PATCH', body: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new Error('Could not reach the backend. Is it running?')
  }
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, `Request failed (${res.status})`))
  }
  return res.json() as Promise<T>
}

export function fetchFollowUps(filters: FollowUpFilters = {}): Promise<FollowUp[]> {
  const params = new URLSearchParams()
  if (filters.status) params.set('status', filters.status)
  if (filters.reviewer) params.set('reviewer', filters.reviewer)
  if (filters.case_id) params.set('case_id', filters.case_id)
  if (filters.overdue !== undefined) params.set('overdue', String(filters.overdue))
  const qs = params.toString()
  return apiGet<FollowUp[]>(`/api/followups${qs ? `?${qs}` : ''}`)
}

export function fetchCaseFollowUps(caseId: string): Promise<FollowUp[]> {
  return apiGet<FollowUp[]>(`/api/cases/${encodeURIComponent(caseId)}/followups`)
}

export function createFollowUp(payload: FollowUpCreate): Promise<FollowUp> {
  return apiMutate<FollowUp>('/api/followups', 'POST', payload)
}

export function patchFollowUp(followUpId: number, update: FollowUpUpdate): Promise<FollowUp> {
  return apiMutate<FollowUp>(`/api/followups/${followUpId}`, 'PATCH', update)
}

// --- Audit trail ---
// Append-only. `actor` is a supplied reviewer label, not an authenticated
// identity — this app has no login/authentication system.

export type AuditEventType =
  | 'fact_verified'
  | 'fact_corrected'
  | 'fact_conflict_flagged'
  | 'fact_conflict_resolved'
  | 'evaluation_run'
  | 'case_status_changed'
  | 'followup_created'
  | 'followup_updated'
  | 'followup_reassigned'
  | 'followup_started'
  | 'followup_completed'
  | 'followup_cancelled'

export interface AuditEvent {
  id: number
  case_id: string
  event_type: AuditEventType
  entity_id: string | null
  actor: string | null
  description: string
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  created_at: string
}

export function fetchAuditLog(caseId: string, limit = 50): Promise<AuditEvent[]> {
  return apiGet<AuditEvent[]>(`/api/cases/${encodeURIComponent(caseId)}/audit-log?limit=${limit}`)
}

// --- Case review-status changes ---
// The only case field a reviewer can change here is review_status; custody
// dates, charges, etc. remain read-only seed data.

export function patchCaseStatus(caseId: string, reviewStatus: ReviewStatus, reviewer: string): Promise<Case> {
  return apiMutate<Case>(`/api/cases/${encodeURIComponent(caseId)}`, 'PATCH', {
    review_status: reviewStatus,
    reviewer,
  })
}
