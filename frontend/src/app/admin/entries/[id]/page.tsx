'use client'

/**
 * /admin/entries/[id] — 申請詳細ページ
 *
 * 表示:
 *   - 作業員情報（全フィールド）
 *   - 健康診断・保険情報
 *   - 個人情報同意
 *   - 承認ログ
 *
 * 操作:
 *   - 承認ボタン（確認ダイアログ付き）
 *   - 差戻しボタン（理由入力必須）
 */

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { getEntryDetail, approveEntry, rejectEntry } from '@/lib/api/entries'
import { ApiError } from '@/lib/api/client'
import { useAdminAuth } from '@/lib/context/AdminAuthContext'
import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import type { EntryDetailResponse } from '@/types/api'

function formatDate(v: string | null): string {
  if (!v) return '未入力'
  return new Date(v).toLocaleDateString('ja-JP')
}

function formatDateTime(v: string | null): string {
  if (!v) return '—'
  return new Date(v).toLocaleString('ja-JP', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const workerTypeLabel: Record<string, string> = {
  company_employee: '協力会社社員',
  sole_proprietor: '一人親方',
  part_time: 'アルバイト',
}

const genderLabel: Record<string, string> = {
  male: '男性', female: '女性', other: 'その他',
}

const bloodTypeLabel: Record<string, string> = {
  A: 'A型', B: 'B型', O: 'O型', AB: 'AB型', unknown: '不明',
}

const statusLabel: Record<string, { label: string; cls: string }> = {
  pending:   { label: '審査待ち',   cls: 'bg-yellow-100 text-yellow-800' },
  approved:  { label: '承認済み',   cls: 'bg-success-100 text-success-800' },
  rejected:  { label: '差戻し',     cls: 'bg-danger-100 text-danger-800' },
  draft:     { label: '下書き',     cls: 'bg-gray-100 text-gray-600' },
  withdrawn: { label: '取下げ',     cls: 'bg-gray-100 text-gray-600' },
}

// 情報行コンポーネント
function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex gap-3 py-2.5 border-b border-gray-100 last:border-0">
      <dt className="text-sm text-gray-500 flex-shrink-0 w-32">{label}</dt>
      <dd className="text-sm text-gray-900 flex-1">{value || <span className="text-gray-400">未入力</span>}</dd>
    </div>
  )
}

// セクションタイトル
function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-sm font-semibold text-gray-700 bg-gray-100 px-3 py-1.5 rounded-lg mb-0">
      {children}
    </h2>
  )
}

