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
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

async function apiGet<T>(path: string): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`)
  } catch {
    throw new Error('Could not reach the backend. Is it running?')
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body = (await res.json()) as { detail?: string }
      if (body?.detail) detail = body.detail
    } catch {
      // response body wasn't JSON — fall back to the generic message above
    }
    throw new Error(detail)
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
