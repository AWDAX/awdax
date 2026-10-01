import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router'
import LandingPage from './landing/LandingPage.tsx'
import { TourProvider } from './ui/tour/TourProvider.tsx'

// Sign-in and the app, with Supabase, load only when someone leaves the landing page.
const AppRoot = lazy(() => import('./app/AppRoot.tsx'))
// Public and Supabase-free, so it sits outside AppRoot (and its AuthProvider).
const PrivacyPage = lazy(() => import('./landing/PrivacyPage.tsx'))

export default function App() {
  return (
    <TourProvider>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route
          path="/privacy"
          element={
            <Suspense fallback={null}>
              <PrivacyPage />
            </Suspense>
          }
        />
        <Route
          path="*"
          element={
            <Suspense fallback={null}>
              <AppRoot />
            </Suspense>
          }
        />
      </Routes>
    </TourProvider>
  )
}

