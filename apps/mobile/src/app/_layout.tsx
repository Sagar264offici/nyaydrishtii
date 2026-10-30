import { Stack } from 'expo-router'
import { StatusBar } from 'expo-status-bar'

export default function RootLayout() {
  return (
    <>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: '#1d4ed8' },
          headerTintColor: '#fff',
          headerTitleStyle: { fontWeight: '600' },
          contentStyle: { backgroundColor: '#f7f7f8' },
        }}
      >
        <Stack.Screen name="index" options={{ title: 'NyayDrishti' }} />
        <Stack.Screen name="case/[caseId]" options={{ title: 'Case Details' }} />
      </Stack>
    </>
  )
}
