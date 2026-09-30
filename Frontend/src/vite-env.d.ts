/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** https://<project-ref>.supabase.co */
  readonly VITE_SUPABASE_URL: string
  /** sb_publishable_…: a public client key; Row Level Security protects the data. */
  readonly VITE_SUPABASE_PUBLISHABLE_KEY: string
  /** Optional AWDAX backend origin. Unset in dev: calls go to same-origin /api, which Vite proxies. */
  readonly VITE_API_BASE_URL?: string
  /** `on` shows Ask database (src/app/features.ts). Anything else, or unset, hides it. */
  readonly VITE_FEATURE_ASK_DATABASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
