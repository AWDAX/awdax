import { CompassIcon } from '../appIcons.tsx'
import { buttonClass, type ButtonVariant } from '../buttonClass.ts'
import { useTour } from './tourContext.ts'

type Props = {
  tourId: string
  label?: string
  variant?: ButtonVariant
  iconOnly?: boolean
  className?: string
}

export function TourTrigger({
  tourId,
  label = 'Take a Tour',
  variant = 'secondary',
  iconOnly = false,
  className = '',
}: Props) {
  const { startTour, isActive } = useTour()

  if (iconOnly) {
    return (
      <button
        type="button"
        onClick={() => startTour(tourId)}
        disabled={isActive}
        aria-label={label}
        title={label}
        className={`grid size-8 place-items-center rounded-control border-2 border-line text-ink-2 hover:border-ink hover:bg-sunken hover:text-ink focus-visible:outline-2 focus-visible:outline-ink ${className}`}
      >
        <CompassIcon className="size-4" />
      </button>
    )
  }

  return (
    <button
      type="button"
      onClick={() => startTour(tourId)}
      disabled={isActive}
      className={buttonClass(variant, 'md', `gap-1.5 ${className}`)}
    >
      <CompassIcon className="size-4" />
      <span>{label}</span>
    </button>
  )
}
