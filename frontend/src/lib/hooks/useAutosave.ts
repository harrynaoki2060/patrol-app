'use client'

/**
 * useAutosave — 3秒 debounce の自動保存フック
 *
 * 使い方:
 *   const { isSaving, lastSaved, triggerSave, flush } = useAutosave({
 *     data: formData,
 *     onSave: async (data) => { await updateDraft(...) },
 *     debounceMs: 3000,
 *   })
 *
 * - triggerSave(): データ変更時に呼ぶ（3秒後に onSave が実行される）
 * - flush(): 即座に保存（ステップ遷移・ページ離脱前に使う）
 */

import { useCallback, useEffect, useRef, useState } from 'react'

export type SaveStatus = 'idle' | 'pending' | 'saving' | 'saved' | 'error'

interface UseAutosaveOptions<T> {
  data: T
  onSave: (data: T) => Promise<void>
  debounceMs?: number
  enabled?: boolean
}

interface UseAutosaveResult {
  status: SaveStatus
  lastSaved: Date | null
  triggerSave: () => void
  flush: () => Promise<void>
}

export function useAutosave<T>({
  data,
  onSave,
  debounceMs = 3000,
  enabled = true,
}: UseAutosaveOptions<T>): UseAutosaveResult {
  const [status, setStatus] = useState<SaveStatus>('idle')
  const [lastSaved, setLastSaved] = useState<Date | null>(null)

  // 最新の data と onSave を ref で保持（stale closure 防止）
  const dataRef  = useRef(data)
  const saveRef  = useRef(onSave)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const savingRef = useRef(false)

  dataRef.current = data
  saveRef.current = onSave

  const doSave = useCallback(async () => {
    if (savingRef.current || !enabled) return
    savingRef.current = true
    setStatus('saving')
    try {
      await saveRef.current(dataRef.current)
      setLastSaved(new Date())
      setStatus('saved')
    } catch {
      setStatus('error')
    } finally {
      savingRef.current = false
    }
  }, [enabled])

  const triggerSave = useCallback(() => {
    if (!enabled) return
    if (timerRef.current) clearTimeout(timerRef.current)
    setStatus('pending')
    timerRef.current = setTimeout(doSave, debounceMs)
  }, [enabled, debounceMs, doSave])

  const flush = useCallback(async () => {
    if (!enabled) return
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    await doSave()
  }, [enabled, doSave])

  // アンマウント時にタイマーをクリア
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  return { status, lastSaved, triggerSave, flush }
}
