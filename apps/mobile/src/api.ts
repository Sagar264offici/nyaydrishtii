// Typed client for the NyayDrishti backend API, shared by every mobile
// screen. Mirrors apps/admin/src/api.ts's contract exactly (same backend) --
// mobile only needs a read-heavy subset plus follow-up create/status-change.
// PDF upload and the Counsel Review Pack stay web-only (see the mobile
// README) to avoid duplicating that complexity here.
//
// The backend base URL is never hardcoded to "localhost": a physical device
// or an Android emulator cannot reach the development machine at that
// address. Set EXPO_PUBLIC_API_BASE_URL in apps/mobile/.env.local to your
// machine's LAN address -- see the mobile README for exact steps.

export const API_BASE_URL: string | null = process.env.EXPO_PUBLIC_API_BASE_URL ?? null

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

// --- Document facts (read-only on mobile; upload/edit stays on the web admin) ---

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

// --- Section 479 BNSS evaluations (read-only on mobile -- the rule engine
// itself lives only in the backend; nothing here recomputes it) ---

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

// --- Follow-up tasks ---

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
  // The reviewer making THIS change -- required when completing/cancelling.
  // A supplied label, not an authenticated identity (this app has no login).
  reviewer?: string
}

// --- Audit trail (read-only) ---

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

export class ApiNotConfiguredError extends Error {
  constructor() {
    super(
      "Backend URL not configured. Set EXPO_PUBLIC_API_BASE_URL in apps/mobile/.env.local " +
        'to your machine\'s LAN address (see the mobile README), then restart the app.',
    )
    this.name = 'ApiNotConfiguredError'
  }
}

async function readErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string }
    return body?.detail ?? fallback
  } catch {
    return fallback // response body wasn't JSON -- fall back to the generic message
  }
}

async function apiGet<T>(path: string): Promise<T> {
  if (!API_BASE_URL) throw new ApiNotConfiguredError()
  let res: Response
  try {
    res = await fetch(`${API_BASE_URL}${path}`)
  } catch {
    throw new Error('Could not reach the backend. Is it running, and is the configured URL reachable from this device?')
  }
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, `Request failed (${res.status})`))
  }
  return res.json() as Promise<T>
}

async function apiMutate<T>(path: string, method: 'POST' | 'PATCH', body: unknown): Promise<T> {
  if (!API_BASE_URL) throw new ApiNotConfiguredError()
  let res: Response
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new Error('Could not reach the backend. Is it running, and is the configured URL reachable from this device?')
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

export function fetchEvaluations(caseId: string): Promise<Evaluation[]> {
  return apiGet<Evaluation[]>(`/api/cases/${encodeURIComponent(caseId)}/evaluations`)
}

export function fetchAuditLog(caseId: string, limit = 15): Promise<AuditEvent[]> {
  return apiGet<AuditEvent[]>(`/api/cases/${encodeURIComponent(caseId)}/audit-log?limit=${limit}`)
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
