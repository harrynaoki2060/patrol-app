/**
 * ErrorBanner — フルワイドのエラーメッセージバナー
 */

interface ErrorBannerProps {
  message: string | null
  onDismiss?: () => void
  type?: 'error' | 'warning' | 'info'
}

const styles = {
  error:   'bg-danger-50 border-danger-200 text-danger-800',
  warning: 'bg-yellow-50 border-yellow-200 text-yellow-800',
  info:    'bg-primary-50 border-primary-200 text-primary-800',
}

const icons = {
  error:   '⚠️',
  warning: '⚠️',
  info:    'ℹ️',
}

export function ErrorBanner({ message, onDismiss, type = 'error' }: ErrorBannerProps) {
  if (!message) return null

  return (
    <div
      role="alert"
      className={`flex items-start gap-3 px-4 py-3 border rounded-xl text-sm ${styles[type]}`}
    >
      <span aria-hidden className="mt-0.5 flex-shrink-0">{icons[type]}</span>
      <span className="flex-1">{message}</span>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="flex-shrink-0 text-current opacity-60 hover:opacity-100 min-w-[44px] min-h-[44px] flex items-center justify-center -mr-2 -mt-2"
          aria-label="閉じる"
        >
          ✕
        </button>
      )}
    </div>
  )
}

/** オフライン警告バナー */
export function OfflineBanner() {
  return (
    <div
      role="alert"
      className="offline-banner fixed top-0 left-0 right-0 z-50 bg-yellow-500 text-white text-center text-sm font-medium py-2 px-4"
    >
      📡 オフラインです — 接続が回復したら自動的に保存されます
    </div>
  )
}
