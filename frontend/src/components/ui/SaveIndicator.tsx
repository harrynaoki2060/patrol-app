'use client'

import type { SaveStatus } from '@/lib/hooks/useAutosave'
import { Spinner } from './Spinner'

interface SaveIndicatorProps {
  status: SaveStatus
  lastSaved: Date | null
}

/** 自動保存の状態を示す小さなインジケーター */
export function SaveIndicator({ status, lastSaved }: SaveIndicatorProps) {
  if (status === 'idle' && !lastSaved) return null

  const timeStr = lastSaved
    ? lastSaved.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' })
    : null

  return (
    <div className="flex items-center gap-1.5 text-xs text-gray-500" aria-live="polite">
      {status === 'saving' && (
        <>
          <Spinner size="sm" className="text-gray-400" />
          <span>保存中...</span>
        </>
      )}
      {status === 'pending' && (
        <span className="text-gray-400">入力中...</span>
      )}
      {status === 'saved' && timeStr && (
        <>
          <span className="text-success-600">✓</span>
          <span>{timeStr} 保存済み</span>
        </>
      )}
      {status === 'error' && (
        <span className="text-danger-600">⚠ 保存に失敗しました</span>
      )}
    </div>
  )
}
