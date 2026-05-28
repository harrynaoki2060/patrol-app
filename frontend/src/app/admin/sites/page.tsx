'use client'

export const dynamic = 'force-dynamic'

/**
 * /admin/sites — 現場一覧
 *
 * - ロールスコープ（supervisor=担当現場のみ / admin=自社 / super_admin=全現場）
 * - カード形式で現場名・工期・QR 数・pending 申請数を表示
 * - 各カードから現場詳細へ遷移
 */

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { getSites } from '@/lib/api/sites'
import { ApiError } from '@/lib/api/client'
import { useAdminAuth } from '@/lib/context/AdminAuthContext'
import { Spinner } from '@/components/ui/Spinner'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { Button } from '@/components/ui/Button'
import type { SiteListItem, SiteListResponse } from '@/types/api'

// 日付フォーマット
function fmtDate(s: string | null): string {
  if (!s) return '—'
  const d = new Date(s)
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`
}

// 工期テキスト
function periodText(start: string | null, end: string | null): string {
  if (!start && !end) return '—'
  return `${fmtDate(start)} 〜 ${fmtDate(end)}`
}

// ============================================================
// 現場カード
// ============================================================
function SiteCard({ site }: { site: SiteListItem }) {
  const today = new Date().toISOString().slice(0, 10)
  const isEnded = site.end_date ? site.end_date < today : false

  return (
    <Link href={`/admin/sites/${site.id}`} className="block card hover:shadow-md transition-shadow">
      {/* ヘッダー行 */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <h2 className="font-bold text-gray-900 text-base leading-tight">{site.name}</h2>
          {!site.is_active || isEnded ? (
            <span className="badge-draft text-xs">終了</span>
          ) : (
            <span className="badge-approved text-xs">稼働中</span>
          )}
        </div>
        <span className="text-gray-400 text-lg flex-shrink-0">›</span>
      </div>

      {/* 詳細情報 */}
      <div className="text-sm text-gray-500 space-y-1">
        <p>📅 {periodText(site.start_date, site.end_date)}</p>
        {site.supervisor_name && (
          <p>👤 担当: {site.supervisor_name}</p>
        )}
        {site.address && (
          <p className="truncate">📍 {site.address}</p>
        )}
      </div>

      {/* バッジ行 */}
      <div className="flex gap-3 mt-3 pt-2 border-t border-gray-100">
        <div className="flex items-center gap-1">
          <span className="text-xs text-gray-400">有効QR</span>
          <span className={`text-sm font-bold ${site.active_qr_count === 0 ? 'text-gray-400' : 'text-primary-600'}`}>
            {site.active_qr_count}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-xs text-gray-400">承認待ち</span>
          <span className={`text-sm font-bold ${site.pending_entry_count > 0 ? 'text-yellow-600' : 'text-gray-400'}`}>
            {site.pending_entry_count}
          </span>
          {site.pending_entry_count > 0 && (
            <span className="text-xs text-yellow-600 font-medium">件</span>
          )}
        </div>
      </div>
    </Link>
  )
}

// ============================================================
// ページ本体
// ============================================================
export default function AdminSitesPage() {
  const { getAccessToken, refreshIfNeeded, isAuthenticated } = useAdminAuth()
  const router = useRouter()

  const [data,    setData]    = useState<SiteListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)
  const [page,    setPage]    = useState(1)

  const load = useCallback(async (pg: number) => {
    const token = getAccessToken()
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const res = await getSites({ page: pg, per_page: 20 }, token)
      setData(res)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        const newToken = await refreshIfNeeded()
        if (!newToken) { router.push('/admin/login'); return }
        const res = await getSites({ page: pg, per_page: 20 }, newToken)
        setData(res)
      } else {
        setError('現場一覧の取得に失敗しました')
      }
    } finally {
      setLoading(false)
    }
  }, [getAccessToken, refreshIfNeeded, router])

  useEffect(() => {
    if (isAuthenticated) void load(page)
  }, [load, page, isAuthenticated])

  return (
    <div className="p-4 space-y-4 pb-8">
      {/* ヘッダー */}
      <div className="pt-2">
        <h1 className="text-xl font-bold text-gray-900">現場一覧</h1>
        {data && (
          <p className="text-sm text-gray-500 mt-0.5">{data.total}件の現場</p>
        )}
      </div>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {/* リスト */}
      {loading ? (
        <div className="flex justify-center py-12">
          <Spinner size="lg" className="text-primary-600" />
        </div>
      ) : data?.items.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <div className="text-4xl mb-3">🏗️</div>
          <p className="font-medium">担当している現場はありません</p>
          <p className="text-sm mt-1">管理者に現場の割り当てを依頼してください</p>
        </div>
      ) : (
        <div className="space-y-3">
          {data?.items.map(site => (
            <SiteCard key={site.id} site={site} />
          ))}
        </div>
      )}

      {/* ページネーション */}
      {data && data.total > 20 && (
        <div className="flex items-center justify-between pt-2">
          <Button
            variant="secondary" fullWidth={false} className="min-w-[100px]"
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1 || loading}
          >
            ← 前
          </Button>
          <span className="text-sm text-gray-500">
            {page} / {Math.ceil(data.total / 20)}ページ
          </span>
          <Button
            variant="secondary" fullWidth={false} className="min-w-[100px]"
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
