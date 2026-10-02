import { useCallback, useEffect, useRef, useState } from 'react'
import { BellIcon, BellOffIcon, CompassIcon, MoreIcon, TrashIcon } from '../../ui/appIcons.tsx'
import { CheckIcon, PauseIcon, PlayIcon } from '../../ui/icons.tsx'
import { Popover } from '../../ui/Popover.tsx'
import { Tooltip } from '../../ui/Tooltip.tsx'
import { useTutorial } from '../../ui/tutorial/tutorialContext.ts'
import { useFocusTrap } from '../../ui/useFocusTrap.ts'

type Props = {
  watched: boolean
  onWatch: (on: boolean) => void
  liveEnabled: boolean
  switching: boolean
  onLive: (enabled: boolean) => void
  onDelete: () => void
}

const CONFIRM_MS = 4000
const item =
  'flex w-full items-center gap-2.5 rounded-control px-2.5 py-2 text-left text-small transition-colors duration-200 ease-soft hover:bg-sunken focus-visible:bg-sunken focus-visible:outline-none disabled:opacity-40'

/**
 * A chat's commands in one ⋯ menu instead of a row of buttons: the tutorial, row alerts, pause/resume and delete.
 * Delete asks twice (the item turns into "Click again to delete" for CONFIRM_MS), so closing the menu or a stray
 * click never deletes. The menu pattern is copied from dashboard/TileMenu.tsx (Popover + useFocusTrap).
 */
export function ChatMenu({ watched, onWatch, liveEnabled, switching, onLive, onDelete }: Props) {
  const [open, setOpen] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const anchor = useRef<HTMLButtonElement>(null)
  const menu = useFocusTrap<HTMLDivElement>(open, { arrows: true })
  const { openTutorial } = useTutorial()
  const close = useCallback(() => {
    setOpen(false)
    setConfirming(false)
  }, [])

  // An armed delete disarms itself after a moment.
  useEffect(() => {
    if (!confirming) return undefined
    const t = window.setTimeout(() => setConfirming(false), CONFIRM_MS)
    return () => window.clearTimeout(t)
  }, [confirming])

  const run = (fn: () => void) => () => {
    close()
    fn()
  }

  return (
    <>
      <Tooltip content="Chat options" placement="bottom-end">
        <button
          ref={anchor}
          type="button"
          aria-label="Chat options"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => (open ? close() : setOpen(true))}
          className="grid size-10 place-items-center rounded-control border-2 border-ink bg-surface transition-colors duration-300 ease-soft hover:bg-sunken focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-ink aria-expanded:bg-sunken"
        >
          <MoreIcon />
        </button>
      </Tooltip>
      <Popover anchor={anchor} open={open} onClose={close} boxRef={menu} role="menu" label="Chat options" className="flex w-60 flex-col p-1">
        <button role="menuitem" type="button" className={item} onClick={run(openTutorial)}>
          <CompassIcon className="shrink-0 text-ink-2" /> Watch tutorial
        </button>
        <button role="menuitemcheckbox" aria-checked={watched} type="button" className={item} onClick={run(() => onWatch(!watched))}>
          {watched ? <BellIcon className="shrink-0 text-ink-2" /> : <BellOffIcon className="shrink-0 text-ink-2" />}
          <span className="flex-1">Alert me on new rows</span>
          {watched && <CheckIcon className="shrink-0" />}
        </button>
        <button role="menuitem" type="button" className={item} disabled={switching} onClick={run(() => onLive(!liveEnabled))}>
          {liveEnabled ? <PauseIcon className="shrink-0 text-ink-2" /> : <PlayIcon className="shrink-0 text-ink-2" />}
          {liveEnabled ? 'Pause tracking' : 'Resume tracking'}
        </button>
        <div role="separator" className="my-1 h-px bg-line" />
        <button
          role="menuitem"
          type="button"
          className={`${item} ${confirming ? 'bg-blocked font-semibold text-on-ink hover:bg-blocked focus-visible:bg-blocked' : 'text-blocked hover:bg-blocked/10 focus-visible:bg-blocked/10'}`}
          onClick={confirming ? run(onDelete) : () => setConfirming(true)}
        >
          <TrashIcon className="shrink-0" /> {confirming ? 'Click again to delete' : 'Delete chat'}
        </button>
      </Popover>
    </>
  )
}
