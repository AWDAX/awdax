import { useSyncExternalStore } from 'react'

// supabase-js keeps the session under sb-<project-ref>-auth-token. Reading that key tells the landing
// page whether someone is probably signed in, without downloading the Supabase client. It is only a
// hint for what the nav shows: /app itself asks Supabase to confirm the session (AuthProvider).
const KEY = (() => {
  try {
    return `sb-${new URL(import.meta.env.VITE_SUPABASE_URL).hostname.split('.')[0]}-auth-token`
  } catch {
    return null
  }
})()

const read = () => {
  if (!KEY) return false
  try {
    return localStorage.getItem(KEY) !== null
  } catch {
    return false
  }
}

// Other tabs signing in or out fire `storage`; this tab re-reads on every render anyway.
const subscribe = (onChange: () => void) => {
  window.addEventListener('storage', onChange)
  return () => window.removeEventListener('storage', onChange)
}

export function useSignedInHint(): boolean {
  return useSyncExternalStore(subscribe, read, () => false)
}
