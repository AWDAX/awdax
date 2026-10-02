# Spec F3: microphone and dictation lifecycle (FE-10, FE-12) + auth gate catch (N5)

Read `.agent/specs/FE-common.md` first. Files you own (only these):
`Frontend/src/ui/micro/useMicLevel.ts`, `Frontend/src/ui/micro/VoicePill.tsx`, `Frontend/src/app/voice/useSpeechToText.ts`,
new `Frontend/src/ui/micro/micSession.ts` + `micSession.test.ts`, `Frontend/src/app/auth/AuthProvider.tsx` (only the `getUser()` chain).

## 1. Mic (FE-10) — privacy bug: the mic stays on after leaving a chat, or turns on with the pill showing "off"
Causes: `VoicePill.tsx:86` mount-only cleanup closes over `listening=false` so `stop('unmount')` returns early; `useMicLevel.ts:35-37` assigns the stream after `await getUserMedia`
with no "still wanted?" check; the `AudioContext` is not closed when permission is denied.
Fix:
- Pure `micSession.ts`: a tiny start-generation helper, e.g. `createStartGuard(): { next(): number; cancel(): void; isCurrent(gen: number): boolean }` (`cancel` invalidates every outstanding gen).
- `useMicLevel`: `start()` takes `gen = guard.next()`; creates the context; awaits `getUserMedia`; if `!guard.isCurrent(gen)` (stopped, restarted or unmounted meanwhile) → stop all tracks of
  the new stream, close the context, return. On any error → close the context it created. `stop()` calls `guard.cancel()` then releases everything it holds (tracks, context, rAF) unconditionally.
  Add an unmount effect in the hook that calls `stop()`. Keep callbacks in refs so effects don't re-run each render.
- `VoicePill.tsx`: remove the stale mount-only `stop('unmount')` effect (the hook now owns cleanup). Keep the rest of the component's behaviour.
- Tests (`micSession.test.ts`): stop before grant → stale; two starts resolving in reverse → only the newest current; cancel invalidates all.

## 2. Dictation (FE-12)
`useSpeechToText.ts` `onresult`: first line `if (recognitionRef.current !== recognition) return` (same guard `onerror`/`onend` already use). On cleanup, also null the handlers
of the aborted recognizer before `abort()`.

## 3. Auth gate (N5)
`AuthProvider.tsx:46`: `supabase.auth.getUser().then(...)` has no rejection path. Add `.catch(() => { /* keep the existing session, same policy as the error branch */ })` that
sets the same "confirmed" state the error branch uses, so the "Checking your sign-in…" gate can never spin forever. Do not change any other auth behaviour.

## Done
Tests pass; eslint/tsc clean for your files. Describe how you checked (by reading) that a mic stream can no longer outlive the component.
