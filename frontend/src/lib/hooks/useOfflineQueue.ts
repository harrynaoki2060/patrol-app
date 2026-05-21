/**
 * useOfflineQueue — オフライン時のドラフト保存キュー
 *
 * ネットワーク断絶時に autosave のペイロードを localStorage に積み、
 * オンライン復帰時に自動でリトライする。
 *
 * 使い方:
 *   const { enqueue, queueSize } = useOfflineQueue(onFlush)
 *
 *   // オフライン時に呼び出す
 *   enqueue({ entryId, updates, sessionToken })
 *
 *   // onFlush は復帰時に呼ばれる: (item) => Promise<void>
 *
 * 設計:
 *   - localStorage キー: 'offline_draft_queue'
 *   - キューは JSON 配列（最大 20 件、超えると古いものを削除）
 *   - オンライン復帰を window の 'online' イベントで検知
 *   - リトライ失敗は無視（autosave は best-effort）
 */

import { useCallback, useEffect, useRef, useState } from 'react'

const STORAGE_KEY = 'offline_draft_queue'
const MAX_QUEUE = 20

export interface OfflineDraftItem {
  id: string           // UUID（キューエントリの識別子）
  entryId: string      // 入場申請 ID
  sessionToken: string // entry_session_token
  updates: Record<string, unknown>  // DraftUpdateRequest に渡す内容
  enqueuedAt: string   // ISO 8601
}

function loadQueue(): OfflineDraftItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function saveQueue(items: OfflineDraftItem[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items))
  } catch {
    // localStorage 容量超過などは無視
  }
}

function clearQueue(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // ignore
  }
}

type FlushCallback = (item: OfflineDraftItem) => Promise<void>

export function useOfflineQueue(onFlush: FlushCallback) {
  const [queueSize, setQueueSize] = useState(0)
  const isFlushing = useRef(false)
  const onFlushRef = useRef(onFlush)
  onFlushRef.current = onFlush

  // 初期化: 現在のキューサイズを反映
  useEffect(() => {
    setQueueSize(loadQueue().length)
  }, [])

  // オンライン復帰時にフラッシュ
  const flush = useCallback(async () => {
    if (isFlushing.current) return
    isFlushing.current = true

    try {
      const queue = loadQueue()
      if (queue.length === 0) return

      for (const item of queue) {
        try {
          await onFlushRef.current(item)
        } catch {
          // ベストエフォート: 1 件失敗しても続ける
        }
      }
      clearQueue()
      setQueueSize(0)
    } finally {
      isFlushing.current = false
    }
  }, [])

  // online イベントでフラッシュ
  useEffect(() => {
    const handler = () => void flush()
    window.addEventListener('online', handler)
    return () => window.removeEventListener('online', handler)
  }, [flush])

  // キューに追加
  const enqueue = useCallback((item: Omit<OfflineDraftItem, 'id' | 'enqueuedAt'>) => {
    const queue = loadQueue()
    const newItem: OfflineDraftItem = {
      ...item,
      id: crypto.randomUUID(),
      enqueuedAt: new Date().toISOString(),
    }
    // 同じ entryId の古いエントリを差し替え（最新のみ保持）
    const filtered = queue.filter(q => q.entryId !== item.entryId)
    const next = [...filtered, newItem].slice(-MAX_QUEUE)
    saveQueue(next)
    setQueueSize(next.length)
  }, [])

  return { enqueue, queueSize, flush }
}
