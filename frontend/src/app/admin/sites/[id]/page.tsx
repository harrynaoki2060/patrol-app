'use client'

/**
 * /admin/sites/[id] — 現場詳細 + QR コード管理
 *
 * 機能:
 *  - 現場情報表示（工期・監督・注意事項）
 *  - QR コード一覧（use_count / last_accessed / expires_at / blocked_count）
 *  - QR 新規発行フォーム（インライン展開）
 *  - QR 無効化 / 再有効化
 *  - QR 画像表示（Canvas） + PNG / SVG ダウンロード
 *  - 印刷レイアウト（@media print、A4 最適化）
 *
 * QR URL 形式: window.location.origin + '/entry/' + token
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import QRCode from 'qrcode'
import { getSiteDetail, createQr, deactivateQr, activateQr } from '@/lib/api/sites'
import { ApiError } from '@/lib/api/client'
import { useAdminAuth } from '@/lib/context/AdminAuthContext'
import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import type { QrCodeItem, QrCreateRequest, SiteDetailResponse } from '@/types/api'

// =============================================================================
// ユーティリティ
// =============================================================================

function fmtDate(s: string | null | undefined): string {
  if (!s) return '—'
  const d = new Date(s)
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`
}

function fmtDateTime(s: string | null | undefined): string {
  if (!s) return '—'
  return new Date(s).toLocaleString('ja-JP', {
    month: 'numeric', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function isExpired(expiresAt: string | null): boolean {
  if (!expiresAt) return false
  return new Date(expiresAt) < new Date()
}

/** QR の実質的な有効性（is_active && !expired && max_uses 未達） */
function isEffectivelyActive(qr: QrCodeItem): boolean {
  if (!qr.is_active) return false
  if (isExpired(qr.expires_at)) return false
  if (qr.max_uses !== null && qr.use_count >= qr.max_uses) return false
  return true
}

function buildQrUrl(token: string): string {
  if (typeof window === 'undefined') return `/entry/${token}`
  return `${window.location.origin}/entry/${token}`
}

// =============================================================================
// QR 画像生成（Canvas + qrcode ライブラリ）
// =============================================================================

interface QrImageProps {
  url: string
  size?: number
}

function QrImage({ url, size = 220 }: QrImageProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (!canvasRef.current) return
    QRCode.toCanvas(canvasRef.current, url, {
      width: size,
      margin: 2,
      errorCorrectionLevel: 'M',
      color: { dark: '#1a1a1a', light: '#ffffff' },
    }).catch(console.error)
  }, [url, size])

  return (
    <canvas
      ref={canvasRef}
      width={size}
      height={size}
      className="rounded-lg"
      style={{ imageRendering: 'pixelated' }}
    />
  )
}

// =============================================================================
// QR ダウンロード（PNG / SVG）
// =============================================================================

async function downloadQrPng(url: string, label: string) {
  const dataUrl = await QRCode.toDataURL(url, {
    width: 512,
    margin: 2,
    errorCorrectionLevel: 'M',
    color: { dark: '#1a1a1a', light: '#ffffff' },
  })
  const a = document.createElement('a')
  a.href = dataUrl
  a.download = `qr-${label || 'code'}.png`
  a.click()
}

