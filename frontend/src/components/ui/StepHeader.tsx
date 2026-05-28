/**
 * StepHeader — ステップ番号 + タイトル + プログレスバー
 */

interface StepHeaderProps {
  currentStep: number
  totalSteps: number
  title: string
  subtitle?: string
}

export function StepHeader({ currentStep, totalSteps, title, subtitle }: StepHeaderProps) {
  const progress = Math.round((currentStep / totalSteps) * 100)

  return (
    <div className="px-4 pt-4 pb-2">
      {/* プログレスバー */}
      <div className="flex items-center gap-2 mb-3">
        <div className="flex-1 bg-gray-200 rounded-full h-1.5" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
          <div
            className="bg-primary-600 h-1.5 rounded-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
        <span className="text-xs text-gray-500 flex-shrink-0">
          {currentStep}/{totalSteps}
        </span>
      </div>

      {/* タイトル */}
      <h1 className="text-xl font-bold text-gray-900">{title}</h1>
      {subtitle && (
        <p className="text-sm text-gray-500 mt-0.5">{subtitle}</p>
      )}
    </div>
  )
}
