import { useState } from 'react'
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native'

import { Badge } from '@/components/Badge'
import { type Evaluation } from '@/api'
import { OUTCOME_LABELS } from '@/constants'
import { colors } from '@/theme'

// Shows only the backend's own stored evaluation -- never recomputes
// anything. This is an internal review-status flag, never a bail/release
// decision; the disclaimer below is always shown alongside it.
export function EvaluationCard({ evaluation }: { evaluation: Evaluation | null }) {
  const [showTrace, setShowTrace] = useState(false)

  if (!evaluation) {
    return (
      <View style={styles.card}>
        <Text style={styles.noEvalText}>
          No Section 479 BNSS evaluation has been performed for this case yet. Run one from the
          admin dashboard.
        </Text>
      </View>
    )
  }

  const gazetteVerified = evaluation.statutory_source.verified_against_gazette

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Badge label={OUTCOME_LABELS[evaluation.outcome]} statusKey={evaluation.outcome} />
        <Text style={styles.meta}>
          {new Date(evaluation.created_at).toLocaleString()} · {evaluation.reviewer}
        </Text>
      </View>
      <Text style={styles.ruleVersion}>Rule version: {evaluation.rule_version}</Text>
      <Text style={styles.explanation}>{evaluation.explanation}</Text>

      {evaluation.blockers.length > 0 && (
        <View style={styles.listBlock}>
          {evaluation.blockers.map((b, i) => (
            <Text key={i} style={styles.listItem}>
              • {b}
            </Text>
          ))}
        </View>
      )}
      {evaluation.escalation_reasons.length > 0 && (
        <View style={styles.listBlock}>
          {evaluation.escalation_reasons.map((r, i) => (
            <Text key={i} style={styles.listItem}>
              • {r}
            </Text>
          ))}
        </View>
      )}

      {Object.keys(evaluation.calculation).length > 0 && (
        <View style={styles.calcBlock}>
          {Object.entries(evaluation.calculation).map(([k, v]) => (
            <View key={k} style={styles.calcRow}>
              <Text style={styles.calcKey}>{k.replace(/_/g, ' ')}</Text>
              <Text style={styles.calcValue}>{String(v)}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Gazette-verification warning: always visible wherever an evaluation is shown. */}
      <View style={[styles.gazetteBanner, gazetteVerified ? styles.gazetteOk : styles.gazetteWarning]}>
        <Text style={gazetteVerified ? styles.gazetteOkText : styles.gazetteWarningText}>
          {gazetteVerified
            ? 'Statutory text verified against the official Gazette.'
            : 'NOT YET verified against the official Gazette/India Code text — pending legal review.'}
        </Text>
      </View>

      <TouchableOpacity onPress={() => setShowTrace((v) => !v)}>
        <Text style={styles.traceToggle}>{showTrace ? 'Hide rule trace ▲' : 'Show rule trace ▼'}</Text>
      </TouchableOpacity>
      {showTrace && (
        <View style={styles.traceBlock}>
          {evaluation.trace.map((t, i) => (
            <Text key={i} style={styles.traceItem}>
              <Text style={styles.traceRule}>{t.rule}</Text> ({t.result}): {t.detail}
            </Text>
          ))}
        </View>
      )}

      <Text style={styles.disclaimer}>
        Internal review-status flag only — never a bail/release decision or a guarantee of any
        legal outcome.
      </Text>
    </View>
  )
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    padding: 14,
    backgroundColor: colors.card,
    gap: 8,
  },
  noEvalText: { fontSize: 14, color: colors.danger },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 6 },
  meta: { fontSize: 11, color: colors.textMuted },
  ruleVersion: { fontSize: 11, color: colors.textMuted },
  explanation: { fontSize: 14, color: colors.text, lineHeight: 20 },
  listBlock: { gap: 2 },
  listItem: { fontSize: 13, color: colors.text },
  calcBlock: {
    backgroundColor: colors.background,
    borderRadius: 8,
    padding: 10,
    gap: 4,
  },
  calcRow: { flexDirection: 'row', justifyContent: 'space-between' },
  calcKey: { fontSize: 12, color: colors.textMuted, textTransform: 'capitalize' },
  calcValue: { fontSize: 12, color: colors.text, fontWeight: '600' },
  gazetteBanner: { borderRadius: 8, padding: 10, borderWidth: 1 },
  gazetteOk: { backgroundColor: '#dcfce7', borderColor: '#15803d' },
  gazetteOkText: { color: '#15803d', fontSize: 12, fontWeight: '600' },
  gazetteWarning: { backgroundColor: colors.warningBg, borderColor: colors.warningBorder },
  gazetteWarningText: { color: colors.warningText, fontSize: 12, fontWeight: '600' },
  traceToggle: { fontSize: 13, color: colors.primary, fontWeight: '600' },
  traceBlock: { gap: 6, paddingTop: 4 },
  traceItem: { fontSize: 12, color: colors.text, lineHeight: 17 },
  traceRule: { fontWeight: '700' },
  disclaimer: { fontSize: 11, color: colors.textMuted, fontStyle: 'italic', marginTop: 4 },
})
