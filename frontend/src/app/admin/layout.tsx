'use client'

/**
 * 管理者エリア レイアウト（Phase 9 更新）
 *
 * - AdminAuthProvider でラップ
 * - ログインページ以外は認証チェック
 * - ヘッダーに pending バッジカウント（1〜2 分ポーリング）
 * - 朝礼モードリンク
 * - 高齢者モードトグル
 * - UX フィードバックモーダル
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { AdminAuthProvider, useAdminAuth } from '@/lib/context/AdminAuthContext'
import { ElderlyModeProvider, useElderlyMode } from '@/lib/context/ElderlyModeContext'
import { Spinner } from '@/components/ui/Spinner'
import { getPendingBadges, submitFeedback } from '@/lib/api/ops'
import type { FeedbackCategory, PendingBadgeResponse } from '@/types/api'

// バッジポーリング間隔 (ms)
const BADGE_POLL_INTERVAL = 90_000  // 90 秒

// フィードバックカテゴリのラベル
const FEEDBACK_LABELS: Record<FeedbackCategory, string> = {
  input_hard:      '入力しにくい',
  poor_connection: '接続が悪い',
  unclear:         'わかりにくい',
  other:           'その他',
}

// ============================================================
// PendingBadge コンポーネント
// ============================================================
function PendingBadge({ count, stale }: { count: number; stale: number }) {
  if (count === 0) return null
  return (
    <span
      className={`
        inline-flex items-center justify-center
        min-w-[20px] h-5 px-1.5 rounded-full
        text-xs font-bold text-white
        ${stale > 0 ? 'bg-red-500' : 'bg-primary-500'}
      `}
      aria-label={`承認待ち ${count} 件${stale > 0 ? `（うち ${stale} 件が 30 分超過）` : ''}`}
    >
      {count > 99 ? '99+' : count}
    </span>
  )
}

// ============================================================
// FeedbackModal コンポーネント
// ============================================================
interface FeedbackModalProps {
  token: string
  onClose: () => void
}

function FeedbackModal({ token, onClose }: FeedbackModalProps) {
  const [category, setCategory] = useState<FeedbackCategory>('input_hard')
  const [detail, setDetail]     = useState('')
  const [sending, setSending]   = useState(false)
  const [sent, setSent]         = useState(false)
  const [error, setError]       = useState<string | null>(null)

  async function handleSend(e: React.FormEvent) {
    e.preventDefault()
    setSending(true)
    setError(null)
    try {
      await submitFeedback({ category, detail: detail || undefined }, token)
      setSent(true)
      setTimeout(onClose, 1500)
    } catch {
      setError('送信に失敗しました。もう一度お試しください')
    } finally {
      setSending(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center"
      role="dialog"
      aria-modal="true"
      aria-label="UX フィードバック"
    >
      {/* オーバーレイ */}
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* モーダル本体 */}
      <div className="relative w-full max-w-lg bg-white rounded-t-2xl p-6 pb-10 animate-slide-up">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-bold text-gray-900">UX フィードバック</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-2xl leading-none min-h-[44px] min-w-[44px] flex items-center justify-center"
            aria-label="閉じる"
          >
            ×
          </button>
        </div>

        {sent ? (
          <div className="text-center py-4">
            <div className="text-4xl mb-2">✅</div>
            <p className="text-gray-700 font-medium">フィードバックを受け付けました</p>
          </div>
        ) : (
          <form onSubmit={handleSend} className="space-y-4">
            <p className="text-sm text-gray-600">
              「朝の現場で止まらない」ための改善にご協力ください。
            </p>

            {/* カテゴリ選択 */}
            <div className="grid grid-cols-2 gap-2">
              {(Object.entries(FEEDBACK_LABELS) as [FeedbackCategory, string][]).map(
                ([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setCategory(key)}
                    className={`
                      py-3 px-3 rounded-xl text-sm font-medium transition-colors
                      ${category === key
                        ? 'bg-primary-600 text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }
                    `}
                  >
                    {label}
                  </button>
                )
              )}
            </div>

            {/* 詳細 */}
            <div>
              <label className="form-label" htmlFor="fb-detail">
                詳細（任意・最大500文字）
              </label>
              <textarea
                id="fb-detail"
                value={detail}
                onChange={e => setDetail(e.target.value.slice(0, 500))}
                rows={3}
                placeholder="具体的に教えてください"
                className="form-input resize-none"
              />
            </div>

            {error && (
              <p className="text-sm text-red-600">{error}</p>
            )}

            <button
              type="submit"
              disabled={sending}
              className="btn-primary"
            >
              {sending ? '送信中...' : '送信する'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}

// ============================================================
// AdminLayoutInner
// ============================================================
function AdminLayoutInner({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading, user, logout, getAccessToken } = useAdminAuth()
  const accessToken = getAccessToken()
  const { enabled: elderlyMode, toggle: toggleElderlyMode } = useElderlyMode()
  const pathname    = usePathname()
  const router      = useRouter()

  const isLoginPage = pathname === '/admin/login'

  const [badge, setBadge] = useState<PendingBadgeResponse | null>(null)
  const [showFeedback, setShowFeedback] = useState(false)
  const badgeTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!isLoading && !isAuthenticated && !isLoginPage) {
      router.replace('/admin/login')
    }
  }, [isLoading, isAuthenticated, isLoginPage, router])

  // バッジポーリング
  useEffect(() => {
    if (!isAuthenticated || isLoginPage || !accessToken) return

    async function fetchBadge() {
      if (!accessToken) return
      try {
        const data = await getPendingBadges(accessToken)
        setBadge(data)
      } catch {
        // ポーリングエラーは無視（バッジは best-effort）
      }
    }

    void fetchBadge()
    badgeTimerRef.current = setInterval(fetchBadge, BADGE_POLL_INTERVAL)
    return () => {
      if (badgeTimerRef.current) clearInterval(badgeTimerRef.current)
    }
  }, [isAuthenticated, isLoginPage, accessToken])

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Spinner size="lg" className="text-primary-600" />
      </div>
    )
  }

  if (!isAuthenticated && !isLoginPage) {
    return null
  }

  const roleLabel: Record<string, string> = {
    super_admin: 'スーパー管理者',
    admin:       '管理者',
    supervisor:  '監督',
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* ナビゲーションヘッダー（ログインページ以外） */}
      {!isLoginPage && user && (
        <header className="bg-white border-b border-gray-200 px-4 py-3 sticky top-0 z-30">
          <div className="flex items-center justify-between max-w-3xl mx-auto">
            {/* 左: 名前・ロール */}
            <div>
              <p className="font-semibold text-gray-900 text-sm">入場管理システム</p>
              <p className="text-xs text-gray-500">
                {user.name}（{roleLabel[user.role] ?? user.role}）
              </p>
            </div>

            {/* 右: ナビ */}
            <div className="flex items-center gap-2">
              {/* 朝礼モード */}
              <a
                href="/admin/morning"
                className="text-sm text-primary-600 font-medium hover:underline min-h-[44px] flex items-center px-1"
              >
                朝礼
              </a>

              {/* 現場 */}
              <a
                href="/admin/sites"
                className="text-sm text-primary-600 font-medium hover:underline min-h-[44px] flex items-center px-1"
              >
                現場
              </a>

              {/* 申請 (バッジ付き) */}
              <a
                href="/admin/pending"
                className="relative text-sm text-primary-600 font-medium hover:underline min-h-[44px] flex items-center px-1"
              >
                申請
                {badge && badge.total_pending > 0 && (
                  <span className="ml-1">
                    <PendingBadge
                      count={badge.total_pending}
                      stale={badge.total_stale}
                    />
                  </span>
                )}
              </a>

              {/* 高齢者モードトグル */}
              <button
                onClick={toggleElderlyMode}
                className={`
                  text-xs px-2 py-1 rounded-lg min-h-[44px] flex items-center
                  transition-colors
                  ${elderlyMode
                    ? 'bg-orange-100 text-orange-700 font-medium'
                    : 'text-gray-400 hover:text-gray-600'
                  }
                `}
                aria-pressed={elderlyMode}
                title={elderlyMode ? '高齢者モード: ON' : '高齢者モード: OFF'}
              >
                👴
              </button>

              {/* フィードバック */}
              <button
                onClick={() => setShowFeedback(true)}
                className="text-xs text-gray-400 hover:text-gray-600 min-h-[44px] px-1 flex items-center"
                title="UX フィードバックを送る"
              >
                💬
              </button>

              {/* ログアウト */}
              <button
                onClick={logout}
                className="text-sm text-gray-500 hover:text-gray-700 min-h-[44px] px-2"
              >
                ログアウト
              </button>
            </div>
          </div>

          {/* 30 分超過警告バナー */}
          {badge && badge.total_stale > 0 && (
            <div className="mt-2 -mx-4 px-4 py-2 bg-red-50 border-t border-red-100 text-xs text-red-700 flex items-center gap-2">
              <span>⚠️</span>
              <span>
                {badge.total_stale} 件の申請が 30 分以上承認されていません
              </span>
              <a href="/admin/pending" className="font-bold underline ml-auto">
                確認する
              </a>
            </div>
          )}
        </header>
      )}

      <main className="max-w-3xl mx-auto">
        {children}
      </main>

      {/* フィードバックモーダル */}
      {showFeedback && accessToken && (
        <FeedbackModal
          token={accessToken}
          onClose={() => setShowFeedback(false)}
        />
      )}
    </div>
  )
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AdminAuthProvider>
      <ElderlyModeProvider>
        <AdminLayoutInner>{children}</AdminLayoutInner>
      </ElderlyModeProvider>
    </AdminAuthProvider>
  )
}