async function downloadQrSvg(url: string, label: string) {
  const svg = await QRCode.toString(url, {
    type: 'svg',
    width: 256,
    margin: 2,
    errorCorrectionLevel: 'M',
    color: { dark: '#1a1a1a', light: '#ffffff' },
  })
  const blob = new Blob([svg], { type: 'image/svg+xml' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `qr-${label || 'code'}.svg`
  a.click()
  URL.revokeObjectURL(a.href)
}

// =============================================================================
// QR カード
// =============================================================================

interface QrCardProps {
  qr: QrCodeItem
  siteId: string
  siteName: string
  siteCustomNotice: string | null
  onDeactivate: (id: string) => Promise<void>
  onActivate: (id: string) => Promise<void>
  processing: string | null
  frontendOrigin: string
}

function QrCard({
  qr, siteId, siteName, siteCustomNotice,
  onDeactivate, onActivate, processing, frontendOrigin,
}: QrCardProps) {
  const [showQr, setShowQr] = useState(false)
  const [printing, setPrinting] = useState(false)
  const isProc = processing === qr.id
  const effective = isEffectivelyActive(qr)
  const expired = isExpired(qr.expires_at)
  const maxReached = qr.max_uses !== null && qr.use_count >= qr.max_uses
  const qrUrl = `${frontendOrigin}/entry/${qr.is_active ? '' : ''}${frontendOrigin}/entry/`
    .replace(/\/entry\/$/, `/entry/`) // normalize
  const fullQrUrl = `${frontendOrigin}/entry/${qr.id}` // placeholder until token exposed

  // NOTE: token は QrCreateResponse にしか入っていない（一覧では不要）
  // 印刷・DL 用 URL は qr.id ではなく別途 token を保持する必要があるが、
  // ここでは ID を代替として使う（実際は token が必要 → 次フェーズで改善）

  const statusLabel = !qr.is_active
    ? '無効'
    : expired
      ? '期限切れ'
      : maxReached
        ? '上限到達'
        : '有効'

  const statusColor = effective
    ? 'badge-approved'
    : 'badge-rejected'

  return (
    <div className={`card border ${effective ? 'border-green-100' : 'border-gray-200'}`}>
      {/* ヘッダー */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-gray-900 text-sm">
              {qr.label || 'ラベルなし'}
            </span>
            <span className={statusColor}>{statusLabel}</span>
            {qr.pin_required && (
              <span className="badge-pending">PIN 必須</span>
            )}
          </div>
          <p className="text-xs text-gray-400 mt-0.5">
            発行: {fmtDateTime(qr.created_at)}
            {qr.created_by_name && ` (${qr.created_by_name})`}
          </p>
        </div>
      </div>

      {/* アナリティクス */}
      <div className="grid grid-cols-3 gap-2 mt-3 text-center">
        <div className="bg-gray-50 rounded-lg py-1.5 px-2">
          <p className="text-xs text-gray-400">認証回数</p>
          <p className="text-base font-bold text-gray-900">{qr.use_count}</p>
          {qr.max_uses !== null && (
            <p className="text-xs text-gray-400">/ {qr.max_uses}</p>
          )}
        </div>
        <div className="bg-gray-50 rounded-lg py-1.5 px-2">
          <p className="text-xs text-gray-400">最終アクセス</p>
          <p className="text-xs font-medium text-gray-700">
            {qr.last_accessed_at ? fmtDateTime(qr.last_accessed_at) : '未使用'}
          </p>
        </div>
        <div className={`rounded-lg py-1.5 px-2 ${qr.blocked_count > 0 ? 'bg-red-50' : 'bg-gray-50'}`}>
          <p className="text-xs text-gray-400">ブロック回数</p>
          <p className={`text-base font-bold ${qr.blocked_count > 0 ? 'text-danger-600' : 'text-gray-900'}`}>
            {qr.blocked_count}
          </p>
        </div>
      </div>

      {/* 有効期限 */}
      {qr.expires_at && (
        <p className={`text-xs mt-2 ${expired ? 'text-danger-600 font-medium' : 'text-gray-500'}`}>
          有効期限: {fmtDateTime(qr.expires_at)}
          {expired && ' （期限切れ）'}
        </p>
      )}

      {/* QR 画像（展開） */}
      {showQr && qr.is_active && (
        <div className="mt-3 pt-3 border-t border-gray-100 qr-print-section">
          <QrImageWithToken qrId={qr.id} label={qr.label || 'QR'} />
        </div>
      )}

      {/* アクションボタン */}
      <div className="flex gap-2 mt-3 pt-3 border-t border-gray-100 no-print">
        {qr.is_active && (
          <button
            onClick={() => setShowQr(v => !v)}
            className="flex-1 min-h-[44px] bg-primary-50 hover:bg-primary-100 text-primary-700 text-sm font-medium rounded-xl transition-colors"
          >
            {showQr ? 'QRを閉じる' : 'QRを表示'}
          </button>
        )}
        {qr.is_active ? (
          <button
            onClick={() => onDeactivate(qr.id)}
            disabled={!!processing}
            className="flex-1 min-h-[44px] bg-white hover:bg-danger-50 text-danger-600 border border-danger-200 text-sm font-medium rounded-xl transition-colors disabled:opacity-50"
          >
            {isProc ? <Spinner size="sm" className="text-danger-600 mx-auto" /> : '無効化'}
          </button>
        ) : (
          <button
            onClick={() => onActivate(qr.id)}
            disabled={!!processing}
            className="flex-1 min-h-[44px] bg-white hover:bg-success-50 text-success-700 border border-success-200 text-sm font-medium rounded-xl transition-colors disabled:opacity-50"
          >
            {isProc ? <Spinner size="sm" className="text-success-700 mx-auto" /> : '再有効化'}
          </button>
        )}
      </div>
    </div>
  )
}

// =============================================================================
// QR 画像（token 付き）コンポーネント
// 表示 + PNG/SVG ダウンロード + 印刷トリガー
// =============================================================================
function QrImageWithToken({ qrId, label }: { qrId: string; label: string }) {
  // NOTE: QrCodeItem には token が含まれていない（セキュリティ設計）
  // 本実装では「QR 作成直後」にのみ token を持っている QrNewlyCreated 状態で表示する
  // ここでは placeholder（実際には /admin/sites/[id]/qr/[qrId]/token エンドポイントが必要）
  // この制限は TECH_DEBT に記録する
  return (
    <div className="text-center text-sm text-gray-500 py-4">
      <p>QR 画像を表示するには再発行が必要です</p>
      <p className="text-xs mt-1 text-gray-400">
        （既存 QR の token は再取得できません。新しく QR を発行してください）
      </p>
    </div>
  )
}

// =============================================================================
// 新規作成後 QR 表示（token あり）
// =============================================================================

interface NewQrDisplayProps {
  token: string
  label: string | null
  siteName: string
  siteCustomNotice: string | null
  onClose: () => void
}

function NewQrDisplay({ token, label, siteName, siteCustomNotice, onClose }: NewQrDisplayProps) {
  const qrUrl = buildQrUrl(token)

  async function handlePrint() {
    // 印刷専用ウィンドウを開く
    const printWin = window.open('', '_blank', 'width=800,height=1000')
    if (!printWin) return

    const pngDataUrl = await QRCode.toDataURL(qrUrl, {
      width: 400,
      margin: 2,
      errorCorrectionLevel: 'M',
    })

    printWin.document.write(`
      <!DOCTYPE html>
      <html lang="ja">
      <head>
        <meta charset="UTF-8">
        <title>QR コード — ${siteName}</title>
        <style>
          @page { size: A4; margin: 20mm; }
          body { font-family: 'Hiragino Kaku Gothic ProN', 'Noto Sans JP', sans-serif;
                 text-align: center; color: #111; }
          .site-name { font-size: 22pt; font-weight: bold; margin-bottom: 8px; }
          .label { font-size: 14pt; color: #555; margin-bottom: 24px; }
          .qr-image { width: 200px; height: 200px; margin: 0 auto 24px; display: block; }
          .url { font-size: 8pt; color: #888; word-break: break-all; margin-bottom: 16px; }
          .notice { font-size: 11pt; background: #fff3cd; border: 1px solid #ffc107;
                    padding: 12px 16px; border-radius: 8px; text-align: left; margin-top: 16px; }
          .notice-title { font-weight: bold; margin-bottom: 4px; }
          .footer { margin-top: 32px; font-size: 9pt; color: #aaa; }
          hr { border: none; border-top: 1px solid #ddd; margin: 20px 0; }
          .instructions { text-align: left; margin-top: 24px; font-size: 10pt; }
          .instructions li { margin-bottom: 6px; }
        </style>
      </head>
      <body>
        <p class="site-name">🏗️ ${siteName}</p>
        ${label ? `<p class="label">${label}</p>` : ''}
        <hr>
        <img class="qr-image" src="${pngDataUrl}" alt="QR コード" />
        <p class="url">${qrUrl}</p>

        <div class="instructions">
          <strong>【入場申請の手順】</strong>
          <ol>
            <li>スマートフォンでこの QR コードを読み取ってください</li>
            <li>表示された申請フォームに必要事項を入力します</li>
            <li>「申請を送信する」をタップして完了です</li>
            <li>受付番号を担当者にお伝えください</li>
          </ol>
        </div>

        ${siteCustomNotice ? `
        <div class="notice">
          <p class="notice-title">⚠️ 現場からのお知らせ</p>
          <p>${siteCustomNotice.replace(/\n/g, '<br>')}</p>
        </div>
        ` : ''}

        <p class="footer">
          建設工事 新規入場管理システム
          &nbsp;|&nbsp; 印刷日: ${new Date().toLocaleDateString('ja-JP')}
        </p>
      </body>
      </html>
    `)
    printWin.document.close()
    printWin.focus()
    printWin.print()
  }

  return (
    <div className="card border-2 border-primary-300 bg-primary-50 animate-slide-up">
      {/* タイトル */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-bold text-primary-800">✅ QR コードが発行されました</h3>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 text-lg min-w-[32px] min-h-[32px] flex items-center justify-center"
          aria-label="閉じる"
        >✕</button>
      </div>

      {label && <p className="text-sm text-primary-700 mb-3 font-medium">{label}</p>}

      {/* QR 画像 */}
      <div className="flex justify-center mb-4">
        <QrImage url={qrUrl} size={200} />
      </div>

      {/* URL */}
      <p className="text-xs text-gray-500 text-center break-all mb-4">{qrUrl}</p>

      {/* ダウンロード・印刷ボタン */}
      <div className="grid grid-cols-3 gap-2">
        <button
          onClick={() => downloadQrPng(qrUrl, label || 'qr')}
          className="min-h-[44px] bg-white hover:bg-gray-50 border border-gray-200 text-gray-700 text-xs font-medium rounded-xl transition-colors flex flex-col items-center justify-center gap-0.5"
        >
          <span>📥</span>
          <span>PNG</span>
        </button>
        <button
          onClick={() => downloadQrSvg(qrUrl, label || 'qr')}
          className="min-h-[44px] bg-white hover:bg-gray-50 border border-gray-200 text-gray-700 text-xs font-medium rounded-xl transition-colors flex flex-col items-center justify-center gap-0.5"
        >
          <span>📐</span>
          <span>SVG</span>
        </button>
        <button
          onClick={handlePrint}
          className="min-h-[44px] bg-primary-600 hover:bg-primary-700 text-white text-xs font-medium rounded-xl transition-colors flex flex-col items-center justify-center gap-0.5"
        >
          <span>🖨️</span>
          <span>印刷</span>
        </button>
      </div>

      <p className="text-xs text-gray-400 text-center mt-3">
        ※ このダイアログを閉じると QR 画像は再表示できません。<br />
        必要な場合は先にダウンロードしてください。
      </p>
    </div>
  )
}

// =============================================================================
// QR 新規発行フォーム
// =============================================================================

interface QrCreateFormProps {
  onSubmit: (req: QrCreateRequest) => Promise<void>
  onCancel: () => void
  submitting: boolean
}

function QrCreateForm({ onSubmit, onCancel, submitting }: QrCreateFormProps) {
  const [label,      setLabel]      = useState('')
  const [pinRequired, setPinRequired] = useState(false)
  const [pin,        setPin]        = useState('')
  const [expiresAt,  setExpiresAt]  = useState('')
  const [maxUses,    setMaxUses]    = useState('')
  const [errors,     setErrors]     = useState<Record<string, string>>({})

  function validate(): boolean {
    const e: Record<string, string> = {}
    if (pinRequired && !pin) e.pin = 'PIN を入力してください'
    if (pin && !/^\d{4,8}$/.test(pin)) e.pin = 'PIN は 4〜8 桁の数字で入力してください'
    if (maxUses && (isNaN(Number(maxUses)) || Number(maxUses) < 1))
      e.maxUses = '1 以上の整数を入力してください'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return
    const req: QrCreateRequest = {
      label: label.trim() || undefined,
      pin_required: pinRequired,
      pin: pinRequired ? pin : undefined,
      expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
      max_uses: maxUses ? Number(maxUses) : null,
    }
    await onSubmit(req)
  }

  return (
    <form onSubmit={handleSubmit} className="card border border-primary-200 bg-primary-50 space-y-4 animate-slide-up">
      <h3 className="font-bold text-primary-800">QR コードを新規発行</h3>

      {/* ラベル */}
      <div>
        <label className="form-label">ラベル <span className="text-gray-400 text-xs">（任意）</span></label>
        <input
          type="text"
          value={label}
          onChange={e => setLabel(e.target.value)}
          placeholder="例: 北ゲート用 / メイン入口"
          maxLength={100}
          className="form-input"
          autoFocus
        />
      </div>

      {/* PIN */}
      <div>
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={pinRequired}
            onChange={e => setPinRequired(e.target.checked)}
            className="w-5 h-5 rounded"
          />
          <span className="text-sm font-medium text-gray-700">PIN 入力を要求する</span>
        </label>
        {pinRequired && (
          <div className="mt-2">
            <input
              type="tel"
              value={pin}
              onChange={e => setPin(e.target.value.replace(/\D/g, '').slice(0, 8))}
              placeholder="4〜8 桁の数字"
              className={`form-input ${errors.pin ? 'border-danger-500' : ''}`}
              inputMode="numeric"
              autoComplete="off"
            />
            {errors.pin && <p className="form-error">{errors.pin}</p>}
            <p className="text-xs text-gray-400 mt-1">
              ※ PIN は現場担当者が口頭で作業員に伝えてください
            </p>
          </div>
        )}
      </div>

      {/* 有効期限 */}
      <div>
        <label className="form-label">有効期限 <span className="text-gray-400 text-xs">（任意・空白 = 無期限）</span></label>
        <input
          type="datetime-local"
          value={expiresAt}
          onChange={e => setExpiresAt(e.target.value)}
          className="form-input"
          min={new Date().toISOString().slice(0, 16)}
        />
      </div>

      {/* 最大使用回数 */}
      <div>
        <label className="form-label">最大使用回数 <span className="text-gray-400 text-xs">（任意・空白 = 無制限）</span></label>
        <input
          type="number"
          value={maxUses}
          onChange={e => setMaxUses(e.target.value)}
          placeholder="例: 50"
          min={1}
          className={`form-input ${errors.maxUses ? 'border-danger-500' : ''}`}
          inputMode="numeric"
        />
        {errors.maxUses && <p className="form-error">{errors.maxUses}</p>}
      </div>

      {/* ボタン */}
      <div className="flex gap-2 pt-2">
        <Button type="submit" fullWidth={false} className="flex-1" loading={submitting}>
          発行する
        </Button>
        <Button type="button" variant="secondary" fullWidth={false} className="flex-1" onClick={onCancel}>
          キャンセル
        </Button>
      </div>
    </form>
  )
}

// =============================================================================
// ページ本体
// =============================================================================

export default function AdminSiteDetailPage() {
  const { id: siteId } = useParams<{ id: string }>()
  const { getAccessToken, refreshIfNeeded, isAuthenticated } = useAdminAuth()
  const router = useRouter()

  const [site,        setSite]        = useState<SiteDetailResponse | null>(null)
  const [loading,     setLoading]     = useState(true)
  const [error,       setError]       = useState<string | null>(null)
  const [actionMsg,   setActionMsg]   = useState<string | null>(null)
  const [processing,  setProcessing]  = useState<string | null>(null)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [creating,    setCreating]    = useState(false)
  const [newQr,       setNewQr]       = useState<{ token: string; label: string | null } | null>(null)
  const [origin,      setOrigin]      = useState('')

  useEffect(() => {
    if (typeof window !== 'undefined') setOrigin(window.location.origin)
  }, [])

  const load = useCallback(async () => {
    const token = getAccessToken()
    if (!token || !siteId) return
    setLoading(true)
    setError(null)
    try {
      const res = await getSiteDetail(siteId, token)
      setSite(res)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        const newToken = await refreshIfNeeded()
        if (!newToken) { router.push('/admin/login'); return }
        const res = await getSiteDetail(siteId, newToken)
        setSite(res)
      } else if (err instanceof ApiError && err.status === 404) {
        setError('現場が見つかりません（スコープ外）')
      } else {
        setError('現場情報の取得に失敗しました')
      }
    } finally {
      setLoading(false)
    }
  }, [getAccessToken, refreshIfNeeded, router, siteId])

  useEffect(() => {
    if (isAuthenticated) void load()
  }, [load, isAuthenticated])

  async function handleCreateQr(req: QrCreateRequest) {
    const token = getAccessToken()
    if (!token || !siteId) return
    setCreating(true)
    setError(null)
    try {
      const res = await createQr(siteId, req, token)
      setNewQr({ token: res.token, label: res.label })
      setShowCreateForm(false)
      setActionMsg('QR コードを発行しました')
      void load()
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail || 'QR の発行に失敗しました')
      } else {
        setError('QR の発行に失敗しました')
      }
    } finally {
      setCreating(false)
    }
  }

  async function handleDeactivate(qrId: string) {
    const token = getAccessToken()
    if (!token) return
    setProcessing(qrId)
    setError(null)
    try {
      await deactivateQr(qrId, token)
      setActionMsg('QR コードを無効化しました')
      void load()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError('すでに無効化されています')
      } else {
        setError('無効化に失敗しました')
      }
    } finally {
      setProcessing(null)
    }
  }

  async function handleActivate(qrId: string) {
    const token = getAccessToken()
    if (!token) return
    setProcessing(qrId)
    setError(null)
    try {
      await activateQr(qrId, token)
      setActionMsg('QR コードを再有効化しました')
      void load()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError('すでに有効です')
      } else {
        setError('再有効化に失敗しました')
      }
    } finally {
      setProcessing(null)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Spinner size="lg" className="text-primary-600" />
      </div>
    )
  }

  if (!site) {
    return (
      <div className="p-4">
        <ErrorBanner message={error || '現場が見つかりません'} />
        <div className="mt-4">
          <Link href="/admin/sites" className="text-primary-600 hover:underline text-sm">
            ← 現場一覧に戻る
          </Link>
        </div>
      </div>
    )
  }

  const activeQrCount = site.qr_codes.filter(q => isEffectivelyActive(q)).length

  return (
    <div className="p-4 space-y-5 pb-12">
      {/* 戻るリンク */}
      <div className="pt-2 no-print">
        <Link href="/admin/sites" className="text-sm text-primary-600 hover:underline">
          ← 現場一覧
        </Link>
      </div>

      {/* 現場情報 */}
      <div className="card">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary-100 flex items-center justify-center text-xl flex-shrink-0">
            🏗️
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-bold text-gray-900">{site.name}</h1>
            {site.address && (
              <p className="text-sm text-gray-500 truncate">📍 {site.address}</p>
            )}
          </div>
          {site.pending_entry_count > 0 && (
            <Link
              href={`/admin/pending`}
              className="flex-shrink-0 badge-pending text-xs py-1 px-2.5"
            >
              承認待ち {site.pending_entry_count}件 →
            </Link>
          )}
        </div>

        <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <div>
            <span className="text-gray-400">工期</span>
            <span className="ml-2 text-gray-700">
              {fmtDate(site.start_date)} 〜 {fmtDate(site.end_date)}
            </span>
          </div>
          <div>
            <span className="text-gray-400">担当監督</span>
            <span className="ml-2 text-gray-700">{site.supervisor_name || '—'}</span>
          </div>
          <div>
            <span className="text-gray-400">健康診断</span>
            <span className="ml-2 text-gray-700">{site.require_health_check ? '必須' : '任意'}</span>
          </div>
          <div>
            <span className="text-gray-400">保険情報</span>
            <span className="ml-2 text-gray-700">{site.require_insurance ? '必須' : '任意'}</span>
          </div>
        </div>

        {site.custom_notice && (
          <div className="mt-3 p-3 bg-yellow-50 border border-yellow-200 rounded-xl text-sm text-yellow-800">
            <p className="font-medium mb-0.5">⚠️ 現場からのお知らせ</p>
            <p className="whitespace-pre-wrap text-xs leading-relaxed">{site.custom_notice}</p>
          </div>
        )}
      </div>

      {/* メッセージ */}
      {actionMsg && (
        <ErrorBanner type="info" message={actionMsg} onDismiss={() => setActionMsg(null)} />
      )}
      {error && (
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
      )}

      {/* 新規作成後 QR 表示 */}
      {newQr && (
        <NewQrDisplay
          token={newQr.token}
          label={newQr.label}
          siteName={site.name}
          siteCustomNotice={site.custom_notice}
          onClose={() => setNewQr(null)}
        />
      )}

      {/* QR コードセクション */}
      <div className="space-y-3 no-print">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-bold text-gray-900">QR コード</h2>
            <p className="text-sm text-gray-500">
              有効: {activeQrCount} / 合計: {site.qr_codes.length}
            </p>
          </div>
          {!showCreateForm && (
            <button
              onClick={() => { setShowCreateForm(true); setNewQr(null) }}
              className="min-h-[44px] px-4 bg-primary-600 hover:bg-primary-700 text-white text-sm font-semibold rounded-xl transition-colors"
            >
              + 新規発行
            </button>
          )}
        </div>

        {/* 発行フォーム */}
        {showCreateForm && (
          <QrCreateForm
            onSubmit={handleCreateQr}
            onCancel={() => setShowCreateForm(false)}
            submitting={creating}
          />
        )}

        {/* QR 一覧 */}
        {site.qr_codes.length === 0 ? (
          <div className="text-center py-10 text-gray-400">
            <div className="text-4xl mb-2">📷</div>
            <p className="text-sm">QR コードがまだ発行されていません</p>
          </div>
        ) : (
          <div className="space-y-3">
            {site.qr_codes.map(qr => (
              <QrCard
                key={qr.id}
                qr={qr}
                siteId={site.id}
                siteName={site.name}
                siteCustomNotice={site.custom_notice}
                onDeactivate={handleDeactivate}
                onActivate={handleActivate}
                processing={processing}
                frontendOrigin={origin}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
