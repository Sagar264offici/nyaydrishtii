import { useCallback, useState } from 'react'
import { useFocusEffect, useRouter } from 'expo-router'
import {
  ActivityIndicator,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native'

import { Badge } from '@/components/Badge'
import { NotConfigured } from '@/components/NotConfigured'
import { API_BASE_URL, fetchCases, fetchMetrics, type Case, type Metrics, type ReviewStatus } from '@/api'
import { REVIEW_STATUSES as STATUSES, REVIEW_STATUS_LABELS as STATUS_LABELS } from '@/constants'
import { colors } from '@/theme'

export default function Dashboard() {
  const router = useRouter()
  const [cases, setCases] = useState<Case[] | null>(null)
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<ReviewStatus | 'all'>('all')

  const load = useCallback(async (isRefresh: boolean) => {
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    setError(null)
    try {
      const [caseList, metricsData] = await Promise.all([fetchCases(), fetchMetrics()])
      setCases(caseList)
      setMetrics(metricsData)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard data')
    } finally {
      if (isRefresh) setRefreshing(false)
      else setLoading(false)
    }
  }, [])

  useFocusEffect(
    useCallback(() => {
      void load(false)
    }, [load]),
  )

  if (!API_BASE_URL) return <NotConfigured />

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
    <View style={styles.container}>
      <View style={styles.banner}>
        <Text style={styles.bannerText}>⚠ Synthetic Demo Data — every case is fictional</Text>
      </View>

      {loading && (
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={styles.mutedText}>Loading dashboard…</Text>
        </View>
      )}

      {error && !loading && (
        <View style={styles.centered}>
          <Text style={styles.errorText}>Couldn&apos;t load dashboard data: {error}</Text>
          <TouchableOpacity style={styles.retryButton} onPress={() => void load(false)}>
            <Text style={styles.retryButtonText}>Retry</Text>
          </TouchableOpacity>
        </View>
      )}

      {!loading && !error && cases && metrics && (
        <FlatList
          data={filteredCases}
          keyExtractor={(c) => c.case_id}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} />}
          ListHeaderComponent={
            <>
              <MetricsSummary metrics={metrics} />
              <View style={styles.toolbar}>
                <TextInput
                  style={styles.searchInput}
                  placeholder="Search case ID, reviewer, or charges…"
                  placeholderTextColor={colors.textMuted}
                  value={search}
                  onChangeText={setSearch}
                  autoCapitalize="none"
                  autoCorrect={false}
                />
                <View style={styles.filterRow}>
                  <FilterChip label="All" active={statusFilter === 'all'} onPress={() => setStatusFilter('all')} />
                  {STATUSES.map((s) => (
                    <FilterChip
                      key={s}
                      label={STATUS_LABELS[s]}
                      active={statusFilter === s}
                      onPress={() => setStatusFilter(s)}
                    />
                  ))}
                </View>
              </View>
            </>
          }
          ListEmptyComponent={
            <View style={styles.centered}>
              <Text style={styles.mutedText}>No cases match the current search and filter.</Text>
            </View>
          }
          renderItem={({ item }) => (
            <TouchableOpacity
              style={styles.caseRow}
              onPress={() => router.push({ pathname: '/case/[caseId]', params: { caseId: item.case_id } })}
            >
              <View style={styles.caseRowHeader}>
                <Text style={styles.caseId}>{item.case_id}</Text>
                <Badge label={STATUS_LABELS[item.review_status]} statusKey={item.review_status} />
              </View>
              <Text style={styles.caseMeta}>Reviewer: {item.assigned_reviewer}</Text>
              <Text style={styles.caseMeta} numberOfLines={1}>
                {item.charges.join(', ')}
              </Text>
            </TouchableOpacity>
          )}
          contentContainerStyle={styles.listContent}
        />
      )}
    </View>
  )
}

function MetricsSummary({ metrics }: { metrics: Metrics }) {
  return (
    <View style={styles.metricsRow}>
      <MetricCard value={metrics.total_cases} label="Total Cases" />
      {STATUSES.map((s) => (
        <MetricCard key={s} value={metrics.status_counts[s]} label={STATUS_LABELS[s]} />
      ))}
      <MetricCard value={metrics.overdue_follow_ups} label="Overdue Follow-ups" danger />
    </View>
  )
}

function MetricCard({ value, label, danger }: { value: number; label: string; danger?: boolean }) {
  return (
    <View style={styles.metricCard}>
      <Text style={[styles.metricValue, danger && styles.metricValueDanger]}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  )
}

function FilterChip({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <TouchableOpacity style={[styles.chip, active && styles.chipActive]} onPress={onPress}>
      <Text style={[styles.chipText, active && styles.chipTextActive]}>{label}</Text>
    </TouchableOpacity>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  banner: {
    backgroundColor: colors.warningBg,
    borderBottomWidth: 2,
    borderBottomColor: colors.warningBorder,
    paddingVertical: 8,
    paddingHorizontal: 16,
  },
  bannerText: { color: colors.warningText, fontWeight: '600', fontSize: 12, textAlign: 'center' },
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, gap: 10 },
  mutedText: { color: colors.textMuted, fontSize: 14, textAlign: 'center' },
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
  listContent: { padding: 16, gap: 10 },
  metricsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 16 },
  metricCard: {
    flexGrow: 1,
    minWidth: 90,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: 'center',
  },
  metricValue: { fontSize: 22, fontWeight: '700', color: colors.text },
  metricValueDanger: { color: colors.danger },
  metricLabel: { fontSize: 11, color: colors.textMuted, marginTop: 2, textAlign: 'center' },
  toolbar: { gap: 10, marginBottom: 14 },
  searchInput: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
    color: colors.text,
  },
  filterRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 999,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontSize: 13, color: colors.text, fontWeight: '500' },
  chipTextActive: { color: '#fff' },
  caseRow: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    padding: 14,
    gap: 4,
  },
  caseRowHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  caseId: { fontSize: 16, fontWeight: '700', color: colors.text },
  caseMeta: { fontSize: 13, color: colors.textMuted },
})
