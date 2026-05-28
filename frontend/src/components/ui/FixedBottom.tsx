/**
 * FixedBottom — 画面下部に固定されるボタンエリア
 *
 * iPhone の Home Indicator (safe area) に対応。
 * スクロール時もボタンが常に見えるようにする。
 */

interface FixedBottomProps {
  children: React.ReactNode
  className?: string
}

export function FixedBottom({ children, className = '' }: FixedBottomProps) {
  return (
    <>
      {/* スペーサー（コンテンツが固定エリアに隠れないように） */}
      <div className="h-28" aria-hidden />

      {/* 固定エリア */}
      <div
        className={`fixed bottom-0 left-0 right-0 z-40 bg-white border-t border-gray-100 px-4 pt-3 pb-safe-bottom ${className}`}
        style={{ paddingBottom: 'max(12px, env(safe-area-inset-bottom))' }}
      >
        {children}
      </div>
    </>
  )
}
