import { useState } from 'react'
import { StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native'

import { createFollowUp } from '@/api'
import { colors } from '@/theme'

const PRESETS: { label: string; days: number }[] = [
  { label: '+1 day', days: 1 },
  { label: '+3 days', days: 3 },
  { label: '+1 week', days: 7 },
]

// No native date/time picker here on purpose -- Expo Go only bundles its own
// native modules, and a community date-picker would need a custom dev build
// (see apps/mobile/AGENTS.md). Quick presets fill a valid UTC timestamp
// without the user having to type one by hand; they can still edit it.
export function CreateFollowUpForm({ caseId, onCreated }: { caseId: string; onCreated: () => void }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [assignedReviewer, setAssignedReviewer] = useState('')
  const [dueAt, setDueAt] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const applyPreset = (days: number) => {
    setDueAt(new Date(Date.now() + days * 24 * 60 * 60 * 1000).toISOString())
  }

  const submit = async () => {
    if (!title.trim() || !assignedReviewer.trim() || !dueAt.trim()) {
      setError('Title, assigned reviewer, and due date are required.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await createFollowUp({
        case_id: caseId,
        title: title.trim(),
        description: description.trim() || undefined,
        assigned_reviewer: assignedReviewer.trim(),
        due_at: dueAt.trim(),
      })
      setTitle('')
      setDescription('')
      setAssignedReviewer('')
      setDueAt('')
      onCreated()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create follow-up')
    } finally {
      setSaving(false)
    }
  }

  return (
    <View style={styles.form}>
      <TextInput
        style={styles.input}
        placeholder="Title"
        placeholderTextColor={colors.textMuted}
        value={title}
        onChangeText={setTitle}
      />
      <TextInput
        style={styles.input}
        placeholder="Description (optional)"
        placeholderTextColor={colors.textMuted}
        value={description}
        onChangeText={setDescription}
      />
      <TextInput
        style={styles.input}
        placeholder="Assigned reviewer"
        placeholderTextColor={colors.textMuted}
        value={assignedReviewer}
        onChangeText={setAssignedReviewer}
        autoCapitalize="words"
      />
      <View style={styles.presetRow}>
        {PRESETS.map((p) => (
          <TouchableOpacity key={p.label} style={styles.presetChip} onPress={() => applyPreset(p.days)}>
            <Text style={styles.presetChipText}>{p.label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <TextInput
        style={styles.input}
        placeholder="Due date (ISO 8601, e.g. 2026-11-05T14:30)"
        placeholderTextColor={colors.textMuted}
        value={dueAt}
        onChangeText={setDueAt}
        autoCapitalize="none"
        autoCorrect={false}
      />
      <Text style={styles.hint}>A time with no timezone offset is treated as UTC.</Text>
      {error && <Text style={styles.error}>{error}</Text>}
      <TouchableOpacity style={[styles.submitButton, saving && styles.submitButtonDisabled]} onPress={() => void submit()} disabled={saving}>
        <Text style={styles.submitButtonText}>{saving ? 'Creating…' : 'Create Follow-up'}</Text>
      </TouchableOpacity>
    </View>
  )
}

const styles = StyleSheet.create({
  form: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    padding: 12,
    backgroundColor: colors.card,
    gap: 8,
  },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 9,
    fontSize: 14,
    color: colors.text,
  },
  presetRow: { flexDirection: 'row', gap: 8 },
  presetChip: {
    paddingVertical: 5,
    paddingHorizontal: 10,
    borderRadius: 999,
    backgroundColor: colors.background,
    borderWidth: 1,
    borderColor: colors.border,
  },
  presetChipText: { fontSize: 12, color: colors.text },
  hint: { fontSize: 11, color: colors.textMuted },
  error: { fontSize: 12, color: colors.danger },
  submitButton: {
    backgroundColor: colors.primary,
    borderRadius: 6,
    paddingVertical: 10,
    alignItems: 'center',
  },
  submitButtonDisabled: { opacity: 0.6 },
  submitButtonText: { color: '#fff', fontWeight: '700', fontSize: 14 },
})
