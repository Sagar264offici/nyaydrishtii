import { useEffect, useState } from 'react'
import './App.css'
import {
  fetchCase,
  fetchCases,
  fetchMetrics,
  type Case,
  type Metrics,
  type ReviewStatus,
} from './api'

const STATUSES: ReviewStatus[] = ['pending', 'in_review', 'reviewed', 'escalated']

const STATUS_LABELS: Record<ReviewStatus, string> = {
  pending: 'Pending',
  in_review: 'In Review',
  reviewed: 'Reviewed',
  escalated: 'Escalated',
}

function formatDate(value: string | null): string {
  return value ?? '—'
}

function StatusBadge({ status }: { status: ReviewStatus }) {
  return <span className={`status-badge status-${status}`}>{STATUS_LABELS[status]}</span>
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

        {selectedCaseId ? (
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
