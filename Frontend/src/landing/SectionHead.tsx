import { useRef } from 'react'
import type { HTMLAttributes, ReactNode } from 'react'
import { useSeen } from '../ui/useSeen.ts'


type SectionProps = HTMLAttributes<HTMLElement> & {
  id?: string
  labelledBy: string
  /** Fill one screen below the nav on desktop and centre the content in it. Off for pinned sections. */
  fit?: boolean
  className?: string
  children: ReactNode
}

/**
 * Every landing section's frame. On desktop a fitted section is at least one screen tall (minus the
 * nav) with its content centred, so each section reads as one view. On phones it just flows.
 */
export function Section({ id, labelledBy, fit = true, className = '', children, ...rest }: SectionProps) {
  const frame = fit ? 'lg:flex lg:min-h-[calc(100dvh-4rem)] lg:flex-col lg:justify-center lg:py-8' : ''
  return (
    <section id={id} aria-labelledby={labelledBy} className={`scroll-mt-16 py-16 md:py-24 ${frame} ${className}`} {...rest}>
      {children}
    </section>
  )
}


type HeadProps = {
  id: string
  /** Two-digit section number, e.g. "02". */
  index: string
  kicker: string
  /** The headline. `seen` turns its highlight on once the heading scrolls into view. */
  title: (seen: boolean) => ReactNode
  lede?: ReactNode
  /**
   * split: headline left, lede right, bottoms aligned: short, for sections that sit below it.
   * stack: everything in one column, for a heading that lives in a side column.
   */
  layout?: 'split' | 'stack'
  className?: string
}

/** Every landing section opens the same way: a 2px ink rule, a mono number and kicker, a wide headline. */
export function SectionHead({ id, index, kicker, title, lede, layout = 'split', className = '' }: HeadProps) {
  const ref = useRef<HTMLDivElement>(null)
  const seen = useSeen(ref, 0.6)
  const split = layout === 'split'
  return (
    <div
      ref={ref}
      className={`grid gap-x-12 gap-y-5 border-t-2 border-ink pt-5 ${split ? 'lg:grid-cols-12 lg:items-end' : ''} ${className}`}
    >
      <div className={split ? 'lg:col-span-8' : ''}>
        <p className="flex items-baseline gap-3 text-small text-ink-2">
          <span className="font-mono text-micro text-ink-3">{index}</span>
          {kicker}
        </p>
        <h2 id={id} className="mt-4 max-w-[24ch] font-display font-wide text-section font-extrabold">
          {title(seen)}
        </h2>
      </div>
      {lede && <p className={`max-w-[52ch] text-lead text-ink-2 ${split ? 'lg:col-span-4 lg:pb-1' : ''}`}>{lede}</p>}
    </div>
  )
}
