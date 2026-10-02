/**
 * The commit rule behind an undo window (FuseButton, a chat row's Delete): once armed, the action runs exactly once,
 * when the fuse ends or when the control unmounts first, unless Undo came first. Pure, so it is tested without React:
 * finish() and unmount() return true exactly once while armed, and the caller then runs the action.
 */
export type FuseLatch = { arm: () => void; undo: () => void; finish: () => boolean; unmount: () => boolean }

export function createFuseLatch(): FuseLatch {
  let pending = false
  // Cleared before true is returned, so a commit that makes the control unmount cannot run itself a second time.
  const take = () => {
    const was = pending
    pending = false
    return was
  }
  return {
    arm: () => {
      pending = true
    },
    undo: () => {
      pending = false
    },
    finish: take,
    unmount: take,
  }
}
