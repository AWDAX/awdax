import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router'
import AuthCallback from './AuthCallback.tsx'
import { AuthProvider } from './auth/AuthProvider.tsx'
import { RequireAuth } from './auth/RequireAuth.tsx'
import ChatPage from './chat/ChatPage.tsx'
import DevelopersPage from './developers/DevelopersPage.tsx'
import DemoReplay from './demo/DemoReplay.tsx'
import FilePage from './chat/FilePage.tsx'
import NewChat from './chat/NewChat.tsx'
import LoginPage from './LoginPage.tsx'
import ProjectsReport from './report/ProjectsReport.tsx'
import Layout from './workspace/Layout.tsx'

// Dev-only preview of components and the dashboard on sample tables; Vite drops it from production builds.
const DevPreview = import.meta.env.DEV ? lazy(() => import('./dev/DevPreview.tsx')) : null

/**
 * Everything that is not the landing page, loaded as one lazy chunk so Supabase never ships with the
 * landing. /login and /auth/callback are public; /app and below need a session.
 */
export default function AppRoot() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="login" element={<LoginPage />} />
        <Route path="auth/callback" element={<AuthCallback />} />
        <Route
          path="app"
          element={
            <RequireAuth>
              <Layout />
            </RequireAuth>
          }
        >
          <Route index element={<NewChat />} />
          <Route path="c/:id" element={<ChatPage />} />
          <Route path="f/:id" element={<FilePage />} />
          <Route path="demo/:slug" element={<DemoReplay />} />
          <Route path="projects" element={<ProjectsReport />} />
          <Route path="developers" element={<DevelopersPage />} />
          {DevPreview && (
            <Route
              path="dev"
              element={
                <Suspense fallback={null}>
                  <DevPreview />
                </Suspense>
              }
            />
          )}
          <Route path="*" element={<Navigate to="/app" replace />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}
