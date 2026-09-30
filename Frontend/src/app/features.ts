/**
 * Feature flags. Each one is off for every user unless its env var is `on` at build time. Vite inlines the
 * value, so the code behind an off flag isn't reachable in the app.
 */
export const FEATURES = {
  /** Ask database (/app/ask, and its links in the sidebar and under New chat). Off while the owner decides
   * whether to keep it (2026-09-28). Turn on with VITE_FEATURE_ASK_DATABASE=on. */
  askDatabase: import.meta.env.VITE_FEATURE_ASK_DATABASE === 'on',
} as const
