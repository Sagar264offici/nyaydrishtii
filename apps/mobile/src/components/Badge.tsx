import { StyleSheet, Text, View } from 'react-native'

import { DEFAULT_BADGE_COLOR, statusColors } from '@/theme'

export function Badge({ label, statusKey }: { label: string; statusKey: string }) {
  const c = statusColors[statusKey] ?? DEFAULT_BADGE_COLOR
  return (
    <View style={[styles.badge, { backgroundColor: c.bg }]}>
      <Text style={[styles.text, { color: c.fg }]}>{label}</Text>
    </View>
  )
}

const styles = StyleSheet.create({
  badge: {
    paddingVertical: 3,
    paddingHorizontal: 10,
    borderRadius: 999,
    alignSelf: 'flex-start',
  },
  text: {
    fontSize: 12,
    fontWeight: '600',
  },
})
