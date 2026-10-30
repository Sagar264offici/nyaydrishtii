import { StyleSheet, Text, View } from 'react-native'

import { type AuditEvent } from '@/api'
import { AUDIT_EVENT_LABELS } from '@/constants'
import { colors } from '@/theme'

// Read-only. `actor` is a free-text label the caller supplied -- never an
// authenticated identity, since this app has no login system.
export function AuditRow({ event }: { event: AuditEvent }) {
  return (
    <View style={styles.row}>
      <View style={styles.header}>
        <Text style={styles.type}>{AUDIT_EVENT_LABELS[event.event_type]}</Text>
        <Text style={styles.time}>{new Date(event.created_at).toLocaleString()}</Text>
      </View>
      <Text style={styles.description}>{event.description}</Text>
      <Text style={styles.actor}>By: {event.actor ?? '—'}</Text>
    </View>
  )
}

const styles = StyleSheet.create({
  row: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    padding: 12,
    backgroundColor: colors.card,
    gap: 3,
  },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  type: { fontSize: 13, fontWeight: '700', color: colors.text },
  time: { fontSize: 11, color: colors.textMuted },
  description: { fontSize: 13, color: colors.text },
  actor: { fontSize: 11, color: colors.textMuted },
})
