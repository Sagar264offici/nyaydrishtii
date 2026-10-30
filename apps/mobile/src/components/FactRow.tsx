import { StyleSheet, Text, View } from 'react-native'

import { Badge } from '@/components/Badge'
import { type Fact } from '@/api'
import { FACT_LABELS, FACT_STATUS_LABELS } from '@/constants'
import { colors } from '@/theme'

// Read-only on mobile -- editing/verifying a fact stays on the web admin
// dashboard. A value is always shown next to its verification status, so an
// unverified/unknown/conflict value is never mistaken for an established one.
export function FactRow({ fact }: { fact: Fact }) {
  return (
    <View style={styles.row}>
      <View style={styles.header}>
        <Text style={styles.label}>{FACT_LABELS[fact.fact_type] ?? fact.fact_type}</Text>
        <Badge label={FACT_STATUS_LABELS[fact.verification_status]} statusKey={fact.verification_status} />
      </View>
      <Text style={styles.value}>{formatFactValue(fact.value)}</Text>
      {fact.source_filename && (
        <Text style={styles.meta}>
          Source: {fact.source_filename}
          {fact.source_page ? `, p.${fact.source_page}` : ''} · via {fact.extraction_method}
        </Text>
      )}
      {fact.verification_note && <Text style={styles.note}>Note: {fact.verification_note}</Text>}
      {fact.reviewed_by && <Text style={styles.meta}>Reviewed by {fact.reviewed_by}</Text>}
    </View>
  )
}

function formatFactValue(value: Fact['value']): string {
  if (value == null) return 'Not available'
  if (Array.isArray(value)) return value.length ? value.join(', ') : '(none recorded)'
  if (typeof value === 'boolean') return value ? 'True' : 'False'
  return String(value)
}

const styles = StyleSheet.create({
  row: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    padding: 12,
    backgroundColor: colors.card,
    gap: 4,
  },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  label: { fontSize: 13, fontWeight: '600', color: colors.text, flexShrink: 1 },
  value: { fontSize: 15, color: colors.text },
  meta: { fontSize: 11, color: colors.textMuted },
  note: { fontSize: 12, color: colors.danger },
})
