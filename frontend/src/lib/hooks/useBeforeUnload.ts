'use client'

/**
 * useBeforeUnload — ページ離脱前に flush を実行するフック
 *
 * 使い方:
 *   useBeforeUnload(flush, isDirty)
 *
 * isDirty=true の場合のみ beforeunload イベントに登録する。
 * flush は navigator.sendBeacon や fetch で実装される想定。
 */

import { useEffect } from 'react'

export function useBeforeUnload(
  flush: () => Promise<void> | void,
  isDirty: boolean,
) {
  useEffect(() => {
    if (!isDirty) return

    const handler = (e: BeforeUnloadEvent) => {
      // 非同期 flush は保証できないため、同期的に警告を出す
      e.preventDefault()
      e.returnValue = ''  // Chrome では文字列を設定する必要がある
      // best-effort: 非同期保存を試みる（保証はなし）
      flush()
    }

    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [flush, isDirty])
}
