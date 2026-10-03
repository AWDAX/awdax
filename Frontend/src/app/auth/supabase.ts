import { AuthClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY

if (!url || !key) {
  throw new Error('VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY must be set (README, "Environment").')
}

/**
 * The one Supabase client. Only the app routes import it, so the landing page never downloads it.
 * PKCE: Google sends the visitor back to /auth/callback with a code, which is exchanged here on load.
 * Auth only: createClient also bundles the database, storage and realtime clients (~35 KB gzipped) this app never
 * uses. The URL, apikey headers and sb-<ref>-auth-token storage key are the ones createClient sets, so existing
 * sessions (and the landing's signed-in hint, useSignedInHint.ts) still find their key.
 */
export const supabase = {
  auth: new AuthClient({
    url: `${url.replace(/\/+$/, '')}/auth/v1`,
    headers: { Authorization: `Bearer ${key}`, apikey: key },
    storageKey: `sb-${new URL(url).hostname.split('.')[0]}-auth-token`,
    flowType: 'pkce',
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  }),
}
