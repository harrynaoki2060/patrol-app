'use client'

export const dynamic = 'force-dynamic'

/**
 * /admin/pending — 承認待ち申請一覧
 *
 * - ページネーション（20件/ページ）
 * - キーワード検索（氏名・受付番号）
 * - 行ごとの承認・差戻しボタン
 * - 差戻し理由はインラインフォームで入力
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { getPendingEntries, approveEntry, rejectEntry } from '@/lib/api/entries'
import { ApiError } from '@/lib/api/client'
import { useAdminAuth } from '@/lib/context/AdminAuthContext'
import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import type { EntryListItem, PendingListResponse } from '@/types/api'

// 日時フォーマット
function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('ja-JP', {
    month: 'numeric', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

const workerTypeLabel: Record<string, string> = {
  company_employee: '協力会社社員',
  sole_proprietor:  '一人親方',
  part_time:        'アルバイト',
}

// ============================================================
// 1行コンポーネント
// ============================================================
interface EntryRowProps {
  item:       EntryListItem
  onApprove:  (id: string) => Promise<void>
  onReject:   (id: string, reason: string) => Promise<void>
  processing: string | null
}

function EntryRow({ item, onApprove, onReject, processing }: EntryRowProps) {
  const [showRejectForm, setShowRejectForm] = useState(false)
  const [rejectReason,   setRejectReason]   = useState('')
  const [rejectError,    setRejectError]    = useState<string | null>(null)

  const isProcessing = processing === item.id

  async function handleApprove() {
    await onApprove(item.id)
  }

  async function handleRejectSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!rejectReason.trim()) {
      setRejectError('差戻し理由を入力してください')
      return
    }
    await onReject(item.id, rejectReason)
    setShowRejectForm(false)
    setRejectReason('')
  }

  return (
    <div className="card border border-gray-100">
      {/* メイン情報 */}
      <div className="flex items-start gap-3 mb-3">
        <div className="w-10 h-10 rounded-full bg-primary-100 flex items-center justify-center text-lg flex-shrink-0">
          👷
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Link
              href={`/admin/entries/${item.id}`}
              className="font-semibold text-gray-900 hover:text-primary-600 hover:underline"
            >
              {item.worker.last_name} {item.worker.first_name}
            </Link>
            <span className="text-xs bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded-full font-medium">
              審査待ち
            </span>
          </div>
          {item.worker.affiliation_company && (
            <p className="text-sm text-gray-500 truncate">{item.worker.affiliation_company}</p>
          )}
          <p className="text-xs text-gray-400 mt-0.5">
            {item.site_name} ・ {formatDateTime(item.submitted_at)}
          </p>
        </div>
        <span className="text-xs text-gray-400 font-mono flex-shrink-0">
          {item.receipt_number}
        </span>
      </div>

      {/* 差戻しフォーム */}
      {showRejectForm && (
        <form onSubmit={handleRejectSubmit} className="mt-2 mb-3 space-y-2 border-t pt-3">
          <label className="form-label" htmlFor={`reject-${item.id}`}>
            差戻し理由 <span className="text-danger-600">*</span>
          </label>
          <textarea
            id={`reject-${item.id}`}
            value={rejectReason}
            onChange={e => { setRejectReason(e.target.value); setRejectError(null) }}
            placeholder="差戻し理由を入力してください（作業員に伝わる内容で）"
            rows={3}
            className={`form-input resize-none ${rejectError ? 'border-danger-500' : ''}`}
            autoFocus
          />
          {rejectError && <p role="alert" className="form-error">{rejectError}</p>}
          <div className="flex gap-2">
            <Button type="submit" variant="danger" fullWidth={false} className="flex-1" loading={isProcessing}>
              差戻しを確定
            </Button>
            <Button type="button" variant="secondary" fullWidth={false} className="flex-1"
              onClick={() => { setShowRejectForm(false); setRejectReason(''); setRejectError(null) }}>
              キャンセル
            </Button>
          </div>
        </form>
      )}

      {/* ボタン */}
      {!showRejectForm && (
        <div className="flex gap-2 border-t pt-3">
          <button
            onClick={handleApprove}
            disabled={!!processing}
            className="flex-1 min-h-[48px] bg-success-600 hover:bg-success-700 active:bg-success-800 text-white font-semibold text-sm rounded-xl flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
          >
            {isProcessing ? <Spinner size="sm" className="text-white" /> : '✓'}
            承認
          </button>
          <button
            onClick={() => setShowRejectForm(true)}
            disabled={!!processing}
            className="flex-1 min-h-[48px] bg-white hover:bg-danger-50 active:bg-danger-100 text-danger-600 border border-danger-300 font-semibold text-sm rounded-xl flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
          >
            ✕ 差戻し
          </button>
          <Link
            href={`/admin/entries/${item.id}`}
            className="min-h-[48px] min-w-[48px] bg-gray-100 hover:bg-gray-200 text-gray-600 rounded-xl flex items-center justify-center text-sm transition-colors"
            aria-label="詳細を見る"
          >
            →
          </Link>
        </div>
      )}
    </div>
  )
}

