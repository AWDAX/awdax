# Credits

Everything AWDAX uses that someone else made. Every copied or adapted component gets an entry here.

## Fonts

- **Mona Sans**: GitHub, via Google Fonts (SIL OFL)
- **Geist Mono**: Vercel, via Google Fonts (SIL Open Font License 1.1)

## Libraries

- React, React DOM: Meta (MIT)
- Vite, @vitejs/plugin-react: VoidZero and contributors (MIT)
- Tailwind CSS, @tailwindcss/vite: Tailwind Labs (MIT)
- Motion: Motion Division (MIT)
- React Router: Shopify / Remix (MIT)
- Lenis: darkroom.engineering (MIT)
- Supabase JS client: Supabase (MIT)

## Design references

Direction references for "The web, highlighted", all Awwwards 2026 winners. No code, colors or assets copied.

- AI in Design Report: charts drawn in ink on paper with one accent
- Why Zero: saturated color used sparingly, for energy
- Squarespace Foundations: ink-and-paper rules, heavy black lines on white

## Components

React Bits (David Haz, MIT + Commons Clause) — `TS-TW` variants adapted from
`github.com/DavidHDev/react-bits`, `public/r/<Name>-TS-TW.json`:

- **VoicePill** — https://reactbits.dev/micro/voice-pill — `src/ui/micro/VoicePill.tsx`.
  Changed: dropped `simulated` reactivity and hold/slide-to-cancel (kept mic-reactive, tap-to-toggle);
  @hugeicons → `MicIcon`/`StopIcon` (`src/ui/appIcons.tsx`); `motion` → plain CSS transitions + a
  canvas waveform (`useMicLevel.ts`, `drawWaveform.ts`); colors → `border-ink`/`bg-signal` tokens;
  shape fixed to the rounded square (4px radius), no pill.
- **ThoughtLine** — https://reactbits.dev/micro/thought-line — `src/ui/micro/ThoughtLine.tsx`.
  Changed: @hugeicons sparkle/chevron/check → `CheckIcon`/`ChevronIcon`; text-shimmer gradient →
  an opacity pulse between `text-ink`/`text-ink-3` (`m.span`, disabled under reduced motion);
  step trace uses `text-micro`/`text-ink-3` tokens, no color mixing.
- **CallChip** — https://reactbits.dev/micro/call-chip — `src/ui/micro/CallChip.tsx`.
  Changed: @hugeicons terminal/file/search/edit/check/retry → our `appIcons.tsx`/`icons.tsx`;
  arbitrary surface/progress/done/error colors → `bg-signal-soft` (running/done wash) and
  `bg-blocked/15` (error), `border-ink`, `rounded-control`; `motion` import → imperative `animate()`
  from `motion/react` on a plain ref (allowed outside LazyMotion's strict `m.*` requirement).
- **SwipeToast** — https://reactbits.dev/micro/swipe-toast — `src/ui/toast/SwipeToast.tsx` +
  `src/ui/toast/ToastHost.tsx` + `src/ui/toast/toastContext.ts`.
  Changed: @hugeicons close → `CloseIcon`; `motion.div` → `m.div`; fixed inline positioning →
  `ToastProvider`'s own stack (bottom-right desktop, bottom mobile); background/ink/fuse hex →
  `border-ink`/`bg-surface`/`bg-signal`/`bg-blocked` tokens, `rounded-panel`; kept swipe-to-dismiss,
  pause-on-hover/focus fuse bar, and Escape-to-close.
- **BellToggle** — https://reactbits.dev/micro/bell-toggle — `src/ui/micro/BellToggle.tsx`.
  Changed: @hugeicons bell → `BellIcon`/`BellOffIcon`; dropped the crossfading off/on-label DOM
  trick and clapper/wave SVGs for a simpler swap plus an `animate()` rotate wobble; badge colors →
  `bg-signal`/`text-on-signal`, `rounded-control` (no pill); kept controlled/uncontrolled `pressed`,
  count badge and icon-only mode.
- **FuseButton** — https://reactbits.dev/micro/fuse-button — `src/ui/micro/FuseButton.tsx`.
  Changed: @hugeicons archive/undo/check → `TrashIcon`/`ReplayIcon`/`CheckIcon`; dropped the
  `outline` SVG fuse variant (kept top/bottom bar only) and settle/press CSS-variable machinery;
  fuse/ink colors → `bg-blocked` (tone="danger") / `bg-signal`, `border-ink`, `rounded-control`;
  kept press-to-arm, undo window, Escape-to-undo, and an icon-only compact variant.

ncdai (MIT) — https://21st.dev/@ncdai/components/copy-button —
`src/ui/micro/CopyButton.tsx` + `src/ui/micro/useCopyToClipboard.ts` + `src/ui/micro/IconSwap.tsx`.
Changed: lucide-react icons → `CopyIcon`/`CheckIcon`/`ErrorIcon`; shadcn `Button` → a plain
size-7 `rounded-control` ghost icon button matching `buttonClass.ts`'s hover pattern; dropped the
`@rexa-developer/tiks` and `web-haptics` dependencies from the hook (no new packages); `motion.div`
→ `m.span`.

AssistantOrb — `src/ui/micro/AssistantOrb.tsx`: our own, behaviour inspired by the OdysseyUI
avatar (blinking eyes, breathing while working); no code copied, no license to satisfy.
