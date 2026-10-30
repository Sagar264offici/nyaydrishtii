// Pure derivation logic, kept separate from the screens that render it.
// Mirrors the "Outstanding Issues" section of backend/review_pack.py exactly
// (missing/unverified/conflicting facts, plus the latest evaluation's own
// stored blockers/escalation reasons) -- this never recomputes anything the
// backend already computed, it only re-presents it.

import type { Evaluation, Fact } from '@/api'
import { FACT_LABELS } from '@/constants'

export function computeOutstandingIssues(facts: Fact[], latestEvaluation: Evaluation | null): string[] {
  const issues: string[] = []

  for (const fact of facts) {
    const label = FACT_LABELS[fact.fact_type] ?? fact.fact_type
    if (fact.verification_status === 'unknown') {
      issues.push(`${label}: missing — no value on record.`)
    } else if (fact.verification_status === 'unverified') {
      issues.push(`${label}: unverified — extracted but not reviewer-confirmed.`)
    } else if (fact.verification_status === 'conflict') {
      const note = fact.verification_note ? ` Note: ${fact.verification_note}` : ''
      issues.push(`${label}: flagged as conflicting by a reviewer.${note}`)
    }
  }

  if (latestEvaluation) {
    for (const blocker of latestEvaluation.blockers) issues.push(`Evaluation blocker: ${blocker}`)
    for (const reason of latestEvaluation.escalation_reasons) {
      issues.push(`Escalated for legal review: ${reason}`)
    }
  }

  return issues
}