// ============================================================
// メインページ
// ============================================================
export default function AdminPendingPage() {
  const { getAccessToken, refreshIfNeeded, isAuthenticated } = useAdminAuth()
  const router = useRouter()

  const [data,       setData]       = useState<PendingListResponse | null>(null)
  const [loading,    setLoading]    = useState(true)
  const [error,      setError]      = useState<string | null>(null)
  const [page,       setPage]       = useState(1)
  const [keyword,    setKeyword]    = useState('')
  const [inputKw,    setInputKw]    = useState('')   // input の即時値
  const [processing, setProcessing] = useState<string | null>(null)
  const [actionMsg,  setActionMsg]  = useState<string | null>(null)

  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback(async (pg: number, kw: string) => {
    const token = getAccessToken()
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const res = await getPendingEntries({ page: pg, per_page: 20, keyword: kw || undefined }, token)
      setData(res)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        const newToken = await refreshIfNeeded()
        if (!newToken) { router.push('/admin/login'); return }
        const res = await getPendingEntries({ page: pg, per_page: 20, keyword: kw || undefined }, newToken)
        setData(res)
      } else {
        setError('申請一覧の取得に失敗しました')
      }
    } finally {
      setLoading(false)
    }
  }, [getAccessToken, refreshIfNeeded, router])

  useEffect(() => {
    if (isAuthenticated) void load(page, keyword)
  }, [load, page, keyword, isAuthenticated])

  // 検索デバウンス
  function handleSearchChange(v: string) {
    setInputKw(v)
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => {
      setPage(1)
      setKeyword(v)
    }, 500)
  }

  async function handleApprove(entryId: string) {
    const token = getAccessToken()
    if (!token) return
    setProcessing(entryId)
    setActionMsg(null)
    try {
      await approveEntry(entryId, {}, token)
      setActionMsg('承認しました')
      void load(page, keyword)
    } catch {
      setError('承認に失敗しました')
    } finally {
      setProcessing(null)
    }
  }

  async function handleReject(entryId: string, reason: string) {
    const token = getAccessToken()
    if (!token) return
    setProcessing(entryId)
    setActionMsg(null)
    try {
      await rejectEntry(entryId, { reason }, token)
      setActionMsg('差戻しました')
      void load(page, keyword)
    } catch {
      setError('差戻しに失敗しました')
    } finally {
      setProcessing(null)
    }
  }

  return (
    <div className="p-4 space-y-4 pb-8">
      {/* ページヘッダー */}
      <div className="pt-2">
        <h1 className="text-xl font-bold text-gray-900">承認待ち申請</h1>
        {data && (
          <p className="text-sm text-gray-500 mt-0.5">
            {data.total}件の申請があります
          </p>
        )}
      </div>

      {/* 検索 */}
      <div className="relative">
        <input
          type="search"
          value={inputKw}
          onChange={e => handleSearchChange(e.target.value)}
          placeholder="氏名・受付番号で検索..."
          className="form-input pl-10"
          aria-label="申請を検索"
        />
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">🔍</span>
      </div>

      {/* アクション結果 */}
      {actionMsg && (
        <ErrorBanner type="info" message={actionMsg} onDismiss={() => setActionMsg(null)} />
      )}
      {error && (
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
      )}

      {/* リスト */}
      {loading ? (
        <div className="flex justify-center py-12">
          <Spinner size="lg" className="text-primary-600" />
        </div>
      ) : data?.items.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <div className="text-4xl mb-3">📋</div>
          <p className="font-medium">
            {keyword ? '検索結果が見つかりません' : '審査待ちの申請はありません'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {data?.items.map(item => (
            <EntryRow
              key={item.id}
              item={item}
              onApprove={handleApprove}
              onReject={handleReject}
              processing={processing}
            />
          ))}
        </div>
      )}

      {/* ページネーション */}
      {data && data.total > 20 && (
        <div className="flex items-center justify-between pt-2">
          <Button
            variant="secondary"
            fullWidth={false}
            className="min-w-[100px]"
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1 || loading}
          >
            ← 前
          </Button>
          <span className="text-sm text-gray-500">
            {page} / {Math.ceil(data.total / 20)}ページ
          </span>
          <Button
            variant="secondary"
            fullWidth={false}
            className="min-w-[100px]"
            onClick={() => setPage(p => p + 1)}
            disabled={!data.has_next || loading}
          >
            次 →
          </Button>
        </div>
      )}
    </div>
  )
}
