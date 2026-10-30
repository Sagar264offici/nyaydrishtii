import { useState } from 'react'
import { ActivityIndicator, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native'

import { Badge } from '@/components/Badge'
import { patchFollowUp, type FollowUp, type FollowUpStatus } from '@/api'
import { FOLLOWUP_STATUS_LABELS } from '@/constants'
import { colors } from '@/theme'

// Mobile only changes status (start/complete/cancel) -- editing a follow-up's
// title/description/due date/assignee stays on the web admin dashboard.
export function FollowUpCard({ followUp, onChanged }: { followUp: FollowUp; onChanged: () => void }) {
  const [reviewer, setReviewer] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const terminal = followUp.status === 'completed' || followUp.status === 'cancelled'

  const changeStatus = async (status: FollowUpStatus) => {
    if ((status === 'completed' || status === 'cancelled') && !reviewer.trim()) {
      setError('Enter a reviewer name to complete or cancel this task.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const update: { status: FollowUpStatus; reviewer?: string } = { status }
      if (reviewer.trim()) update.reviewer = reviewer.trim()
      await patchFollowUp(followUp.id, update)
      setReviewer('')
      onChanged() // reload the whole case screen -- a status change also produces a new audit event
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to update this task')
    } finally {
      setSaving(false)
    }
  }

  return (
    <View style={[styles.card, followUp.is_overdue && styles.cardOverdue]}>
      <View style={styles.header}>
        <Text style={styles.title}>{followUp.title}</Text>
        <Badge label={FOLLOWUP_STATUS_LABELS[followUp.status]} statusKey={followUp.status} />
      </View>
      {followUp.description && <Text style={styles.description}>{followUp.description}</Text>}
      <Text style={styles.meta}>Reviewer: {followUp.assigned_reviewer}</Text>
      <View style={styles.dueRow}>
        <Text style={styles.meta}>Due: {new Date(followUp.due_at).toLocaleString()}</Text>
        {followUp.is_overdue && <Badge label="Overdue" statusKey="conflict" />}
      </View>
      {followUp.completed_at && (
        <Text style={styles.meta}>
          {FOLLOWUP_STATUS_LABELS[followUp.status]} by {followUp.completed_by ?? '—'} at{' '}
          {new Date(followUp.completed_at).toLocaleString()}
        </Text>
      )}

      {!terminal && (
        <View style={styles.actions}>
          <TextInput
            style={styles.reviewerInput}
            placeholder="Reviewer name"
            placeholderTextColor={colors.textMuted}
            value={reviewer}
            onChangeText={setReviewer}
            autoCapitalize="words"
          />
          <View style={styles.actionButtons}>
            {followUp.status === 'pending' && (
              <ActionButton label="Start" onPress={() => void changeStatus('in_progress')} disabled={saving} />
            )}
            {followUp.status === 'in_progress' && (
              <ActionButton
                label="Complete"
                onPress={() => void changeStatus('completed')}
                disabled={saving || !reviewer.trim()}
              />
            )}
            <ActionButton
              label="Cancel"
              onPress={() => void changeStatus('cancelled')}
              disabled={saving || !reviewer.trim()}
              danger
            />
          </View>
          {saving && <ActivityIndicator size="small" color={colors.primary} />}
          {error && <Text style={styles.error}>{error}</Text>}
        </View>
      )}
    </View>
  )
}

function ActionButton({
  label,
  onPress,
  disabled,
  danger,
}: {
  label: string
  onPress: () => void
  disabled?: boolean
  danger?: boolean
}) {
  return (
    <TouchableOpacity
      style={[styles.actionButton, danger && styles.actionButtonDanger, disabled && styles.actionButtonDisabled]}
      onPress={onPress}
      disabled={disabled}
    >
      <Text style={[styles.actionButtonText, danger && styles.actionButtonTextDanger]}>{label}</Text>
    </TouchableOpacity>
  )
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    padding: 12,
    backgroundColor: colors.card,
    gap: 6,
  },
  cardOverdue: { borderColor: colors.danger },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  title: { fontSize: 15, fontWeight: '700', color: colors.text, flexShrink: 1 },
  description: { fontSize: 13, color: colors.text },
  meta: { fontSize: 12, color: colors.textMuted },
  dueRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  actions: { gap: 8, marginTop: 4, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 8 },
  reviewerInput: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 7,
    fontSize: 13,
    color: colors.text,
  },
  actionButtons: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  actionButton: {
    paddingVertical: 7,
    paddingHorizontal: 14,
    borderRadius: 6,
    backgroundColor: colors.primary,
  },
  actionButtonDanger: { backgroundColor: '#fee2e2' },
  actionButtonDisabled: { opacity: 0.5 },
  actionButtonText: { color: '#fff', fontSize: 13, fontWeight: '600' },
  actionButtonTextDanger: { color: colors.danger },
  error: { fontSize: 12, color: colors.danger },
})
