import { CopyIcon } from '../../ui/appIcons.tsx'
import { useToast } from '../../ui/toast/toastContext.ts'

/** A snippet to copy: monospace, scrolls sideways rather than wrapping, and a button beside it copies all of it. */
export function CodeBlock({ code, label }: { code: string; label: string }) {
  const { toast } = useToast()
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      toast({ title: 'Copied', tone: 'success', duration: 2000 })
    } catch {
      toast({ title: 'Couldn’t copy', description: 'Select the text and copy it by hand.', tone: 'error' })
    }
  }
  return (
    <div className="flex items-start gap-1.5">
      <pre tabIndex={0} aria-label={label} className="min-w-0 flex-1 overflow-x-auto rounded-control border-2 border-line bg-sunken p-3 font-mono text-micro leading-relaxed">
        {code}
      </pre>
      <button
        type="button"
        onClick={() => void copy()}
        aria-label={`Copy: ${label}`}
        className="grid size-10 shrink-0 place-items-center rounded-control border-2 border-line text-ink-2 hover:border-ink hover:text-ink focus-visible:outline-2 focus-visible:outline-ink"
      >
        <CopyIcon />
      </button>
    </div>
  )
}
