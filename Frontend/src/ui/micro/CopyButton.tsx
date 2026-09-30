import { CopyIcon, ErrorIcon } from '../appIcons.tsx'
import { CheckIcon } from '../icons.tsx'
import { IconSwap, IconSwapItem } from './IconSwap.tsx'
import { useCopyToClipboard } from './useCopyToClipboard.ts'

export type CopyButtonProps = {
  text: string | (() => string)
  onCopySuccess?: (text: string) => void
  onCopyError?: (error: Error) => void
  label?: string
  className?: string
}

/** Ghost icon button that copies `text` and swaps its icon to a check (or an error mark). Ported
 * from ncdai/chanhdai.com's CopyButton (MIT), with hugeicons -> our icons and shadcn's Button
 * dropped for a plain ghost icon button matching buttonClass.ts. */
export function CopyButton({ text, onCopySuccess, onCopyError, label = 'Copy', className = '' }: CopyButtonProps) {
  const { state, copy } = useCopyToClipboard({ onCopySuccess, onCopyError })

  return (
    <button
      type="button"
      aria-label={label}
      onClick={() => void copy(text)}
      className={
        'inline-flex size-7 items-center justify-center rounded-control text-ink-2 transition-colors duration-300 ease-soft ' +
        'hover:bg-sunken hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink ' +
        `${state === 'error' ? 'text-blocked' : ''} ${className}`
      }
    >
      <IconSwap>
        <IconSwapItem key={state}>
          {state === 'idle' && <CopyIcon />}
          {state === 'done' && <CheckIcon />}
          {state === 'error' && <ErrorIcon />}
        </IconSwapItem>
      </IconSwap>
    </button>
  )
}
