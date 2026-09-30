import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link } from 'react-router'
import type { LinkProps } from 'react-router'
import { buttonClass } from './buttonClass.ts'
import type { ButtonSize, ButtonVariant } from './buttonClass.ts'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  children: ReactNode
}

export function Button({
  variant,
  size,
  loading = false,
  disabled,
  type = 'button',
  className = '',
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={buttonClass(variant, size, className)}
    >
      {loading && (
        <span aria-hidden className="size-4 animate-spin rounded-full border-2 border-current border-r-transparent" />
      )}
      {children}
    </button>
  )
}

type ButtonLinkProps = LinkProps & { variant?: ButtonVariant; size?: ButtonSize }

export function ButtonLink({ variant, size, className = '', ...rest }: ButtonLinkProps) {
  return <Link {...rest} className={buttonClass(variant, size, className)} />
}
