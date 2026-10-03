// Motion's animation features, split out of the first bundle: LazyMotion (main.tsx) loads this chunk right after the
// page starts, so first paint doesn't wait on ~19 KB gzipped of animation code. A module of its own, or the
// dynamic import would stay in the main chunk (motion/react is imported statically everywhere else).
export { domMax as default } from 'motion/react'
