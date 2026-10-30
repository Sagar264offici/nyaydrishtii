import { useEffect, useState } from 'react'
import './App.css'
import {
  createFollowUp,
  downloadReviewPack,
  fetchAuditLog,
  fetchCase,
  fetchCaseFollowUps,
  fetchCases,
  fetchEvaluations,
  fetchFacts,
  fetchFollowUps,
  fetchMetrics,
  patchCaseStatus,
  patchFact,
  patchFollowUp,
  runEvaluation,
  uploadDocument,
  type AuditEvent,
  type AuditEventType,
  type Case,
  type DocumentPreviewResponse,
  type Evaluation,
  type EvaluationOutcome,
  type Fact,
  type FactType,
  type FactUpdate,
  type FactValue,
  type FollowUp,
  type FollowUpStatus,
  type FollowUpUpdate,
  type Metrics,
  type ReviewStatus,
  type VerificationStatus,
} from './api'

const STATUSES: ReviewStatus[] = ['pending', 'in_review', 'reviewed', 'escalated']

const STATUS_LABELS: Record<ReviewStatus, string> = {
  pending: 'Pending',
  in_review: 'In Review',
  reviewed: 'Reviewed',
  escalated: 'Escalated',
}

const FACT_TYPES: FactType[] = [
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

const FACT_LABELS: Record<FactType, string> = {
  custody_start_date: 'Custody Start Date',
  custody_end_date: 'Custody End Date',
  current_charges: 'Current Charges',
  max_punishment: 'Maximum Punishment',
  max_punishment_years: 'Maximum Punishment — Years (for Section 479 calculation)',
  max_punishment_source: 'Maximum Punishment — Source',
  death_or_life_punishment: 'Death or Life Imprisonment Specified?',
  other_pending_cases: 'Other Pending Cases',
  exception_flags: 'Exception Flags',
  accused_caused_delay_days: 'Accused-Caused Delay (days, optional)',
}

const FACT_STATUS_LABELS: Record<VerificationStatus, string> = {
  unknown: 'Unknown',
  unverified: 'Unverified',
  verified: 'Verified',
  conflict: 'Conflict',
}

const FOLLOWUP_STATUSES: FollowUpStatus[] = ['pending', 'in_progress', 'completed', 'cancelled']

const FOLLOWUP_STATUS_LABELS: Record<FollowUpStatus, string> = {
  pending: 'Pending',
  in_progress: 'In Progress',
  completed: 'Completed',
  cancelled: 'Cancelled',
}

const DATE_FACT_TYPES = new Set<FactType>(['custody_start_date', 'custody_end_date'])
const LIST_FACT_TYPES = new Set<FactType>(['current_charges', 'other_pending_cases', 'exception_flags'])
const NUMBER_FACT_TYPES = new Set<FactType>(['max_punishment_years', 'accused_caused_delay_days'])
const BOOLEAN_FACT_TYPES = new Set<FactType>(['death_or_life_punishment'])

function formatDate(value: string | null): string {
  return value ?? '—'
}

function StatusBadge({ status }: { status: ReviewStatus }) {
  return <span className={`status-badge status-${status}`}>{STATUS_LABELS[status]}</span>
}

function FactStatusBadge({ status }: { status: VerificationStatus }) {
  return <span className={`fact-status-badge fact-status-${status}`}>{FACT_STATUS_LABELS[status]}</span>
}

function FollowUpStatusBadge({ status }: { status: FollowUpStatus }) {
  return (
    <span className={`followup-status-badge followup-status-${status}`}>{FOLLOWUP_STATUS_LABELS[status]}</span>
  )
}

function factValueToText(value: Fact['value']): string {
  if (value == null) return ''
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return String(value)
}

function textToFactValue(factType: FactType, text: string): FactValue {
  const trimmed = text.trim()
  if (LIST_FACT_TYPES.has(factType)) {
    return trimmed
      ? trimmed
          .split(',')
          .map((part) => part.trim())
          .filter(Boolean)
      : []
  }
  if (NUMBER_FACT_TYPES.has(factType)) {
    if (!trimmed) return null
    const n = Number(trimmed)
    return Number.isNaN(n) ? null : n
  }
  if (BOOLEAN_FACT_TYPES.has(factType)) {
    return trimmed === 'true' ? true : trimmed === 'false' ? false : null
  }
  return trimmed || null
}

function FactRow({
  fact,
  onSave,
}: {
  fact: Fact
  onSave: (factId: number, update: FactUpdate) => Promise<void>
}) {
  const [editing, setEditing] = useState(false)
  const [valueText, setValueText] = useState(() => factValueToText(fact.value))
  const [reviewer, setReviewer] = useState(fact.reviewed_by ?? '')
  const [note, setNote] = useState(fact.verification_note ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const startEditing = () => {
    setValueText(factValueToText(fact.value))
    setReviewer(fact.reviewed_by ?? '')
    setNote(fact.verification_note ?? '')
    setError(null)
    setEditing(true)
  }

  const save = async (status?: VerificationStatus) => {
    if (status && !reviewer.trim()) {
      setError('Enter a reviewer name before verifying or flagging this fact.')
      return
    }
    setSaving(true)
    setError(null)
    const update: FactUpdate = { value: textToFactValue(fact.fact_type, valueText) }
    if (status) update.verification_status = status
    if (reviewer.trim()) update.reviewer = reviewer.trim()
    if (note.trim()) update.verification_note = note.trim()
    try {
      await onSave(fact.id, update)
      setEditing(false)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save this fact')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={`fact-row fact-status-border-${fact.verification_status}`}>
      <div className="fact-head">
        <span className="fact-label">{FACT_LABELS[fact.fact_type]}</span>
        <FactStatusBadge status={fact.verification_status} />
      </div>

      {!editing ? (
        <>
          <div className="fact-value">
            {fact.value == null ? (
              <em>Unknown — not found in any uploaded document</em>
            ) : (
              factValueToText(fact.value)
            )}
          </div>
          <div className="fact-meta">
            {fact.source_filename ? (
              <span>
                Source: {fact.source_filename}
                {fact.source_page ? `, p.${fact.source_page}` : ''} · extracted via {fact.extraction_method}
              </span>
            ) : (
              <span>No source document yet</span>
            )}
            {fact.reviewed_by && <span> · Reviewed by {fact.reviewed_by}</span>}
          </div>
          {fact.verification_note && <div className="fact-note">Note: {fact.verification_note}</div>}
          <button className="fact-edit-button" onClick={startEditing}>
            Edit / Verify
          </button>
        </>
      ) : (
        <div className="fact-editor">
          {DATE_FACT_TYPES.has(fact.fact_type) ? (
            <input
              type="date"
              value={valueText}
              onChange={(e) => setValueText(e.target.value)}
              aria-label={`${FACT_LABELS[fact.fact_type]} value`}
            />
          ) : BOOLEAN_FACT_TYPES.has(fact.fact_type) ? (
            <select
              value={valueText}
              onChange={(e) => setValueText(e.target.value)}
              aria-label={`${FACT_LABELS[fact.fact_type]} value`}
            >
              <option value="">— unset —</option>
              <option value="true">True</option>
              <option value="false">False</option>
            </select>
          ) : NUMBER_FACT_TYPES.has(fact.fact_type) ? (
            <input
              type="number"
              step="any"
              min="0"
              value={valueText}
              onChange={(e) => setValueText(e.target.value)}
              aria-label={`${FACT_LABELS[fact.fact_type]} value`}
            />
          ) : (
            <input
              type="text"
              value={valueText}
              onChange={(e) => setValueText(e.target.value)}
              placeholder={LIST_FACT_TYPES.has(fact.fact_type) ? 'Comma-separated values' : 'Value'}
              aria-label={`${FACT_LABELS[fact.fact_type]} value`}
            />
          )}
          <input
            type="text"
            value={reviewer}
            onChange={(e) => setReviewer(e.target.value)}
            placeholder="Reviewer name"
            aria-label="Reviewer name"
          />
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Verification note (optional)"
            aria-label="Verification note"
          />
          {error && <p className="fact-error">{error}</p>}
          <div className="fact-editor-actions">
            <button disabled={saving} onClick={() => save()}>
              Save
            </button>
            <button disabled={saving} onClick={() => save('verified')}>
              Mark Verified
            </button>
            <button disabled={saving} onClick={() => save('conflict')}>
              Flag Conflict
            </button>
            <button disabled={saving} onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function DocumentFacts({ caseId }: { caseId: string }) {
  const [facts, setFacts] = useState<Fact[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadResult, setUploadResult] = useState<DocumentPreviewResponse | null>(null)

  const load = () => {
    setLoading(true)
    setError(null)
    fetchFacts(caseId)
      .then(setFacts)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Failed to load facts'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    // caseId only — load() is recreated each render but shouldn't retrigger the effect
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId])

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setUploading(true)
    setUploadError(null)
    setUploadResult(null)
    try {
      const result = await uploadDocument(caseId, file)
      setUploadResult(result)
      setFacts(result.facts)
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const handleFactSave = async (factId: number, update: FactUpdate) => {
    const updated = await patchFact(caseId, factId, update)
    setFacts((prev) => (prev ? prev.map((f) => (f.id === updated.id ? updated : f)) : prev))
  }

  return (
    <div className="document-facts">
      <h2>Document Upload &amp; Extracted Facts</h2>

      <div className="upload-box">
        <label className="upload-label">
          Upload a case PDF to extract candidate facts (synthetic documents only — never real records)
          <input
            type="file"
            accept="application/pdf"
            onChange={(e) => void handleFileChange(e)}
            disabled={uploading}
          />
        </label>
        {uploading && <p className="status-message">Uploading and extracting…</p>}
        {uploadError && <p className="status-message status-error">{uploadError}</p>}
        {uploadResult && (
          <p className="upload-summary">
            Extracted {uploadResult.page_count} page(s) from &quot;{uploadResult.filename}&quot; via{' '}
            {uploadResult.extraction_method}.{uploadResult.message ? ` ${uploadResult.message}` : ''}
          </p>
        )}
      </div>

      {loading && <p className="status-message">Loading facts…</p>}

      {error && !loading && (
        <div className="status-message status-error">
          <p>Couldn&apos;t load facts: {error}</p>
          <button onClick={load}>Retry</button>
        </div>
      )}

      {!loading && !error && facts && facts.length === 0 && (
        <p className="status-message">No document has been uploaded for this case yet.</p>
      )}

      {!loading && !error && facts && facts.length > 0 && (
        <div className="fact-list">
          {FACT_TYPES.map((ft) => {
            const fact = facts.find((f) => f.fact_type === ft)
            return fact ? <FactRow key={fact.id} fact={fact} onSave={handleFactSave} /> : null
          })}
        </div>
      )}
    </div>
  )
}

const OUTCOME_LABELS: Record<EvaluationOutcome, string> = {
  REVIEW_THRESHOLD_REACHED: 'Review Threshold Reached',
  THRESHOLD_NOT_REACHED: 'Threshold Not Reached',
  BLOCKED_MISSING_FACTS: 'Blocked — Missing Facts',
  ESCALATED_LEGAL_REVIEW: 'Escalated — Legal Review',
}

function outcomeSlug(outcome: EvaluationOutcome): string {
  return outcome.toLowerCase().replace(/_/g, '-')
}

function EvaluationCard({ evaluation }: { evaluation: Evaluation }) {
  return (
    <div className={`evaluation-card outcome-border-${outcomeSlug(evaluation.outcome)}`}>
      <div className="evaluation-head">
        <span className={`outcome-badge outcome-${outcomeSlug(evaluation.outcome)}`}>
          {OUTCOME_LABELS[evaluation.outcome]}
        </span>
        <span className="evaluation-meta">
          {new Date(evaluation.created_at).toLocaleString()} · by {evaluation.reviewer} · rules{' '}
          {evaluation.rule_version}
        </span>
      </div>

      <p className="evaluation-explanation">{evaluation.explanation}</p>

      {evaluation.blockers.length > 0 && (
        <ul className="evaluation-reasons evaluation-blockers">
          {evaluation.blockers.map((b, i) => (
            <li key={i}>{b}</li>
          ))}
        </ul>
      )}

      {evaluation.escalation_reasons.length > 0 && (
        <ul className="evaluation-reasons evaluation-escalations">
          {evaluation.escalation_reasons.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}

      {Object.keys(evaluation.calculation).length > 0 && (
        <dl className="evaluation-calc">
          {Object.entries(evaluation.calculation).map(([k, v]) => (
            <div key={k}>
              <dt>{k.replace(/_/g, ' ')}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      )}

      <details className="evaluation-trace">
        <summary>Rule trace &amp; statutory source</summary>
        <ol>
          {evaluation.trace.map((t, i) => (
            <li key={i}>
              <strong>{t.rule}</strong> ({t.result}): {t.detail}
            </li>
          ))}
        </ol>
        <p className="evaluation-source">
          {evaluation.statutory_source.act}, Section {evaluation.statutory_source.section} —{' '}
          &quot;{evaluation.statutory_source.title}&quot; (effective{' '}
          {evaluation.statutory_source.effective_date})
          {!evaluation.statutory_source.verified_against_gazette &&
            ' — not yet verified against the official Gazette text; pending legal review.'}
        </p>
      </details>
    </div>
  )
}

function CaseEvaluations({ caseId }: { caseId: string }) {
  const [evaluations, setEvaluations] = useState<Evaluation[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reviewer, setReviewer] = useState('')
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    setError(null)
    fetchEvaluations(caseId)
      .then(setEvaluations)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Failed to load evaluations'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    // caseId only — load() is recreated each render but shouldn't retrigger the effect
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId])

  const handleRun = async () => {
    if (!reviewer.trim()) {
      setRunError('Enter a reviewer name before running an evaluation.')
      return
    }
    setRunning(true)
    setRunError(null)
    try {
      const result = await runEvaluation(caseId, reviewer.trim())
      setEvaluations((prev) => [result, ...(prev ?? [])])
    } catch (err: unknown) {
      setRunError(err instanceof Error ? err.message : 'Evaluation failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="case-evaluations">
      <h2>Section 479 BNSS Evaluation</h2>
      <p className="evaluation-disclaimer">
        Internal review-status flag only — never a bail/release decision or a guarantee of any
        legal outcome. Requires every critical fact above to be reviewer-verified first.
      </p>

      <div className="evaluation-run-box">
        <input
          type="text"
          value={reviewer}
          onChange={(e) => setReviewer(e.target.value)}
          placeholder="Reviewer name"
          aria-label="Reviewer name for evaluation"
        />
        <button disabled={running} onClick={() => void handleRun()}>
          {running ? 'Running…' : 'Run Evaluation'}
        </button>
      </div>
      {runError && <p className="status-message status-error">{runError}</p>}

      {loading && <p className="status-message">Loading evaluation history…</p>}

      {error && !loading && (
        <div className="status-message status-error">
          <p>Couldn&apos;t load evaluations: {error}</p>
          <button onClick={load}>Retry</button>
        </div>
      )}

      {!loading && !error && evaluations && evaluations.length === 0 && (
        <p className="status-message">No evaluation has been run for this case yet.</p>
      )}

      {!loading && !error && evaluations && evaluations.length > 0 && (
        <div className="evaluation-history">
          {evaluations.map((ev) => (
            <EvaluationCard key={ev.id} evaluation={ev} />
          ))}
        </div>
      )}
    </div>
  )
}

function MetricsSummary({ metrics }: { metrics: Metrics }) {
  return (
    <div className="metrics-row">
      <div className="metric-card">
        <span className="metric-value">{metrics.total_cases}</span>
        <span className="metric-label">Total Cases</span>
      </div>
      {STATUSES.map((s) => (
        <div className="metric-card" key={s}>
          <span className="metric-value">{metrics.status_counts[s]}</span>
          <span className="metric-label">{STATUS_LABELS[s]}</span>
        </div>
      ))}
      <div className="metric-card metric-overdue">
        <span className="metric-value">{metrics.overdue_follow_ups}</span>
        <span className="metric-label">Overdue Follow-ups</span>
      </div>
      {FOLLOWUP_STATUSES.map((s) => (
        <div className="metric-card" key={s}>
          <span className="metric-value">{metrics.follow_up_status_counts[s]}</span>
          <span className="metric-label">{FOLLOWUP_STATUS_LABELS[s]} Follow-ups</span>
        </div>
      ))}
    </div>
  )
}

function ReviewPackDownload({ caseId }: { caseId: string }) {
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleDownload = async () => {
    setDownloading(true)
    setError(null)
    try {
      const blob = await downloadReviewPack(caseId)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `NyayDrishti-ReviewPack-${caseId}.pdf`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to generate the review pack')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="review-pack-download">
      <button disabled={downloading} onClick={() => void handleDownload()}>
        {downloading ? 'Generating…' : 'Download Counsel Review Pack'}
      </button>
      {error && <p className="status-message status-error">{error}</p>}
    </div>
  )
}

function FollowUpRow({
  followUp,
  showCaseId,
  onUpdate,
}: {
  followUp: FollowUp
  showCaseId: boolean
  onUpdate: (updated: FollowUp) => void
}) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(followUp.title)
  const [description, setDescription] = useState(followUp.description ?? '')
  const [assignedReviewer, setAssignedReviewer] = useState(followUp.assigned_reviewer)
  const [dueAt, setDueAt] = useState(followUp.due_at.slice(0, 16))
  const [saving, setSaving] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)

  const [actionReviewer, setActionReviewer] = useState('')
  const [actionSaving, setActionSaving] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const startEditing = () => {
    setTitle(followUp.title)
    setDescription(followUp.description ?? '')
    setAssignedReviewer(followUp.assigned_reviewer)
    setDueAt(followUp.due_at.slice(0, 16))
    setEditError(null)
    setEditing(true)
  }

  const saveEdit = async () => {
    if (!title.trim() || !assignedReviewer.trim() || !dueAt) {
      setEditError('Title, assigned reviewer, and due date are required.')
      return
    }
    setSaving(true)
    setEditError(null)
    try {
      const updated = await patchFollowUp(followUp.id, {
        title: title.trim(),
        description: description.trim() || null,
        assigned_reviewer: assignedReviewer.trim(),
        due_at: dueAt,
      })
      onUpdate(updated)
      setEditing(false)
    } catch (err: unknown) {
      setEditError(err instanceof Error ? err.message : 'Failed to save this follow-up')
    } finally {
      setSaving(false)
    }
  }

  const changeStatus = async (status: FollowUpStatus) => {
    if ((status === 'completed' || status === 'cancelled') && !actionReviewer.trim()) {
      setActionError('Enter a reviewer name to complete or cancel this follow-up.')
      return
    }
    setActionSaving(true)
    setActionError(null)
    try {
      const update: FollowUpUpdate = { status }
      if (actionReviewer.trim()) update.reviewer = actionReviewer.trim()
      const updated = await patchFollowUp(followUp.id, update)
      onUpdate(updated)
      setActionReviewer('')
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Failed to update this follow-up')
    } finally {
      setActionSaving(false)
    }
  }

  const terminal = followUp.status === 'completed' || followUp.status === 'cancelled'

  return (
    <div className={`followup-row followup-status-border-${followUp.status}`}>
      <div className="followup-head">
        {showCaseId && <span className="followup-case-badge">{followUp.case_id}</span>}
        <span className="followup-title">{followUp.title}</span>
        <FollowUpStatusBadge status={followUp.status} />
      </div>

      {!editing ? (
        <>
          {followUp.description && <p className="followup-description">{followUp.description}</p>}
          <div className="followup-meta">
            <span>Reviewer: {followUp.assigned_reviewer}</span>
            <span>Due: {new Date(followUp.due_at).toLocaleString()}</span>
            {followUp.completed_at && (
              <span>
                {FOLLOWUP_STATUS_LABELS[followUp.status]} by {followUp.completed_by ?? '—'} at{' '}
                {new Date(followUp.completed_at).toLocaleString()}
              </span>
            )}
          </div>

          {!terminal && (
            <div className="followup-actions">
              <input
                type="text"
                value={actionReviewer}
                onChange={(e) => setActionReviewer(e.target.value)}
                placeholder="Reviewer name"
                aria-label="Reviewer name for status change"
              />
              {followUp.status === 'pending' && (
                <button disabled={actionSaving} onClick={() => void changeStatus('in_progress')}>
                  Start
                </button>
              )}
              {followUp.status === 'in_progress' && (
                <button
                  disabled={actionSaving || !actionReviewer.trim()}
                  onClick={() => void changeStatus('completed')}
                >
                  Complete
                </button>
              )}
              <button
                disabled={actionSaving || !actionReviewer.trim()}
                onClick={() => void changeStatus('cancelled')}
              >
                Cancel
              </button>
            </div>
          )}
          {actionError && <p className="followup-error">{actionError}</p>}

          <button className="followup-edit-button" onClick={startEditing}>
            Edit
          </button>
        </>
      ) : (
        <div className="followup-editor">
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title"
            aria-label="Title"
          />
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description (optional)"
            aria-label="Description"
          />
          <input
            type="text"
            value={assignedReviewer}
            onChange={(e) => setAssignedReviewer(e.target.value)}
            placeholder="Assigned reviewer"
            aria-label="Assigned reviewer"
          />
          <input
            type="datetime-local"
            value={dueAt}
            onChange={(e) => setDueAt(e.target.value)}
            aria-label="Due date"
          />
          {editError && <p className="followup-error">{editError}</p>}
          <div className="followup-editor-actions">
            <button disabled={saving} onClick={() => void saveEdit()}>
              Save
            </button>
            <button disabled={saving} onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function FollowUpSection({
  title,
  followUps,
  showCaseId,
  onUpdate,
}: {
  title: string
  followUps: FollowUp[]
  showCaseId: boolean
  onUpdate: (updated: FollowUp) => void
}) {
  return (
    <div className="followup-section">
      <h3>
        {title} <span className="followup-section-count">({followUps.length})</span>
      </h3>
      {followUps.length === 0 ? (
        <p className="followup-section-empty">None</p>
      ) : (
        <div className="followup-list">
          {followUps.map((f) => (
            <FollowUpRow key={f.id} followUp={f} showCaseId={showCaseId} onUpdate={onUpdate} />
          ))}
        </div>
      )}
    </div>
  )
}

function FollowUpGroups({
  followUps,
  showCaseId,
  onUpdate,
}: {
  followUps: FollowUp[]
  showCaseId: boolean
  onUpdate: (updated: FollowUp) => void
}) {
  const overdue = followUps.filter((f) => f.is_overdue)
  const upcoming = followUps.filter((f) => !f.is_overdue && (f.status === 'pending' || f.status === 'in_progress'))
  const completed = followUps.filter((f) => f.status === 'completed' || f.status === 'cancelled')

  return (
    <div className="followup-groups">
      <FollowUpSection title="Overdue" followUps={overdue} showCaseId={showCaseId} onUpdate={onUpdate} />
      <FollowUpSection title="Upcoming" followUps={upcoming} showCaseId={showCaseId} onUpdate={onUpdate} />
      <FollowUpSection title="Completed" followUps={completed} showCaseId={showCaseId} onUpdate={onUpdate} />
    </div>
  )
}

function FollowUpCreateForm({
  caseId,
  onCreated,
}: {
  caseId?: string
  onCreated: (created: FollowUp) => void
}) {
  const [targetCaseId, setTargetCaseId] = useState('')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [assignedReviewer, setAssignedReviewer] = useState('')
  const [dueAt, setDueAt] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    const effectiveCaseId = caseId ?? targetCaseId.trim()
    if (!effectiveCaseId || !title.trim() || !assignedReviewer.trim() || !dueAt) {
      setError('Case ID, title, assigned reviewer, and due date are required.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const created = await createFollowUp({
        case_id: effectiveCaseId,
        title: title.trim(),
        description: description.trim() || undefined,
        assigned_reviewer: assignedReviewer.trim(),
        due_at: dueAt,
      })
      onCreated(created)
      setTitle('')
      setDescription('')
      setAssignedReviewer('')
      setDueAt('')
      if (!caseId) setTargetCaseId('')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create follow-up')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="followup-create-form">
      {!caseId && (
        <input
          type="text"
          value={targetCaseId}
          onChange={(e) => setTargetCaseId(e.target.value)}
          placeholder="Case ID"
          aria-label="Case ID"
        />
      )}
      <input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Title"
        aria-label="Title"
      />
      <input
        type="text"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Description (optional)"
        aria-label="Description"
      />
      <input
        type="text"
        value={assignedReviewer}
        onChange={(e) => setAssignedReviewer(e.target.value)}
        placeholder="Assigned reviewer"
        aria-label="Assigned reviewer"
      />
      <input type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} aria-label="Due date" />
      {error && <p className="followup-error">{error}</p>}
      <button disabled={saving} onClick={() => void submit()}>
        {saving ? 'Creating…' : 'Create Follow-up'}
      </button>
    </div>
  )
}

function FollowUpsView() {
  const [followUps, setFollowUps] = useState<FollowUp[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<FollowUpStatus | 'all'>('all')
  const [reviewerFilter, setReviewerFilter] = useState('')
  const [showCreate, setShowCreate] = useState(false)

  const load = () => {
    setLoading(true)
    setError(null)
    fetchFollowUps(statusFilter === 'all' ? {} : { status: statusFilter })
      .then(setFollowUps)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Failed to load follow-ups'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    // statusFilter only — load() is recreated each render but shouldn't retrigger the effect
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter])

  // Reload from the server (rather than patching local state in place) so a
  // status change or a new follow-up is correctly dropped from -- or kept
  // out of -- the list when it no longer matches the active server-side
  // status filter (e.g. starting a task while filtered to "pending" only).
  const handleUpdate = () => {
    load()
  }

  const handleCreated = () => {
    setShowCreate(false)
    load()
  }

  const filtered = (followUps ?? []).filter((f) => {
    const needle = reviewerFilter.trim().toLowerCase()
    if (!needle) return true
    return f.assigned_reviewer.toLowerCase().includes(needle)
  })

  const systemWideEmpty =
    followUps !== null && followUps.length === 0 && statusFilter === 'all' && reviewerFilter.trim() === ''

  return (
    <div className="followups-view">
      {loading && <p className="status-message">Loading follow-ups…</p>}

      {error && !loading && (
        <div className="status-message status-error">
          <p>Couldn&apos;t load follow-ups: {error}</p>
          <button onClick={load}>Retry</button>
        </div>
      )}

      {!loading && !error && followUps && (
        <>
          <div className="toolbar">
            <select
              className="status-filter"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as FollowUpStatus | 'all')}
              aria-label="Filter by follow-up status"
            >
              <option value="all">All statuses</option>
              {FOLLOWUP_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {FOLLOWUP_STATUS_LABELS[s]}
                </option>
              ))}
            </select>
            <input
              type="text"
              className="search-input"
              value={reviewerFilter}
              onChange={(e) => setReviewerFilter(e.target.value)}
              placeholder="Filter by reviewer…"
              aria-label="Filter by reviewer"
            />
            <button onClick={() => setShowCreate((v) => !v)}>{showCreate ? 'Cancel' : 'Create Follow-up'}</button>
          </div>

          {showCreate && <FollowUpCreateForm onCreated={handleCreated} />}

          {systemWideEmpty ? (
            <p className="status-message">No follow-ups have been created yet.</p>
          ) : (
            <FollowUpGroups followUps={filtered} showCaseId={true} onUpdate={handleUpdate} />
          )}
        </>
      )}
    </div>
  )
}

function CaseFollowUps({ caseId }: { caseId: string }) {
  const [followUps, setFollowUps] = useState<FollowUp[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)

  const load = () => {
    setLoading(true)
    setError(null)
    fetchCaseFollowUps(caseId)
      .then(setFollowUps)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Failed to load follow-ups'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    // caseId only — load() is recreated each render but shouldn't retrigger the effect
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId])

  const handleUpdate = (updated: FollowUp) => {
    setFollowUps((prev) => (prev ? prev.map((f) => (f.id === updated.id ? updated : f)) : prev))
  }

  const handleCreated = (created: FollowUp) => {
    setFollowUps((prev) => (prev ? [created, ...prev] : [created]))
    setShowCreate(false)
  }

  return (
    <div className="case-followups">
      <h2>Follow-up Tasks</h2>

      {loading && <p className="status-message">Loading follow-ups…</p>}

      {error && !loading && (
        <div className="status-message status-error">
          <p>Couldn&apos;t load follow-ups: {error}</p>
          <button onClick={load}>Retry</button>
        </div>
      )}

      {!loading && !error && followUps && (
        <>
          <button onClick={() => setShowCreate((v) => !v)}>{showCreate ? 'Cancel' : 'Create Follow-up'}</button>
          {showCreate && <FollowUpCreateForm caseId={caseId} onCreated={handleCreated} />}

          {followUps.length === 0 ? (
            <p className="status-message">No follow-ups for this case yet.</p>
          ) : (
            <FollowUpGroups followUps={followUps} showCaseId={false} onUpdate={handleUpdate} />
          )}
        </>
      )}
    </div>
  )
}

const AUDIT_EVENT_LABELS: Record<AuditEventType, string> = {
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

function CaseAuditLog({ caseId }: { caseId: string }) {
  const [events, setEvents] = useState<AuditEvent[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    setError(null)
    fetchAuditLog(caseId, 20)
      .then((data) =>
        setEvents([...data].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())),
      )
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Failed to load audit log'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    // caseId only — load() is recreated each render but shouldn't retrigger the effect
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId])

  return (
    <div className="case-audit-log">
      <h2>Audit History</h2>

      {loading && <p className="status-message">Loading audit log…</p>}

      {error && !loading && (
        <div className="status-message status-error">
          <p>Couldn&apos;t load audit log: {error}</p>
          <button onClick={load}>Retry</button>
        </div>
      )}

      {!loading && !error && events && events.length === 0 && (
        <p className="status-message">No audit events yet for this case.</p>
      )}

      {!loading && !error && events && events.length > 0 && (
        <div className="table-scroll">
          <table className="audit-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Event</th>
                <th>Actor</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev) => (
                <tr key={ev.id}>
                  <td data-label="Timestamp">{new Date(ev.created_at).toLocaleString()}</td>
                  <td data-label="Event">{AUDIT_EVENT_LABELS[ev.event_type]}</td>
                  <td data-label="Actor">{ev.actor ?? '—'}</td>
                  <td data-label="Description">
                    {ev.description}
                    {(ev.before ?? ev.after) && (
                      <details className="audit-details">
                        <summary>Before / after</summary>
                        {ev.before && <pre>{JSON.stringify(ev.before, null, 2)}</pre>}
                        {ev.after && <pre>{JSON.stringify(ev.after, null, 2)}</pre>}
                      </details>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function CaseStatusControl({
  caseId,
  status,
  onChange,
}: {
  caseId: string
  status: ReviewStatus
  onChange: (updated: Case) => void
}) {
  const [newStatus, setNewStatus] = useState<ReviewStatus>(status)
  const [reviewer, setReviewer] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const save = async () => {
    if (!reviewer.trim()) {
      setError('Enter a reviewer name before saving.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const updated = await patchCaseStatus(caseId, newStatus, reviewer.trim())
      onChange(updated)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to update status')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="case-status-control">
      <select value={newStatus} onChange={(e) => setNewStatus(e.target.value as ReviewStatus)} aria-label="New review status">
        {STATUSES.map((s) => (
          <option key={s} value={s}>
            {STATUS_LABELS[s]}
          </option>
        ))}
      </select>
      <input
        type="text"
        value={reviewer}
        onChange={(e) => setReviewer(e.target.value)}
        placeholder="Reviewer name"
        aria-label="Reviewer name for status change"
      />
      <button disabled={saving || !reviewer.trim()} onClick={() => void save()}>
        {saving ? 'Saving…' : 'Save'}
      </button>
      {error && <p className="followup-error">{error}</p>}
    </div>
  )
}

function CaseDetails({ caseId, onBack }: { caseId: string; onBack: () => void }) {
  const [detail, setDetail] = useState<Case | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchCase(caseId)
      .then((c) => {
        if (!cancelled) setDetail(c)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load case')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [caseId])

  return (
    <div className="case-details">
      <button className="back-button" onClick={onBack}>
        ← Back to case list
      </button>

      {loading && <p className="status-message">Loading case…</p>}

      {error && !loading && (
        <div className="status-message status-error">
          <p>Couldn&apos;t load case &quot;{caseId}&quot;: {error}</p>
        </div>
      )}

      {detail && !loading && !error && (
        <dl className="detail-grid">
          <div>
            <dt>Case ID</dt>
            <dd>{detail.case_id}</dd>
          </div>
          <div>
            <dt>Review Status</dt>
            <dd>
              <StatusBadge status={detail.review_status} />
              <CaseStatusControl caseId={caseId} status={detail.review_status} onChange={setDetail} />
            </dd>
          </div>
          <div>
            <dt>Assigned Reviewer</dt>
            <dd>{detail.assigned_reviewer}</dd>
          </div>
          <div>
            <dt>Custody Start Date</dt>
            <dd>{formatDate(detail.custody_start_date)}</dd>
          </div>
          <div>
            <dt>Custody End Date</dt>
            <dd>{formatDate(detail.custody_end_date)}</dd>
          </div>
          <div>
            <dt>Next Follow-up</dt>
            <dd>{formatDate(detail.next_follow_up)}</dd>
          </div>
          <div className="detail-span">
            <dt>Charges</dt>
            <dd>{detail.charges.join(', ')}</dd>
          </div>
        </dl>
      )}

      {detail && !loading && !error && (
        <>
          <ReviewPackDownload caseId={caseId} />
          <DocumentFacts caseId={caseId} />
          <CaseEvaluations caseId={caseId} />
          <CaseFollowUps caseId={caseId} />
          <CaseAuditLog caseId={caseId} />
        </>
      )}
    </div>
  )
}

function App() {
  const [cases, setCases] = useState<Case[] | null>(null)
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<ReviewStatus | 'all'>('all')
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null)
  const [topView, setTopView] = useState<'cases' | 'followups'>('cases')

  const load = () => {
    setLoading(true)
    setError(null)
    Promise.all([fetchCases(), fetchMetrics()])
      .then(([caseList, metricsData]) => {
        setCases(caseList)
        setMetrics(metricsData)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Failed to load dashboard data')
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [])

  const filteredCases = (cases ?? []).filter((c) => {
    if (statusFilter !== 'all' && c.review_status !== statusFilter) return false
    const needle = search.trim().toLowerCase()
    if (!needle) return true
    return (
      c.case_id.toLowerCase().includes(needle) ||
      c.assigned_reviewer.toLowerCase().includes(needle) ||
      c.charges.some((charge) => charge.toLowerCase().includes(needle))
    )
  })

  return (
    <>
      <div className="demo-banner" role="status">
        ⚠ Synthetic Demo Data — every case below is fictional, for demonstration only
      </div>

      <section id="dashboard">
        <header className="dashboard-header">
          <h1>NyayDrishti Admin Dashboard</h1>
          <p>Legal case review — MVP</p>
        </header>

        <div className="view-tabs">
          <button className={topView === 'cases' ? 'active' : ''} onClick={() => setTopView('cases')}>
            Cases
          </button>
          <button className={topView === 'followups' ? 'active' : ''} onClick={() => setTopView('followups')}>
            Follow-ups
          </button>
        </div>

        {topView === 'followups' ? (
          <FollowUpsView />
        ) : selectedCaseId ? (
          <CaseDetails caseId={selectedCaseId} onBack={() => setSelectedCaseId(null)} />
        ) : (
          <>
            {loading && <p className="status-message">Loading dashboard…</p>}

            {error && !loading && (
              <div className="status-message status-error">
                <p>Couldn&apos;t load dashboard data: {error}</p>
                <button onClick={load}>Retry</button>
              </div>
            )}

            {!loading && !error && cases && metrics && (
              <>
                <MetricsSummary metrics={metrics} />

                <div className="toolbar">
                  <input
                    type="search"
                    className="search-input"
                    placeholder="Search case ID, reviewer, or charges…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    aria-label="Search cases"
                  />
                  <select
                    className="status-filter"
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value as ReviewStatus | 'all')}
                    aria-label="Filter by review status"
                  >
                    <option value="all">All statuses</option>
                    {STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {STATUS_LABELS[s]}
                      </option>
                    ))}
                  </select>
                </div>

                {filteredCases.length === 0 ? (
                  <p className="status-message">No cases match the current search and filter.</p>
                ) : (
                  <div className="table-scroll">
                    <table className="case-table">
                      <thead>
                        <tr>
                          <th>Case ID</th>
                          <th>Status</th>
                          <th>Reviewer</th>
                          <th>Charges</th>
                          <th>Custody Start</th>
                          <th>Next Follow-up</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredCases.map((c) => (
                          <tr
                            key={c.case_id}
                            tabIndex={0}
                            onClick={() => setSelectedCaseId(c.case_id)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') setSelectedCaseId(c.case_id)
                            }}
                          >
                            <td data-label="Case ID">{c.case_id}</td>
                            <td data-label="Status">
                              <StatusBadge status={c.review_status} />
                            </td>
                            <td data-label="Reviewer">{c.assigned_reviewer}</td>
                            <td data-label="Charges">{c.charges.join(', ')}</td>
                            <td data-label="Custody Start">{formatDate(c.custody_start_date)}</td>
                            <td data-label="Next Follow-up">{formatDate(c.next_follow_up)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </section>
    </>
  )
}

export default App
