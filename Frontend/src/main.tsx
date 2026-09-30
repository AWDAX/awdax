import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { LazyMotion, MotionConfig, domAnimation } from 'motion/react'
import App from './App.tsx'
import { SmoothScroll } from './ui/SmoothScroll.tsx'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <LazyMotion features={domAnimation} strict>
        <MotionConfig reducedMotion="user">
          <SmoothScroll>
            <App />
          </SmoothScroll>
        </MotionConfig>
      </LazyMotion>
    </BrowserRouter>
  </StrictMode>,
)