export default function EntryDetailPage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const { getAccessToken, refreshIfNeeded } = useAdminAuth()

  const [entry,      setEntry]      = useState<EntryDetailResponse | null>(null)
  const [loading,    setLoading]    = useState(true)
  const [error,      setError]      = useState<string | null>(null)

  // 承認ダイアログ
  const [showApproveDialog, setShowApproveDialog] = useState(false)
  const [approveComment,    setApproveComment]    = useState('')

  // 差戻しフォーム
  const [showRejectForm, setShowRejectForm] = useState(false)
  const [rejectReason,   setRejectReason]   = useState('')
  const [rejectError,    setRejectError]    = useState<string | null>(null)

  const [processing, setProcessing] = useState(false)
  const [actionResult, setActionResult] = useState<string | null>(null)

  useEffect(() => {
    void loadEntry()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id])

  async function loadEntry() {
    const token = getAccessToken()
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const res = await getEntryDetail(params.id, token)
      setEntry(res)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        const newToken = await refreshIfNeeded()
        if (!newToken) { router.push('/admin/login'); return }
        const res = await getEntryDetail(params.id, newToken)
        setEntry(res)
      } else if (err instanceof ApiError && err.status === 404) {
        setError('申請が見つかりません')
      } else {
        setError('申請の取得に失敗しました')
      }
    } finally {
      setLoading(false)
    }
  }

  async function handleApprove() {
    const token = getAccessToken()
    if (!token || !entry) return
    setProcessing(true)
    try {
      await approveEntry(entry.id, { reason: approveComment || undefined }, token)
      setShowApproveDialog(false)
      setActionResult('承認しました')
      await loadEntry()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError('この申請はすでに処理済みです')
      } else {
        setError('承認に失敗しました')
      }
      setShowApproveDialog(false)
    } finally {
      setProcessing(false)
    }
  }

  async function handleReject(e: React.FormEvent) {
    e.preventDefault()
    if (!rejectReason.trim()) { setRejectError('差戻し理由を入力してください'); return }
    const token = getAccessToken()
    if (!token || !entry) return
    setProcessing(true)
    try {
      await rejectEntry(entry.id, { reason: rejectReason }, token)
      setShowRejectForm(false)
      setRejectReason('')
      setActionResult('差戻しました')
      await loadEntry()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError('この申請はすでに処理済みです')
      } else {
        setError('差戻しに失敗しました')
      }
      setShowRejectForm(false)
    } finally {
      setProcessing(false)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Spinner size="lg" className="text-primary-600" />
      </div>
    )
  }

  if (!entry) {
    return (
      <div className="p-4">
        <ErrorBanner message={error ?? '申請が見つかりません'} />
        <div className="mt-4">
          <Link href="/admin/pending" className="text-primary-600 text-sm hover:underline">
            ← 一覧に戻る
          </Link>
        </div>
      </div>
    )
  }

  const w = entry.worker
  const st = statusLabel[entry.status] ?? { label: entry.status, cls: 'bg-gray-100 text-gray-600' }
  const isPending = entry.status === 'pending'

  return (
    <div className="p-4 pb-12 space-y-4">
      {/* 戻るリンク */}
      <Link href="/admin/pending" className="text-primary-600 text-sm hover:underline flex items-center gap-1">
        ← 一覧に戻る
      </Link>

      {/* ステータスバナー */}
      {actionResult && (
        <ErrorBanner type="info" message={actionResult} onDismiss={() => setActionResult(null)} />
      )}
      {error && (
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
      )}

      {/* ヘッダー */}
      <div className="card">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold text-gray-900">
                {w.last_name} {w.first_name}
              </h1>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${st.cls}`}>
                {st.label}
              </span>
            </div>
            {(w.last_name_kana || w.first_name_kana) && (
              <p className="text-sm text-gray-500">
                {w.last_name_kana} {w.first_name_kana}
              </p>
            )}
          </div>
          <div className="text-right flex-shrink-0">
            <p className="text-xs text-gray-400">受付番号</p>
            <p className="font-mono font-semibold text-gray-700">{entry.receipt_number}</p>
          </div>
        </div>
        <div className="mt-3 text-sm text-gray-500 space-y-0.5">
          <p>📍 {entry.site_name}</p>
          <p>📅 提出: {formatDateTime(entry.submitted_at)}</p>
          {entry.planned_entry_date && (
            <p>🚪 入場予定: {formatDate(entry.planned_entry_date)}</p>
          )}
        </div>
      </div>

      {/* 操作ボタン（pending のみ） */}
      {isPending && !showRejectForm && !showApproveDialog && (
        <div className="flex gap-3">
          <button
            onClick={() => setShowApproveDialog(true)}
            className="flex-1 min-h-[56px] bg-success-600 hover:bg-success-700 text-white font-semibold rounded-xl flex items-center justify-center gap-2 transition-colors"
          >
            ✓ 承認する
          </button>
          <button
            onClick={() => setShowRejectForm(true)}
            className="flex-1 min-h-[56px] bg-white border border-danger-300 text-danger-600 hover:bg-danger-50 font-semibold rounded-xl flex items-center justify-center gap-2 transition-colors"
          >
            ✕ 差戻す
          </button>
        </div>
      )}

      {/* 承認確認ダイアログ */}
      {showApproveDialog && (
        <div className="card border-2 border-success-300 bg-success-50">
          <h3 className="font-semibold text-success-800 mb-3">承認の確認</h3>
          <p className="text-sm text-success-700 mb-3">
            {w.last_name} {w.first_name} さんの申請を承認しますか？
          </p>
          <div className="mb-3">
            <label className="form-label">承認コメント（任意）</label>
            <textarea
              value={approveComment}
              onChange={e => setApproveComment(e.target.value)}
              placeholder="コメントがあれば入力（省略可）"
              rows={2}
              className="form-input resize-none"
              autoFocus
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleApprove}
              disabled={processing}
              className="flex-1 min-h-[48px] bg-success-600 hover:bg-success-700 text-white font-semibold rounded-xl flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {processing ? <Spinner size="sm" className="text-white" /> : null}
              承認を確定
            </button>
            <button
              onClick={() => { setShowApproveDialog(false); setApproveComment('') }}
              className="flex-1 min-h-[48px] bg-white border border-gray-300 text-gray-700 font-semibold rounded-xl transition-colors hover:bg-gray-50"
            >
              キャンセル
            </button>
          </div>
        </div>
      )}

      {/* 差戻しフォーム */}
      {showRejectForm && (
        <form onSubmit={handleReject} className="card border-2 border-danger-300 bg-danger-50 space-y-3">
          <h3 className="font-semibold text-danger-800">差戻しの理由</h3>
          <p className="text-sm text-danger-700">
            差戻し理由は作業員に通知されます。具体的に入力してください。
          </p>
          <div>
            <label className="form-label" htmlFor="reject-reason">
              差戻し理由 <span className="text-danger-600">*</span>
            </label>
            <textarea
              id="reject-reason"
              value={rejectReason}
              onChange={e => { setRejectReason(e.target.value); setRejectError(null) }}
              placeholder="例: 保険証のコピーが不鮮明です。再提出をお願いします。"
              rows={4}
              autoFocus
              className={`form-input resize-none ${rejectError ? 'border-danger-500' : ''}`}
            />
            {rejectError && <p role="alert" className="form-error">{rejectError}</p>}
          </div>
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={processing}
              className="flex-1 min-h-[48px] bg-danger-600 hover:bg-danger-700 text-white font-semibold rounded-xl flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {processing ? <Spinner size="sm" className="text-white" /> : null}
              差戻しを確定
            </button>
            <button
              type="button"
              onClick={() => { setShowRejectForm(false); setRejectReason(''); setRejectError(null) }}
              className="flex-1 min-h-[48px] bg-white border border-gray-300 text-gray-700 font-semibold rounded-xl transition-colors hover:bg-gray-50"
            >
              キャンセル
            </button>
          </div>
        </form>
      )}

      {/* 作業員情報 */}
      <section className="space-y-1">
        <SectionTitle>👷 作業員情報</SectionTitle>
        <dl className="card">
          <InfoRow label="氏名" value={`${w.last_name} ${w.first_name}`} />
          <InfoRow label="カナ" value={(w.last_name_kana || w.first_name_kana) ? `${w.last_name_kana ?? ''} ${w.first_name_kana ?? ''}` : null} />
          <InfoRow label="電話番号" value={w.phone} />
          <InfoRow label="生年月日" value={formatDate(w.birth_date)} />
          <InfoRow label="性別" value={w.gender ? genderLabel[w.gender] ?? w.gender : null} />
          <InfoRow label="血液型" value={w.blood_type ? bloodTypeLabel[w.blood_type] ?? w.blood_type : null} />
          <InfoRow label="区分" value={w.worker_type ? workerTypeLabel[w.worker_type] ?? w.worker_type : null} />
          <InfoRow label="所属会社" value={w.affiliation_company} />
          <InfoRow label="職種" value={w.job_title} />
        </dl>
      </section>

      {/* 連絡先・住所 */}
      <section className="space-y-1">
        <SectionTitle>📞 緊急連絡先・住所</SectionTitle>
        <dl className="card">
          <InfoRow label="緊急連絡先" value={w.emergency_contact} />
          <InfoRow label="連絡先氏名" value={w.emergency_contact_name} />
          <InfoRow label="続柄" value={w.emergency_contact_relation} />
          <InfoRow label="郵便番号" value={w.postal_code} />
          <InfoRow label="住所" value={w.address} />
        </dl>
      </section>

      {/* 健康診断・保険 */}
      <section className="space-y-1">
        <SectionTitle>🏥 健康診断・保険</SectionTitle>
        <dl className="card">
          <InfoRow label="健康診断" value={
            <span className={entry.has_health_check ? 'text-success-600 font-medium' : 'text-danger-600'}>
              {entry.has_health_check ? '✓ 受診済み' : '✗ 未受診'}
            </span>
          } />
          {entry.has_health_check && (
            <InfoRow label="実施日" value={formatDate(entry.health_check_date)} />
          )}
          <InfoRow label="保険種別" value={w.insurance_type} />
          <InfoRow label="保険番号" value={w.insurance_number} />
          <InfoRow label="個人情報同意" value={
            w.consent_agreed_at
              ? <span className="text-success-600 font-medium">✓ 同意済み ({formatDate(w.consent_agreed_at)})</span>
              : <span className="text-danger-600">未同意</span>
          } />
        </dl>
      </section>

      {/* 承認ログ */}
      {entry.approval_logs.length > 0 && (
        <section className="space-y-1">
          <SectionTitle>📋 処理履歴</SectionTitle>
          <div className="space-y-2">
            {entry.approval_logs.map(log => (
              <div key={log.id} className="card border-l-4 border-l-gray-300">
                <div className="flex items-center justify-between mb-1">
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                    log.action === 'approved' ? 'bg-success-100 text-success-700' :
                    log.action === 'rejected' ? 'bg-danger-100 text-danger-700' :
                    'bg-gray-100 text-gray-700'
                  }`}>
                    {log.action === 'approved' ? '承認' : log.action === 'rejected' ? '差戻し' : '取下げ'}
                  </span>
                  <span className="text-xs text-gray-400">{formatDateTime(log.created_at)}</span>
                </div>
                {log.actor_name && (
                  <p className="text-xs text-gray-500">担当: {log.actor_name}</p>
                )}
                {log.reason && (
                  <p className="text-sm text-gray-700 mt-1">{log.reason}</p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
