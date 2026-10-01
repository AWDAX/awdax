import { CompassIcon } from '../appIcons.tsx'
import { buttonClass, type ButtonVariant } from '../buttonClass.ts'
import { useTour } from './tourContext.ts'

type Props = {
  tourId: string
  label?: string
  variant?: ButtonVariant
  iconOnly?: boolean
  bordered?: boolean
  className?: string
}

export function TourTrigger({
  tourId,
  label = 'Take a Tour',
  variant = 'secondary',
  iconOnly = false,
  bordered = false,
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
        className={`grid place-items-center rounded-control outline-none transition-[background-color,border-color,color,scale] duration-200 ease-soft active:scale-97 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink ${
          bordered
            ? 'size-10 border-2 border-ink bg-surface text-ink hover:bg-sunken'
            : 'size-8 text-ink-2 hover:bg-sunken hover:text-ink'
        } ${className}`}
      >
        <CompassIcon className={bordered ? 'size-5' : 'size-4'} />
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
