import { useCallback, useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { NavLink, matchPath, useMatch, useNavigate } from 'react-router'
import { useInstances } from '../../api/instancesContext.ts'
import { useToast } from '../../ui/toast/toastContext.ts'
import { EditIcon, FileIcon, MoreIcon, TrashIcon } from '../../ui/appIcons.tsx'
import { createFuseLatch } from '../../ui/micro/fuseLatch.ts'
import { Popover } from '../../ui/Popover.tsx'
import { useFocusTrap } from '../../ui/useFocusTrap.ts'
import { deleteLocal, renameLocal } from '../files/localProjects.ts'
import { isUntitled } from './groupByDay.ts'

/** A chat in the history: a web request (backend instance) or an uploaded file (kept in this browser). */
export type Entry = { id: string; title: string; updated_at: string; kind: 'web' | 'file' }

type Phase = 'idle' | 'renaming' | 'deleting'

const UNDO_MS = 4000
const item =
  'flex w-full items-center gap-2.5 rounded-control px-2.5 py-1.5 text-left text-small transition-colors duration-200 ease-soft focus-visible:outline-none'

/**
 * One chat in the sidebar, ChatGPT-style: a ⋯ menu on hover (always shown on touch screens and on the open
 * chat) with Rename and Delete. Rename edits the name in place: Enter or clicking away saves, Escape cancels.
 * Delete strikes the row through and waits UNDO_MS with an Undo button before it happens. The menu pattern is
 * copied from TileMenu (Popover + useFocusTrap).
 */
export function HistoryItem({ item: chat, onNavigate }: { item: Entry; onNavigate?: () => void }) {
  const { remove, rename } = useInstances()
  const { toast } = useToast()
  const navigate = useNavigate()
  const path = `/app/${chat.kind === 'file' ? 'f' : 'c'}/${chat.id}`
  const active = useMatch(path) !== null
  const title = isUntitled(chat.title) ? 'Untitled chat' : chat.title
  const [phase, setPhase] = useState<Phase>('idle')
  const [open, setOpen] = useState(false)
  const anchor = useRef<HTMLButtonElement>(null)
  const menu = useFocusTrap<HTMLDivElement>(open, { arrows: true })
  const input = useRef<HTMLInputElement>(null)
  const fuse = useRef<HTMLSpanElement>(null)
  const close = useCallback(() => setOpen(false), [])

  const del = async () => {
    if (matchPath(path, window.location.pathname)) navigate('/app', { replace: true })
    try {
      await (chat.kind === 'file' ? deleteLocal(chat.id) : remove(chat.id))
    } catch {
      toast({ title: 'Couldn’t delete that chat', tone: 'error' })
    }
  }

  // The latest del(), read when the fuse ends or the row unmounts. It checks the location as it runs: the user
  // may have opened another chat during the undo window, and then must not be sent back to New chat.
  const delRef = useRef(del)
  useEffect(() => {
    delRef.current = del
  })
  const [latch] = useState(createFuseLatch)

  // The undo window: a thin line burns down along the row, then the chat is deleted. The row itself is the
  // armed state (struck through, with Undo), so this is FuseButton's fuse without FuseButton's button.
  useEffect(() => {
    if (phase !== 'deleting' || !fuse.current) return undefined
    const anim = fuse.current.animate([{ transform: 'scaleX(1)' }, { transform: 'scaleX(0)' }], { duration: UNDO_MS, easing: 'linear', fill: 'forwards' })
    anim.onfinish = () => {
      if (latch.finish()) void delRef.current()
    }
    return () => anim.cancel()
  }, [phase, latch])

  // A row that moves to another day group, or is filtered out, remounts: its pending delete must still happen.
  useEffect(
    () => () => {
      if (latch.unmount()) void delRef.current()
    },
    [latch],
  )

  useEffect(() => {
    if (phase === 'renaming') input.current?.select()
  }, [phase])

  const saveName = () => {
    const next = input.current?.value.trim() ?? ''
    setPhase('idle')
    if (!next || next === title) return
    if (chat.kind === 'file') void renameLocal(chat.id, next)
    else void rename(chat.id, next).catch(() => toast({ title: 'Couldn’t rename that chat', tone: 'error' }))
  }
  const onNameKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      saveName()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setPhase('idle')
    }
  }

  if (phase === 'renaming') {
    return (
      <li>
        <label className="sr-only" htmlFor={`rename-${chat.kind}-${chat.id}`}>
          New name for {title}
        </label>
        <input
          id={`rename-${chat.kind}-${chat.id}`}
          ref={input}
          autoFocus
          defaultValue={title}
          maxLength={80}
          onKeyDown={onNameKey}
          onBlur={saveName}
          className="block w-full rounded-control border-2 border-ink bg-surface px-2 py-1 text-small text-ink outline-none"
        />
      </li>
    )
  }

  if (phase === 'deleting') {
    return (
      <li className="relative overflow-hidden rounded-control">
        <div role="status" className="flex items-center gap-2 rounded-control bg-sunken py-1.5 pr-1 pl-2 text-small">
          <span className="min-w-0 flex-1 truncate text-ink-3 line-through decoration-blocked decoration-2">{title}</span>
          <span className="sr-only">Deleting in {UNDO_MS / 1000} seconds.</span>
          <button
            type="button"
            autoFocus
            onClick={() => {
              latch.undo()
              setPhase('idle')
            }}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                latch.undo()
                setPhase('idle')
              }
            }}
            className="shrink-0 rounded-control px-2 py-0.5 text-micro font-semibold text-ink transition-colors duration-200 ease-soft hover:bg-surface focus-visible:outline-2 focus-visible:outline-ink"
          >
            Undo
          </button>
        </div>
        <span ref={fuse} aria-hidden className="absolute inset-x-0 bottom-0 h-0.5 origin-left bg-blocked" />
      </li>
    )
  }

  return (
    <li className="group relative">
      <NavLink
        to={path}
        onClick={onNavigate}
        title={title}
        className={({ isActive }) =>
          `flex items-center gap-1.5 rounded-control py-1.5 pr-9 pl-2 text-small transition-colors duration-300 ease-soft focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ink ${
            isActive ? 'bg-signal-soft font-medium text-ink' : 'text-ink-2 hover:bg-sunken hover:text-ink'
          }`
        }
      >
        {chat.kind === 'file' && <FileIcon aria-label="Uploaded file" className="shrink-0 text-ink-3" />}
        <span className="truncate">{title}</span>
      </NavLink>
      <button
        ref={anchor}
        type="button"
        aria-label={`Options for ${title}`}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className={`absolute top-1/2 right-1 grid size-7 -translate-y-1/2 place-items-center rounded-control text-ink-2 transition-[opacity,background-color,color] duration-300 ease-soft hover:bg-ink/10 hover:text-ink focus-visible:opacity-100 focus-visible:outline-2 focus-visible:outline-ink pointer-coarse:opacity-100 ${
          open || active ? 'bg-ink/10 opacity-100' : 'opacity-0 group-hover:opacity-100 group-focus-within:opacity-100'
        }`}
      >
        <MoreIcon />
      </button>
      <Popover anchor={anchor} open={open} onClose={close} boxRef={menu} role="menu" label={`Actions for ${title}`} align="start" className="flex w-44 flex-col p-1">
        <button
          role="menuitem"
          type="button"
          className={`${item} text-ink hover:bg-sunken focus-visible:bg-sunken`}
          onClick={() => {
            setOpen(false)
            setPhase('renaming')
          }}
        >
          <EditIcon className="shrink-0 text-ink-2" /> Rename
        </button>
        <button
          role="menuitem"
          type="button"
          className={`${item} text-blocked hover:bg-blocked/10 focus-visible:bg-blocked/10`}
          onClick={() => {
            setOpen(false)
            latch.arm()
            setPhase('deleting')
          }}
        >
          <TrashIcon className="shrink-0" /> Delete
        </button>
      </Popover>
    </li>
  )
}
