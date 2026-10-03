import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { LazyMotion, MotionConfig, domMax } from 'motion/react'
import App from './App.tsx'
import { installChunkReload } from './ui/chunkReload.ts'
import { ErrorBoundary } from './ui/ErrorBoundary.tsx'
import { SmoothScroll } from './ui/SmoothScroll.tsx'
import './index.css'

installChunkReload(window, () => sessionStorage, Date.now, () => window.location.reload())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary scope="app">
      <BrowserRouter>
        <LazyMotion features={domMax} strict>
          <MotionConfig reducedMotion="user">
            <SmoothScroll>
              <App />
            </SmoothScroll>
          </MotionConfig>
        </LazyMotion>
      </BrowserRouter>
    </ErrorBoundary>
  </StrictMode>,
)
