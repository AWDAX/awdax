import { useEffect, useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router'
import { InstancesProvider } from '../../api/InstancesProvider.tsx'
import { MenuIcon, PlusIcon, SidebarIcon } from '../../ui/appIcons.tsx'
import { ErrorBoundary } from '../../ui/ErrorBoundary.tsx'
import { ToastProvider } from '../../ui/toast/ToastHost.tsx'
import { Tooltip } from '../../ui/Tooltip.tsx'
import { TutorialProvider } from '../../ui/tutorial/TutorialProvider.tsx'
import { TutorialTrigger } from '../../ui/tutorial/TutorialTrigger.tsx'
import { useMediaQuery } from '../../ui/useMediaQuery.ts'
import { Sidebar } from './Sidebar.tsx'


const COLLAPSED_KEY = 'awdax.sidebar.collapsed'

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === '1'
  } catch {
    return false
  }
}

/**
 * The signed-in workspace: a sidebar with chat history beside the page. The app owns its own scroll areas,
 * so the root is a fixed full-height frame and Lenis leaves it alone (data-lenis-prevent).
 */
export default function Layout() {
  const wide = useMediaQuery('(min-width: 768px)')
  const [collapsed, setCollapsed] = useState(readCollapsed)
  const [drawer, setDrawer] = useState(false)
  const { pathname } = useLocation()

  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSED_KEY, collapsed ? '1' : '0')
    } catch {
      // storage blocked: the sidebar just forgets
    }
  }, [collapsed])

  // Escape closes the mobile drawer.
  useEffect(() => {
    if (!drawer) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setDrawer(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [drawer])

  const showSidebar = wide && !collapsed
  // The bar with "Open sidebar" shows whenever the sidebar doesn't: collapsed on desktop, always on phones.
  const bar = !showSidebar
  const slide = 'duration-500 ease-soft motion-reduce:transition-none'

  return (
    <InstancesProvider>
      <ToastProvider>
      <TutorialProvider>
      {/* `relative` on the frame and on <main> matters: screen-reader-only copies of charts (sr-only, absolute)
          would otherwise position against the page, not the scroll area they sit in, and make the whole page
          scroll: a second scrollbar, and a scrollIntoView sliding the app up over blank space. */}
      <div className="relative flex h-dvh overflow-hidden bg-canvas text-ink" data-lenis-prevent>
        {/* Desktop: the sidebar stays mounted and its column slides shut, so opening and closing glide
            instead of snapping. `inert` keeps a closed sidebar out of the tab order. */}
        {wide && (
          <div inert={collapsed} className={`h-full shrink-0 overflow-hidden transition-[width] ${slide} ${collapsed ? 'w-0' : 'w-72'}`}>
            <div className={`h-full w-72 transition-[translate,opacity] ${slide} ${collapsed ? '-translate-x-8 opacity-0' : 'translate-x-0 opacity-100'}`}>
              <Sidebar onCollapse={() => setCollapsed(true)} />
            </div>
          </div>
        )}

        {/* Phones: a drawer that slides in over a fading scrim. */}
        {!wide && (
          <div inert={!drawer} className={`fixed inset-0 z-40 flex ${drawer ? '' : 'pointer-events-none'}`} role="dialog" aria-modal="true" aria-label="Chats">
            <div className={`h-full transition-transform ${slide} ${drawer ? 'translate-x-0' : '-translate-x-full'}`}>
              <Sidebar onCollapse={() => setDrawer(false)} onNavigate={() => setDrawer(false)} />
            </div>
            <button type="button" aria-label="Close menu" className={`flex-1 bg-ink/40 transition-opacity ${slide} ${drawer ? 'opacity-100' : 'opacity-0'}`} onClick={() => setDrawer(false)} />
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col">
          <div
            inert={!bar}
            className={`relative z-20 flex shrink-0 items-center justify-between gap-1 border-ink px-3 transition-[height,border-bottom-width,opacity] ${slide} ${
              bar ? 'h-14 border-b-2 opacity-100 overflow-visible' : 'h-0 border-b-0 opacity-0 overflow-hidden pointer-events-none'
            }`}
          >
            <div className="flex items-center gap-1">
              <Tooltip content={wide ? 'Expand' : 'Open menu'} placement="bottom">
                <button
                  type="button"
                  onClick={() => (wide ? setCollapsed(false) : setDrawer(true))}
                  aria-label="Open sidebar"
                  className="grid size-9 place-items-center rounded-control hover:bg-sunken focus-visible:outline-2 focus-visible:outline-ink"
                >
                  {wide ? <SidebarIcon /> : <MenuIcon />}
                </button>
              </Tooltip>
              <Tooltip content="New chat" placement="bottom">
                <Link
                  to="/app"
                  aria-label="New chat"
                  className="grid size-9 place-items-center rounded-control hover:bg-sunken focus-visible:outline-2 focus-visible:outline-ink"
                >
                  <PlusIcon />
                </Link>
              </Tooltip>
              <span className="ml-2 font-display font-wide text-body font-extrabold">AWDAX</span>
            </div>
            <Tooltip content="Watch tutorial" placement="bottom-end">
              <TutorialTrigger iconOnly label="Watch tutorial" className="size-9" />
            </Tooltip>
          </div>
          {/* Keyed by path so each chat and view starts at the top with fresh state. */}
          <main id="main" key={pathname} className="relative min-h-0 flex-1 overflow-y-auto">
            <ErrorBoundary scope="page" resetKey={pathname}>
              <Outlet />
            </ErrorBoundary>
          </main>

        </div>
      </div>
      </TutorialProvider>
      </ToastProvider>
    </InstancesProvider>
  )
}
