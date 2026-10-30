import { ScrollView, StyleSheet, Text } from 'react-native'

import { colors } from '@/theme'

// Shown instead of attempting any fetch when EXPO_PUBLIC_API_BASE_URL isn't
// set -- a clear setup message beats a confusing network-error screen.
export function NotConfigured() {
  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>Backend not configured</Text>
      <Text style={styles.body}>
        Set <Text style={styles.code}>EXPO_PUBLIC_API_BASE_URL</Text> in{' '}
        <Text style={styles.code}>apps/mobile/.env.local</Text> to your development machine&apos;s
        LAN address, for example:
      </Text>
      <Text style={styles.code}>EXPO_PUBLIC_API_BASE_URL=http://192.168.1.42:8000</Text>
      <Text style={styles.body}>
        Do not use &quot;localhost&quot; — a physical device or an Android emulator cannot reach
        the development machine at that address. See the mobile README for exact steps, then
        restart the app.
      </Text>
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    padding: 20,
    backgroundColor: colors.background,
    gap: 12,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
    color: colors.text,
  },
  body: {
    fontSize: 15,
    color: colors.text,
    lineHeight: 22,
  },
  code: {
    fontFamily: 'monospace',
    fontSize: 13,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 6,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
})
