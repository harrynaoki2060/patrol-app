'use client'

/**
 * /entry/[token] — QR アクセス → PIN 認証 → フォームへ
 *
 * フロー:
 *   1. ページロード時に token で QR 検証を試みる（PIN なし）
 *   2. 成功 → entry_session を sessionStorage に保存 → /entry/[token]/form へ
 *   3. 401 + "PIN" → PIN 入力画面を表示
 *   4. PIN 送信 → 再度検証
 *   5. その他エラー → エラー画面
 */

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { verifyQr } from '@/lib/api/public'
import { ApiError } from '@/lib/api/client'
import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { TroubleHelp } from '@/components/admin/TroubleHelp'

// sessionStorage のキー
const SESSION_TOKEN_KEY = 'entry_session_token'
const SITE_INFO_KEY     = 'entry_site_info'

interface PageProps {
  params: { token: string }
}

type ScreenState = 'loading' | 'pin' | 'verifying' | 'error'

export default function EntryTokenPage({ params }: PageProps) {
  const { token } = params
  const router = useRouter()

  const [screen, setScreen]   = useState<ScreenState>('loading')
  const [pin, setPin]         = useState('')
  const [pinError, setPinError] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [retryAfter, setRetryAfter] = useState<number | null>(null)
  const [pinAttempts, setPinAttempts] = useState(0)

  // 初回ロード: PIN なしで検証を試みる
  useEffect(() => {
    void tryVerify()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  async function tryVerify(pinValue?: string) {
    setScreen('verifying')
    setPinError(null)
    setErrorMsg(null)
    setRetryAfter(null)

    try {
      const res = await verifyQr({ token, pin: pinValue })

      // 成功: sessionStorage に保存して form ページへ
      sessionStorage.setItem(SESSION_TOKEN_KEY, res.entry_session_token)
      sessionStorage.setItem(SITE_INFO_KEY, JSON.stringify(res.site))
      router.replace(`/entry/${token}/form`)

    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          // PIN が必要 or 間違い
          if (pinValue) {
            // PIN を入力済みだが不正
            setPinAttempts(prev => prev + 1)
            setPinError('PINが正しくありません。もう一度入力してください')
            setScreen('pin')
          } else {
            // 初回: PIN が必要
            setScreen('pin')
          }
        } else if (err.status === 429) {
          // ブルートフォース保護でブロック
          const retryMatch = err.detail.match(/(\d+)/)
          setRetryAfter(retryMatch ? parseInt(retryMatch[1]) : 15)
          setErrorMsg(`不正なアクセスが検出されました。しばらくお待ちください`)
          setScreen('error')
        } else if (err.status === 0) {
          setErrorMsg('ネットワークに接続できません。WiFi や電波を確認してください')
          setScreen('error')
        } else {
          setErrorMsg('このQRコードは無効です。現場の担当者にお問い合わせください')
          setScreen('error')
        }
      } else {
        setErrorMsg('予期しないエラーが発生しました')
        setScreen('error')
      }
    }
  }

  function handlePinSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (pin.length < 4) {
      setPinError('PINは4桁以上の数字で入力してください')
      return
    }
    void tryVerify(pin)
  }

  // ============================================================
  // ローディング画面
  // ============================================================
  if (screen === 'loading' || screen === 'verifying') {
    return (
      <div className="min-h-screen bg-primary-600 flex flex-col items-center justify-center p-6">
        <div className="text-center">
          <div className="text-5xl mb-6">🏗️</div>
          <Spinner size="lg" className="text-white mx-auto mb-4" />
          <p className="text-white text-lg font-medium">
            {screen === 'loading' ? '読み込み中...' : '確認中...'}
          </p>
          <p className="text-primary-200 text-sm mt-2">
            このまましばらくお待ちください
          </p>
        </div>
      </div>
    )
  }

  // ============================================================
  // エラー画面
  // ============================================================
  if (screen === 'error') {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col p-6">
        <div className="flex-1 flex flex-col items-center justify-center">
          <div className="text-6xl mb-6">
            {retryAfter ? '🔒' : '❌'}
          </div>
          <h1 className="text-xl font-bold text-gray-900 mb-3 text-center">
            {retryAfter ? 'アクセスがブロックされました' : 'QRコードが無効です'}
          </h1>
          <div className="card w-full max-w-sm">
            <p className="text-gray-700 text-sm leading-relaxed">
              {errorMsg}
            </p>
            {retryAfter && (
              <p className="text-gray-500 text-sm mt-2">
                約{retryAfter}分後に再試行できます
              </p>
            )}
          </div>
          <div className="mt-6">
            <TroubleHelp />
          </div>
        </div>
      </div>
    )
  }

  // ============================================================
  // PIN 入力画面
  // ============================================================
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* ヘッダー */}
      <div className="bg-primary-600 px-4 pt-12 pb-8 text-white text-center">
        <div className="text-4xl mb-3">🔐</div>
        <h1 className="text-xl font-bold">PIN入力</h1>
        <p className="text-primary-200 text-sm mt-1">
          セキュリティのため PIN が必要です
        </p>
      </div>

      {/* フォーム */}
      <form onSubmit={handlePinSubmit} className="flex-1 p-6 space-y-5">
        {pinAttempts >= 3 && (
          <ErrorBanner
            type="warning"
            message="入力エラーが続いています。わからない場合は現場の担当者にお問い合わせください"
          />
        )}

        <div>
          <label className="form-label" htmlFor="pin-input">
            PIN番号
            <span className="text-danger-600 ml-1">*</span>
          </label>
          <input
            id="pin-input"
            type="password"
            inputMode="numeric"
            pattern="[0-9]*"
            value={pin}
            onChange={e => {
              setPin(e.target.value.replace(/\D/g, '').slice(0, 8))
              setPinError(null)
            }}
            placeholder="数字のみ"
            autoFocus
            autoComplete="one-time-code"
            className={`form-input text-center text-2xl tracking-widest ${pinError ? 'border-danger-500' : ''}`}
            aria-describedby={pinError ? 'pin-error' : undefined}
          />
          {pinError && (
            <p id="pin-error" role="alert" className="form-error">
              {pinError}
            </p>
          )}
          <p className="text-xs text-gray-500 mt-2">
            現場の掲示物に記載されているPINを入力してください
          </p>
        </div>

        <div className="pt-4">
          <Button
            type="submit"
            loading={screen === 'verifying'}
            disabled={pin.length < 4}
          >
            確認する
          </Button>
        </div>
      </form>
    </div>
  )
}
