import type { HTMLAttributes, ReactNode } from 'react'

export function Container({ className = '', children, ...rest }: HTMLAttributes<HTMLDivElement> & { className?: string; children: ReactNode }) {
  return (
    <div className={`mx-auto w-full max-w-page px-6 md:px-8 lg:px-12 ${className}`} {...rest}>
      {children}
    </div>
  )
}
