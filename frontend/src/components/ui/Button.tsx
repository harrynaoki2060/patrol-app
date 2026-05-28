import { Spinner } from './Spinner'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost'
  loading?: boolean
  fullWidth?: boolean
  children: React.ReactNode
}

const variants = {
  primary:   'btn-primary',
  secondary: 'btn-secondary',
  danger:    'btn-danger',
  ghost:     'w-full min-h-[56px] px-6 py-4 text-primary-600 text-base font-semibold rounded-xl transition-colors duration-150 hover:bg-primary-50 active:bg-primary-100 flex items-center justify-center gap-2',
}

export function Button({
  variant = 'primary',
  loading = false,
  fullWidth = true,
  className = '',
  disabled,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={`${variants[variant]} ${fullWidth ? '' : 'w-auto'} ${className}`}
    >
      {loading && <Spinner size="sm" className="text-current" />}
      {children}
    </button>
  )
}
