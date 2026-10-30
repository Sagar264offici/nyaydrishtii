import { useCallback, useState } from 'react'
import { useFocusEffect, useLocalSearchParams } from 'expo-router'
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native'

import { AuditRow } from '@/components/AuditRow'
import { Badge } from '@/components/Badge'
import { CreateFollowUpForm } from '@/components/CreateFollowUpForm'
import { EvaluationCard } from '@/components/EvaluationCard'
import { FactRow } from '@/components/FactRow'
import { FollowUpCard } from '@/components/FollowUpCard'
import { NotConfigured } from '@/components/NotConfigured'
import {
  API_BASE_URL,
  fetchAuditLog,
  fetchCase,
  fetchCaseFollowUps,
  fetchEvaluations,
  fetchFacts,
  type AuditEvent,
  type Case,
  type Evaluation,
  type Fact,
  type FollowUp,
} from '@/api'
import { FACT_TYPES, REVIEW_STATUS_LABELS } from '@/constants'
import { colors } from '@/theme'
import { computeOutstandingIssues } from '@/utils/caseInsights'

export default function CaseDetails() {
  const { caseId } = useLocalSearchParams<{ caseId: string }>()
  const [caseData, setCaseData] = useState<Case | null>(null)
  const [facts, setFacts] = useState<Fact[]>([])
  const [evaluations, setEvaluations] = useState<Evaluation[]>([])
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([])
  const [followUps, setFollowUps] = useState<FollowUp[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreateForm, setShowCreateForm] = useState(false)

  const load = useCallback(async () => {
    if (!caseId) return
    setLoading(true)
    setError(null)
    try {
      const [caseResult, factsResult, evaluationsResult, auditResult, followUpsResult] = await Promise.all([
        fetchCase(caseId),
        fetchFacts(caseId),
        fetchEvaluations(caseId),
        fetchAuditLog(caseId, 15),
        fetchCaseFollowUps(caseId),
      ])
      setCaseData(caseResult)
      setFacts(factsResult)
      setEvaluations(evaluationsResult)
      setAuditEvents(auditResult)
      setFollowUps(followUpsResult)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load case')
    } finally {
      setLoading(false)
    }
  }, [caseId])

  useFocusEffect(
    useCallback(() => {
      void load()
    }, [load]),
  )

  if (!API_BASE_URL) return <NotConfigured />

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={styles.mutedText}>Loading case…</Text>
      </View>
    )
  }

  if (error || !caseData) {
    return (
      <View style={styles.centered}>
        <Text style={styles.errorText}>Couldn&apos;t load case &quot;{caseId}&quot;: {error}</Text>
        <TouchableOpacity style={styles.retryButton} onPress={() => void load()}>
          <Text style={styles.retryButtonText}>Retry</Text>
        </TouchableOpacity>
      </View>
    )
  }

  const latestEvaluation = evaluations[0] ?? null
  const outstandingIssues = computeOutstandingIssues(facts, latestEvaluation)
  const factsByType = new Map(facts.map((f) => [f.fact_type, f]))

  const overdue = followUps.filter((f) => f.is_overdue)
  const upcoming = followUps.filter((f) => !f.is_overdue && (f.status === 'pending' || f.status === 'in_progress'))
  const completed = followUps.filter((f) => f.status === 'completed' || f.status === 'cancelled')

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Section title="Case Overview">
        <View style={styles.overviewHeader}>
          <Text style={styles.caseId}>{caseData.case_id}</Text>
          <Badge label={REVIEW_STATUS_LABELS[caseData.review_status]} statusKey={caseData.review_status} />
        </View>
        <OverviewRow label="Assigned Reviewer" value={caseData.assigned_reviewer} />
        <OverviewRow label="Custody Start" value={caseData.custody_start_date} />
        <OverviewRow label="Custody End" value={caseData.custody_end_date ?? '—'} />
        <OverviewRow label="Charges" value={caseData.charges.join(', ')} />
        <OverviewRow label="Next Follow-up" value={caseData.next_follow_up ?? '—'} />
      </Section>

      <Section title="Outstanding Issues">
        {outstandingIssues.length === 0 ? (
          <Text style={styles.mutedText}>No outstanding issues identified from current records.</Text>
        ) : (
          <View style={styles.issuesBlock}>
            {outstandingIssues.map((issue, i) => (
              <Text key={i} style={styles.issueText}>
                • {issue}
              </Text>
            ))}
          </View>
        )}
      </Section>

      <Section title="Facts on Record">
        {facts.length === 0 ? (
          <Text style={styles.mutedText}>No document has been uploaded for this case yet.</Text>
        ) : (
          <>
            <Text style={styles.sectionHint}>
              A value next to Unverified, Unknown, or Conflict is a candidate only — never treat it
              as established.
            </Text>
            <View style={styles.cardList}>
              {FACT_TYPES.map((ft) => {
                const fact = factsByType.get(ft)
                return fact ? <FactRow key={fact.id} fact={fact} /> : null
              })}
            </View>
          </>
        )}
      </Section>

      <Section title="Legal Rule Evaluation — Section 479 BNSS">
        <EvaluationCard evaluation={latestEvaluation} />
      </Section>

      <Section title="Follow-up Tasks">
        <TouchableOpacity style={styles.toggleButton} onPress={() => setShowCreateForm((v) => !v)}>
          <Text style={styles.toggleButtonText}>{showCreateForm ? 'Cancel' : '+ Create Follow-up'}</Text>
        </TouchableOpacity>
        {showCreateForm && (
          <CreateFollowUpForm
            caseId={caseData.case_id}
            onCreated={() => {
              setShowCreateForm(false)
              void load()
            }}
          />
        )}
        <FollowUpGroup title="Overdue" items={overdue} onChanged={load} />
        <FollowUpGroup title="Upcoming" items={upcoming} onChanged={load} />
        <FollowUpGroup title="Completed" items={completed} onChanged={load} />
      </Section>

      <Section title="Audit History">
        {auditEvents.length === 0 ? (
          <Text style={styles.mutedText}>No audit events yet for this case.</Text>
        ) : (
          <View style={styles.cardList}>
            {auditEvents.map((e) => (
              <AuditRow key={e.id} event={e} />
            ))}
          </View>
        )}
      </Section>
    </ScrollView>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  )
}

function OverviewRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.overviewRow}>
      <Text style={styles.overviewLabel}>{label}</Text>
      <Text style={styles.overviewValue}>{value}</Text>
    </View>
  )
}

function FollowUpGroup({ title, items, onChanged }: { title: string; items: FollowUp[]; onChanged: () => void }) {
  return (
    <View style={styles.followUpGroup}>
      <Text style={styles.followUpGroupTitle}>
        {title} ({items.length})
      </Text>
      {items.length === 0 ? (
        <Text style={styles.mutedText}>None</Text>
      ) : (
        <View style={styles.cardList}>
          {items.map((f) => (
            <FollowUpCard key={f.id} followUp={f} onChanged={onChanged} />
          ))}
        </View>
      )}
    </View>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  content: { padding: 16, gap: 20, paddingBottom: 40 },
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, gap: 10, backgroundColor: colors.background },
  mutedText: { color: colors.textMuted, fontSize: 13 },
  errorText: { color: colors.danger, fontSize: 14, textAlign: 'center' },
  retryButton: {
    paddingVertical: 8,
    paddingHorizontal: 18,
    borderRadius: 6,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
  },
  retryButtonText: { color: colors.text, fontWeight: '600' },
  section: { gap: 10 },
  sectionTitle: { fontSize: 16, fontWeight: '700', color: colors.text },
  sectionHint: { fontSize: 12, color: colors.textMuted },
  overviewHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  caseId: { fontSize: 20, fontWeight: '800', color: colors.text },
  overviewRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 10 },
  overviewLabel: { fontSize: 13, color: colors.textMuted },
  overviewValue: { fontSize: 13, color: colors.text, fontWeight: '600', flexShrink: 1, textAlign: 'right' },
  issuesBlock: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    padding: 12,
    gap: 4,
  },
  issueText: { fontSize: 13, color: colors.text },
  cardList: { gap: 10 },
  toggleButton: {
    alignSelf: 'flex-start',
    paddingVertical: 7,
    paddingHorizontal: 14,
    borderRadius: 6,
    backgroundColor: colors.primary,
  },
  toggleButtonText: { color: '#fff', fontWeight: '600', fontSize: 13 },
  followUpGroup: { gap: 8 },
  followUpGroupTitle: { fontSize: 13, fontWeight: '700', color: colors.text },
})
