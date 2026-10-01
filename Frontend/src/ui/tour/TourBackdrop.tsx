import type { HighlightPadding, TargetRect } from './tourTypes.ts'

type Props = {
  rect: TargetRect | null
  settled?: boolean
  padding?: HighlightPadding
  radius?: number
  onClick?: () => void
  smoothTransition?: boolean
}

function parsePadding(p: HighlightPadding = 8) {
  if (typeof p === 'number') {
    return { top: p, bottom: p, left: p, right: p }
  }
  const x = p.x ?? 8
  const y = p.y ?? 8
  return {
    top: p.top ?? p.y ?? y,
    bottom: p.bottom ?? p.y ?? y,
    left: p.left ?? p.x ?? x,
    right: p.right ?? p.x ?? x,
  }
}

/**
 * Fullscreen SVG backdrop that dims out the background and cuts a precise spotlight around the active target.
 * Both the cutout mask and highlight outline ring are rendered in the exact same SVG coordinates,
 * ensuring 100% synchronous tracking during scroll and animations without lag.
 */
export function TourBackdrop({
  rect,
  settled = true,
  padding = 8,
  radius = 6,
  onClick,
  smoothTransition = false,
}: Props) {
  const vw = typeof window !== 'undefined' ? window.innerWidth : 1920
  const vh = typeof window !== 'undefined' ? window.innerHeight : 1080

  if (!rect) {
    return (
      <div
        onClick={onClick}
        className="fixed inset-0 z-60 bg-ink/75 transition-opacity duration-400 ease-soft"
        aria-hidden
      />
    )
  }

  const pad = parsePadding(padding)
  const left = Math.max(0, rect.left - pad.left)
  const top = Math.max(0, rect.top - pad.top)
  const width = Math.min(vw - left, rect.width + pad.left + pad.right)
  const height = Math.min(vh - top, rect.height + pad.top + pad.bottom)
  const r = Math.min(radius, width / 2, height / 2)

  return (
    <div className="fixed inset-0 z-60 pointer-events-none overflow-hidden" aria-hidden>
      {/* SVG Canvas with unified Cutout Mask and Highlight Ring */}
      <svg
        className={`pointer-events-auto size-full ${onClick ? 'cursor-pointer' : 'cursor-default'}`}
        onClick={onClick}
        viewBox={`0 0 ${vw} ${vh}`}
      >
        <defs>
          <mask id="tour-spotlight-mask">
            {/* White covers entire viewport (scrim is visible) */}
            <rect x="0" y="0" width={vw} height={vh} fill="white" />
            {/* Black cutout creates the transparent spotlight window */}
            <rect
              x={left}
              y={top}
              width={width}
              height={height}
              rx={r}
              ry={r}
              fill="black"
              className={smoothTransition ? 'transition-all duration-400 ease-soft' : undefined}
            />
          </mask>
        </defs>

        {/* Dimmed backdrop layer with cutout mask */}
        <rect
          x="0"
          y="0"
          width={vw}
          height={vh}
          fill="currentColor"
          mask="url(#tour-spotlight-mask)"
          className="text-ink/75"
        />

        {/* Glowing Highlighter Outline Ring (Rendered in lockstep with the cutout) */}
        <rect
          x={left}
          y={top}
          width={width}
          height={height}
          rx={r}
          ry={r}
          fill="none"
          stroke="var(--color-signal)"
          strokeWidth="2.5"
          className={`${
            smoothTransition ? 'transition-all duration-400 ease-soft' : 'transition-opacity duration-300 ease-soft'
          } ${settled ? 'opacity-100' : 'opacity-80'}`}
        />
      </svg>
    </div>
  )
}
