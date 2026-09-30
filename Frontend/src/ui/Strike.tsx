import type { HTMLAttributes } from 'react'

type Props = HTMLAttributes<HTMLSpanElement> & {
  /** Drawn or not. Switching to true draws the red line from the left. */
  on?: boolean
  /** Milliseconds before the line starts. */
  delay?: number
}

/** The red pen through inline text: skipped or rejected. Keep the reason next to it. */
export function Strike({ on = true, delay = 0, className = '', style, ...rest }: Props) {
  return (
    <span
      {...rest}
      className={`strike ${on ? 'strike-on' : 'strike-off'} ${className}`}
      style={delay ? { ...style, transitionDelay: `${delay}ms` } : style}
    />
  )
}
