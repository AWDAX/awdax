import type { ReactNode } from 'react'

type TooltipProps = {
  content: ReactNode
  children: ReactNode
  placement?: 'top' | 'bottom' | 'left' | 'right' | 'bottom-end' | 'bottom-start'
  className?: string
}

/**
 * Ink-styled lightweight tooltip that reveals on hover or keyboard focus.
 */
export function Tooltip({ content, children, placement = 'bottom', className = '' }: TooltipProps) {
  const placementClass = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-1.5',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-1.5',
    'bottom-end': 'top-full right-0 mt-1.5',
    'bottom-start': 'top-full left-0 mt-1.5',
    left: 'right-full top-1/2 -translate-y-1/2 mr-1.5',
    right: 'left-full top-1/2 -translate-y-1/2 ml-1.5',
  }[placement]

  return (
    <div className={`group/tip relative inline-flex items-center ${className}`}>
      {children}
      <div
        role="tooltip"
        className={`pointer-events-none absolute z-50 whitespace-nowrap rounded-control border border-ink bg-surface px-2 py-0.5 font-mono text-micro font-medium text-ink shadow-[2px_2px_0px_var(--color-ink)] opacity-0 transition-opacity duration-150 group-hover/tip:opacity-100 group-focus-within/tip:opacity-100 ${placementClass}`}
      >
        {content}
      </div>
    </div>
  )
}
