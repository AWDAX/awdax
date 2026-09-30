export type ButtonVariant = 'primary' | 'secondary' | 'ghost'
export type ButtonSize = 'md' | 'lg'

const base =
  'inline-flex items-center justify-center gap-2 rounded-control border-2 font-semibold whitespace-nowrap select-none ' +
  // Tailwind v4 scales through the `scale` property, not `transform`.
  'transition-[background-color,border-color,color,scale] duration-300 ease-soft active:scale-97 ' +
  'disabled:pointer-events-none disabled:opacity-45 aria-busy:cursor-progress ' +
  'focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-ink'

const variants: Record<ButtonVariant, string> = {
  primary: 'border-ink bg-signal text-on-signal hover:bg-ink hover:text-signal',
  secondary: 'border-ink bg-surface text-ink hover:bg-sunken',
  ghost: 'border-transparent text-ink hover:bg-sunken',
}

const sizes: Record<ButtonSize, string> = {
  md: 'h-10 px-4 text-small',
  lg: 'h-12 px-6 text-body',
}

export function buttonClass(variant: ButtonVariant = 'primary', size: ButtonSize = 'md', extra = '') {
  return [base, variants[variant], sizes[size], extra].join(' ')
}
