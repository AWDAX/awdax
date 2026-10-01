import { useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router'
import { useAuth } from '../auth/authContext.ts'
import { DatabaseIcon, LogoutIcon, PlusIcon, ReportIcon, SearchIcon, SidebarIcon } from '../../ui/appIcons.tsx'
import { buttonClass } from '../../ui/buttonClass.ts'
import { Tooltip } from '../../ui/Tooltip.tsx'
import { TourTrigger } from '../../ui/tour/TourTrigger.tsx'
import { FEATURES } from '../features.ts'
import { HistoryList } from './HistoryList.tsx'

type Props = {
  /** Hides the sidebar on desktop (the rail in Layout brings it back). */
  onCollapse: () => void
  /** Called after navigating, so the mobile drawer can close. */
  onNavigate?: () => void
}

const navClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-2.5 rounded-control px-2 py-1.5 text-small transition-colors duration-300 ease-soft focus-visible:outline-2 focus-visible:outline-ink ${
    isActive ? 'bg-signal-soft font-medium text-ink' : 'text-ink-2 hover:bg-sunken hover:text-ink'
  }`

/** ChatGPT-style sidebar: new chat, the two workspace views, searchable history, and the account. */
export function Sidebar({ onCollapse, onNavigate }: Props) {
  const [query, setQuery] = useState('')

  return (
    <div className="flex h-full w-72 flex-col border-r-2 border-ink bg-surface">
      <div className="flex h-14 shrink-0 items-center justify-between gap-2 px-4">
        <Link
          to="/"
          className="rounded-sm font-display font-wide text-h3 font-extrabold tracking-tight focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink"
        >
          AWDAX
        </Link>
        <div className="flex items-center gap-1">
          <Tooltip content="Workspace Tour" placement="bottom">
            <TourTrigger tourId="sidebar-tour" iconOnly label="Workspace Tour" />
          </Tooltip>
          <Tooltip content="Collapse" placement="bottom-end">
            <button
              type="button"
              onClick={onCollapse}
              aria-label="Close sidebar"
              className="grid size-8 place-items-center rounded-control text-ink-2 hover:bg-sunken hover:text-ink focus-visible:outline-2 focus-visible:outline-ink"
            >
              <SidebarIcon />
            </button>
          </Tooltip>
        </div>
      </div>

      <div className="flex flex-col gap-1 px-3 pb-3">
        <div data-tour="workspace-sidebar-new">
          <Link to="/app" onClick={onNavigate} className={buttonClass('primary', 'md', 'w-full justify-start')}>
            <PlusIcon /> New chat
          </Link>
        </div>
        <div className="mt-2 flex flex-col gap-0.5">
          <NavLink to="/app/projects" onClick={onNavigate} data-tour="workspace-sidebar-projects" className={navClass}>
            <ReportIcon /> Projects report
          </NavLink>
          {FEATURES.askDatabase && (
            <NavLink to="/app/ask" onClick={onNavigate} className={navClass}>
              <DatabaseIcon /> Ask database
            </NavLink>
          )}
        </div>
      </div>

      <label data-tour="workspace-sidebar-search" className="mx-3 mb-3 flex items-center gap-2 rounded-control border-2 border-line px-2.5 focus-within:border-ink">
        <SearchIcon className="shrink-0 text-ink-3" />
        <span className="sr-only">Search chats</span>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search chats"
          className="h-9 w-full min-w-0 bg-transparent text-small outline-none placeholder:text-ink-3"
        />
      </label>

      <div data-tour="workspace-sidebar-history" className="min-h-0 flex-1 overflow-y-auto pb-4" data-lenis-prevent>
        <HistoryList query={query} onNavigate={onNavigate} />
      </div>

      <Account />
    </div>
  )
}

function Account() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const meta = user?.user_metadata ?? {}
  // No user only in the agent preview (npm run dev:agent), which skips sign-in.
  const name: string = meta.full_name ?? meta.name ?? user?.email ?? 'Preview, not signed in'
  const avatar: string | undefined = meta.avatar_url ?? meta.picture

  // Leave first: once the session is gone, RequireAuth would send this page to /login instead.
  const leave = async () => {
    navigate('/', { replace: true })
    await signOut()
  }

  return (
    <div data-tour="workspace-sidebar-account" className="flex items-center gap-2.5 border-t-2 border-ink px-3 py-3">
      {avatar ? (
        <img src={avatar} alt="" width={32} height={32} referrerPolicy="no-referrer" className="size-8 shrink-0 rounded-control border-2 border-ink" />
      ) : (
        <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-control border-2 border-ink bg-signal text-small font-bold">
          {name.slice(0, 1).toUpperCase() || '?'}
        </span>
      )}
      <div className="min-w-0 flex-1 leading-tight">
        <p className="truncate text-small font-medium">{name}</p>
        {user?.email && name !== user.email && <p className="truncate text-micro text-ink-3">{user.email}</p>}
      </div>
      <button
        type="button"
        onClick={leave}
        aria-label="Sign out"
        title="Sign out"
        className="grid size-8 shrink-0 place-items-center rounded-control text-ink-2 hover:bg-sunken hover:text-ink focus-visible:outline-2 focus-visible:outline-ink"
      >
        <LogoutIcon />
      </button>
    </div>
  )
}

