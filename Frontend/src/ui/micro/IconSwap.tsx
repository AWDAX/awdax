import type { ComponentProps } from 'react'
import { AnimatePresence, m } from 'motion/react'

// Ported from ncdai/chanhdai.com's icon-swap (MIT). motion.div -> m.div (LazyMotion strict).
export function IconSwap(props: ComponentProps<typeof AnimatePresence>) {
  return <AnimatePresence mode="popLayout" initial={false} {...props} />
}

export function IconSwapItem(props: ComponentProps<typeof m.span>) {
  return (
    <m.span
      initial={{ opacity: 0, scale: 0.25, filter: 'blur(4px)' }}
      animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
      exit={{ opacity: 0, scale: 0.25, filter: 'blur(4px)' }}
      transition={{ type: 'spring', duration: 0.3, bounce: 0 }}
      className="inline-flex"
      {...props}
    />
  )
}
