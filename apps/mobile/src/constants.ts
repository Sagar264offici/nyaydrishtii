// Shared display labels, kept in one place so every screen/component uses
// the same wording (and so this stays separate from both the API types and
// the UI that renders them).

import type {
  AuditEventType,
  EvaluationOutcome,
  FactType,
  FollowUpStatus,
  ReviewStatus,
  VerificationStatus,
} from '@/api'

export const REVIEW_STATUSES: ReviewStatus[] = ['pending', 'in_review', 'reviewed', 'escalated']

export const REVIEW_STATUS_LABELS: Record<ReviewStatus, string> = {
  pending: 'Pending',
  in_review: 'In Review',
  reviewed: 'Reviewed',
  escalated: 'Escalated',
}

export const FACT_TYPES: FactType[] = [
  'custody_start_date',
  'custody_end_date',
  'current_charges',
  'max_punishment',
  'max_punishment_years',
  'max_punishment_source',
  'death_or_life_punishment',
  'other_pending_cases',
  'exception_flags',
  'accused_caused_delay_days',
]

export const FACT_LABELS: Record<FactType, string> = {
  custody_start_date: 'Custody Start Date',
  custody_end_date: 'Custody End Date',
  current_charges: 'Current Charges',
  max_punishment: 'Maximum Punishment',
  max_punishment_years: 'Maximum Punishment — Years',
  max_punishment_source: 'Maximum Punishment — Source',
  death_or_life_punishment: 'Death or Life Imprisonment?',
  other_pending_cases: 'Other Pending Cases',
  exception_flags: 'Exception Flags',
  accused_caused_delay_days: 'Accused-Caused Delay (days)',
}

export const FACT_STATUS_LABELS: Record<VerificationStatus, string> = {
  unknown: 'Unknown',
  unverified: 'Unverified',
  verified: 'Verified',
  conflict: 'Conflict',
}

export const OUTCOME_LABELS: Record<EvaluationOutcome, string> = {
  REVIEW_THRESHOLD_REACHED: 'Review Threshold Reached',
  THRESHOLD_NOT_REACHED: 'Threshold Not Reached',
  BLOCKED_MISSING_FACTS: 'Blocked — Missing Facts',
  ESCALATED_LEGAL_REVIEW: 'Escalated — Legal Review',
}

export const FOLLOWUP_STATUSES: FollowUpStatus[] = ['pending', 'in_progress', 'completed', 'cancelled']

export const FOLLOWUP_STATUS_LABELS: Record<FollowUpStatus, string> = {
  pending: 'Pending',
  in_progress: 'In Progress',
  completed: 'Completed',
  cancelled: 'Cancelled',
}

export const AUDIT_EVENT_LABELS: Record<AuditEventType, string> = {
  fact_verified: 'Fact Verified',
  fact_corrected: 'Fact Corrected',
  fact_conflict_flagged: 'Fact Conflict Flagged',
  fact_conflict_resolved: 'Fact Conflict Resolved',
  evaluation_run: 'Evaluation Run',
  case_status_changed: 'Case Status Changed',
  followup_created: 'Follow-up Created',
  followup_updated: 'Follow-up Updated',
  followup_reassigned: 'Follow-up Reassigned',
  followup_started: 'Follow-up Started',
  followup_completed: 'Follow-up Completed',
  followup_cancelled: 'Follow-up Cancelled',
}
