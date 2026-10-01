export type TourPlacement = 'top' | 'bottom' | 'left' | 'right' | 'center' | 'auto'

export type HighlightPadding =
  | number
  | {
      top?: number
      bottom?: number
      left?: number
      right?: number
      x?: number
      y?: number
    }

export type TourStep = {
  /** Unique ID for the step */
  id: string
  /** CSS selector targeting the DOM element (e.g. `[data-tour="landing-hero"]`) */
  target: string
  /** Step headline */
  title: string
  /** Detailed plain-English explanation of the feature */
  content: string
  /** Optional badge shown in the header (e.g. "Core Engine", "Live") */
  badge?: string
  /** Optional custom step counter label (e.g. "Beginning", "Live Preview") instead of "Step X of Y" */
  stepLabel?: string
  /** Optional pro-tip or usage guideline */
  tip?: string
  /** Preferred popover position (defaults to 'auto') */
  placement?: TourPlacement
  /** Padding around the spotlight cutout in pixels or per-side object (default: 8) */
  highlightPadding?: HighlightPadding
  /** Radius for the spotlight cutout corners (default: 6) */
  spotlightRadius?: number
  /** Landing-tour only: strict explicit position for the card (bypasses auto-fallback) */
  landingCardPosition?: 'top-right' | 'bottom-right' | 'top-left' | 'bottom-left' | 'inside-bottom-right' | 'inside-top-right' | 'inside-top-center' | 'inside-center' | 'inside-right-center' | 'right-center' | 'bottom-center'
  /** Landing-tour only: manual nudge from the calculated position */
  landingCardOffset?: { x?: number; y?: number }
  /** Custom width for the card in pixels */
  cardWidth?: number
  /** Render in compact 16:9 ratio with tighter typography and padding */
  compact?: boolean
}

export type TourDefinition = {
  /** Unique ID for the tour (e.g. 'landing-tour', 'workspace-tour') */
  id: string
  /** Human-readable title */
  title: string
  /** Short description */
  description?: string
  /** Ordered list of steps */
  steps: TourStep[]
}

export type TourState = {
  /** Currently active tour definition, or null if inactive */
  tour: TourDefinition | null
  /** 0-indexed current step */
  stepIndex: number
  /** Whether the tour overlay is actively shown */
  isActive: boolean
}

export type TargetRect = {
  top: number
  left: number
  width: number
  height: number
  bottom: number
  right: number
}
