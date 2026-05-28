'use client'

export const dynamic = 'force-dynamic'

/**
 * /admin/morning — 朝礼モード
 *
 * 機能:
 *   - 本日の申請一覧（pending 優先 → approved）
 *   - pending 件数・承認済み件数のサマリー
 *   - 30 分超過の申請に警告表示
 *   - 運用メトリクス（過去 30 日）
 *
 * 目的: 「朝の現場で止まらない」ための朝礼前チェック
 */

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useAdminAuth } from '@/lib/context/AdminAuthContext'
import { getMorningBrief, getMetricsSummary } from '@/lib/api/ops'
import { Spinner } from '@/components/ui/Spinner'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import type { MetricsSummaryResponse, MorningBriefResponse, MorningEntryItem } from '@/types/api'

const workerTypeLabel: Record<string, string> = {
  company_employee: '社員',
  sole_proprietor: '一人親方',
}

function StatusBadge({ status, isStale }: { status: string; isStale: boolean }) {
  if (status === 'pending') {
    return (
      <span className={`
        inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium
        ${isStale ? 'bg-red-100 text-red-800' : 'bg-yellow-100 text-yellow-800'}
      `}>
        {isStale ? '⚠️ 待機中' : '承認待ち'}
      </span>
    )
  }
  if (status === 'approved') {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
        ✓ 承認済み
      </span>
    )
  }
  return null
}

function EntryCard({ item }: { item: MorningEntryItem }) {
  return (
    <Link href={`/admin/entries/${item.id}`}>
      <div className={`
        card mb-3 transition-colors hover:shadow-md
        ${item.is_stale ? 'border-red-200 bg-red-50' : ''}
      `}>
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <StatusBadge status={item.status} isStale={item.is_stale} />
              <span className="text-xs text-gray-400 font-mono">{item.receipt_number}</span>
            </div>
            <p className="font-bold text-gray-900 text-lg">{item.worker_name}</p>
            <p className="text-sm text-gray-600">
              {workerTypeLabel[item.worker_type] ?? item.worker_type}
              {item.affiliation_company && ` · ${item.affiliation_company}`}
            </p>
            {item.job_title && (
              <p className="text-sm text-gray-500">🔧 {item.job_title}</p>
            )}
          </div>
          <div className="text-right flex-shrink-0">
            <p className="text-xs text-gray-400">{item.site_name}</p>
            {item.submitted_at && (
              <p className="text-xs text-gray-400 mt-0.5">
                {new Date(item.submitted_at).toLocaleTimeString('ja-JP', {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </p>
            )}
          </div>
        </div>
        {item.is_stale && (
          <p className="text-xs text-red-600 mt-2 font-medium">
            ⚠️ 30 分以上承認されていません
          </p>
        )}
      </div>
    </Link>
  )
}

function MetricsCard({ data }: { data: MetricsSummaryResponse }) {
  return (
    <div className="card mb-6">
      <p className="text-xs font-medium text-gray-500 mb-3">
        運用メトリクス（過去 {data.period_days} 日間）
      </p>
      <div className="grid grid-cols-2 gap-3">
        <div className="text-center">
          <p className="text-2xl font-bold text-gray-900">{data.total_submissions}</p>
          <p className="text-xs text-gray-500">申請数</p>
        </div>
        <div className="text-center">
          <p className="text-2xl font-bold text-green-700">{data.total_approved}</p>
          <p className="text-xs text-gray-500">承認数</p>
        </div>
        <div className="text-center">
          <p className="text-2xl font-bold text-gray-600">{data.total_rejected}</p>
          <p className="text-xs text-gray-500">差戻し数</p>
        </div>
        <div className="text-center">
          <p className={`text-2xl font-bold ${data.avg_approval_minutes && data.avg_approval_minutes > 30 ? 'text-red-600' : 'text-gray-900'}`}>
            {data.avg_approval_minutes != null
              ? `${Math.round(data.avg_approval_minutes)}分`
              : '—'}
          </p>
          <p className="text-xs text-gray-500">平均承認時間</p>
        </div>
      </div>
      {data.pending_over_30min > 0 && (
        <div className="mt-3 p-2 bg-red-50 rounded-lg">
          <p className="text-xs text-red-700 font-medium">
            ⚠️ 現在 {data.pending_over_30min} 件の申請が 30 分以上放置されています
          </p>
        </div>
      )}
    </div>
  )
}

export default function MorningBriefPage() {
  const { getAccessToken } = useAdminAuth()

  const [brief, setBrief]     = useState<MorningBriefResponse | null>(null)
  const [metrics, setMetrics] = useState<MetricsSummaryResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  const token = getAccessToken()

  const load = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const [briefData, metricsData] = await Promise.all([
        getMorningBrief(token),
        getMetricsSummary(token),
      ])
      setBrief(briefData)
      setMetrics(metricsData)
    } catch {
      setError('データの読み込みに失敗しました')
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => { void load() }, [load])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" className="text-primary-600" />
      </div>
    )
  }

  return (
    <div className="p-4 max-w-2xl mx-auto">
      {/* ヘッダー */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">🌅 朝礼モード</h1>
            {brief && (
              <p className="text-sm text-gray-500 mt-0.5">{brief.today}</p>
            )}
          </div>
          <button
            onClick={() => void load()}
            className="text-sm text-primary-600 font-medium min-h-[44px] px-3"
          >
            更新
          </button>
        </div>
      </div>

      {error && (
        <ErrorBanner type="error" message={error} />
      )}

      {/* サマリーカード */}
      {brief && (
        <div className="grid grid-cols-2 gap-3 mb-6">
          <div className="card text-center">
            <p className={`text-3xl font-bold ${brief.pending_count > 0 ? 'text-yellow-700' : 'text-gray-400'}`}>
              {brief.pending_count}
            </p>
            <p className="text-xs text-gray-500 mt-1">承認待ち</p>
          </div>
          <div className="card text-center">
            <p className="text-3xl font-bold text-green-700">{brief.approved_count}</p>
            <p className="text-xs text-gray-500 mt-1">承認済み</p>
          </div>
        </div>
      )}

      {/* 運用メトリクス */}
      {metrics && <MetricsCard data={metrics} />}

      {/* 申請一覧 */}
      {brief && (
        <>
          {brief.entries.length === 0 ? (
            <div className="text-center py-10 text-gray-400">
              <p className="text-4xl mb-3">✅</p>
              <p className="text-sm">本日の申請はありません</p>
            </div>
          ) : (
            <>
              {/* pending */}
              {brief.entries.filter(e => e.status === 'pending').length > 0 && (
                <div className="mb-4">
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                    承認待ち
                  </p>
                  {brief.entries
                    .filter(e => e.status === 'pending')
                    .map(item => (
                      <EntryCard key={item.id} item={item} />
                    ))}
                </div>
              )}

              {/* approved */}
              {brief.entries.filter(e => e.status === 'approved').length > 0 && (
                <div className="mb-4">
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                    承認済み
                  </p>
                  {brief.entries
                    .filter(e => e.status === 'approved')
                    .map(item => (
                      <EntryCard key={item.id} item={item} />
                    ))}
                </div>
              )}
            </>
          )}
        </>
      )}

      {/* 申請一覧へのリンク */}
      <div className="mt-6 pt-4 border-t border-gray-100">
        <Link
          href="/admin/pending"
          className="btn-secondary text-center block"
        >
          全申請一覧を見る
        </Link>
      </div>
    </div>
  )
}
