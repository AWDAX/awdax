import { CompassIcon } from '../appIcons.tsx'
import { buttonClass, type ButtonVariant } from '../buttonClass.ts'
import { useTutorial } from './tutorialContext.ts'

type Props = {
  label?: string
  variant?: ButtonVariant
  iconOnly?: boolean
  className?: string
}

/** Opens the tutorial video. Icon-only for toolbars, labelled for page headers. */
export function TutorialTrigger({ label = 'Watch tutorial', variant = 'secondary', iconOnly = false, className = '' }: Props) {
  const { openTutorial } = useTutorial()

  if (iconOnly) {
    return (
      <button
        type="button"
        onClick={openTutorial}
        aria-label={label}
        title={label}
        className={`grid size-8 place-items-center rounded-control text-ink-2 hover:bg-sunken hover:text-ink focus-visible:outline-2 focus-visible:outline-ink ${className}`}
      >
        <CompassIcon className="size-4" />
      </button>
    )
  }

  return (
    <button type="button" onClick={openTutorial} className={buttonClass(variant, 'md', `gap-1.5 ${className}`)}>
      <CompassIcon className="size-4" />
      <span>{label}</span>
    </button>
  )
}
