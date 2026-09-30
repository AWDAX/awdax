import type { HTMLAttributes } from 'react'
import { MARK } from './markInk.ts'
import type { MarkInk } from './markInk.ts'

type Props = HTMLAttributes<HTMLSpanElement> & {
  ink?: MarkInk
  /** Drawn or not. Switching to true sweeps the fill in from the left. */
  on?: boolean
  /** Milliseconds before the sweep starts. */
  delay?: number
}

/** A highlighter stroke behind inline text. Text on it stays ink. */
export function Mark({ ink = 'yellow', on = true, delay = 0, className = '', style, ...rest }: Props) {
  return (
    <span
      {...rest}
      data-method={ink === 'yellow' ? undefined : ink}
      className={`mark ${MARK[ink]} ${on ? 'mark-on' : 'mark-off'} ${className}`}
      style={delay ? { ...style, transitionDelay: `${delay}ms` } : style}
    />
  )
}
