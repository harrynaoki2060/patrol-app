'use client'

/**
 * /entry/[token]/quick — 超短縮再入場フロー
 *
 * 目標: 既存作業員が 30 秒以内で入場申請を完了できる。
 *
 * フロー:
 *   Screen 1: 電話番号 + 生年月日(月日) 入力 → quick-match API
 *   Screen 2 (matched): 氏名確認 + 入場日 + 健康チェック + 同意 → draft create + submit
 *   Screen 3 (not matched): 「通常フォームへ」案内
 *
 * セキュリティ:
 *   - entry_session_token が必要（QR 認証済みのセッション）
 *   - トークンがない場合は QR ページへリダイレクト
 */

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { quickMatchWorker, createDraft, updateDraft, submitEntry } from '@/lib/api/public'
import { ApiError } from '@/lib/api/client'
import { Button } from '@/components/ui/Button'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import type { WorkerSummary } from '@/types/api'

const SESSION_TOKEN_KEY = 'entry_session_token'

type Screen = 'input' | 'matching' | 'confirm' | 'submitting' | 'done' | 'no_match' | 'error'

// 今日の日付を YYYY-MM-DD で返す（JST 考慮）
function todayJst(): string {
  const now = new Date()
  const jst = new Date(now.getTime() + 9 * 60 * 60 * 1000)
  return jst.toISOString().slice(0, 10)
}

export default function QuickEntryPage() {
  const params = useParams()
  const token = params.token as string
  const router = useRouter()

  // Screen 1 — 入力
  const [phone, setPhone]           = useState('')
  const [birthMonth, setBirthMonth] = useState('')
  const [birthDay, setBirthDay]     = useState('')
  const [inputError, setInputError] = useState<string | null>(null)

  // Screen 2 — 確認
  const [worker, setWorker]               = useState<WorkerSummary | null>(null)
  const [plannedDate, setPlannedDate]     = useState(todayJst())
  const [hasHealth, setHasHealth]         = useState(false)
  const [consentAgreed, setConsentAgreed] = useState(false)

  // General
  const [screen, setScreen]   = useState<Screen>('input')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [receiptNumber, setReceiptNumber] = useState<string | null>(null)

  // sessionToken を取得
  const [sessionToken, setSessionToken] = useState<string | null>(null)

  useEffect(() => {
    const tok = sessionStorage.getItem(SESSION_TOKEN_KEY)
    if (!tok) {
      // QR 認証が済んでいない → QR ページへ
      router.replace(`/entry/${token}`)
      return
    }
    setSessionToken(tok)
  }, [token, router])

  // ============================
  // Screen 1: quick-match 実行
  // ============================
  async function handleMatch(e: React.FormEvent) {
    e.preventDefault()
    setInputError(null)

    const m = parseInt(birthMonth, 10)
    const d = parseInt(birthDay, 10)

    if (!phone.trim()) {
      setInputError('電話番号を入力してください')
      return
    }
    if (!birthMonth || m < 1 || m > 12) {
      setInputError('生まれ月を正しく入力してください（1〜12）')
      return
    }
    if (!birthDay || d < 1 || d > 31) {
      setInputError('生まれ日を正しく入力してください（1〜31）')
      return
    }
    if (!sessionToken) {
  router.replace(`/entry/${token}`)
  return
}

    setScreen('matching')
    try {
      const res = await quickMatchWorker(
        { phone, birth_month: m, birth_day: d },
        sessionToken,
      )
      if (res.matched && res.worker) {
        setWorker(res.worker)
        setScreen('confirm')
      } else {
        setScreen('no_match')
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 0) {
        setErrorMsg('ネットワークに接続できません。WiFi や電波を確認してください')
      } else {
        setErrorMsg('照合中にエラーが発生しました。もう一度お試しください')
      }
      setScreen('error')
    }
  }

  // ============================
  // Screen 2: draft + submit
  // ============================
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!consentAgreed) {
      setInputError('個人情報の取り扱いに同意してください')
      return
    }
    if (!worker || !sessionToken) return

    setScreen('submitting')
    setInputError(null)
    try {
      // 1. Draft 作成（既存作業員の worker_id を指定）
      const draft = await createDraft(
        { phone, worker_id: worker.id },
        sessionToken,
      )

      // 2. Draft を更新（入場日・健康・同意）
      await updateDraft(
        draft.id,
        {
          planned_entry_date: plannedDate || undefined,
          has_health_check: hasHealth,
          consent_agreed: true,
        },
        sessionToken,
      )

      // 3. 申請確定
      const submitted = await submitEntry(draft.id, sessionToken)
      setReceiptNumber(submitted.receipt_number)
      setScreen('done')
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setErrorMsg('この現場への申請がすでに存在します')
        } else if (err.status === 0) {
          setErrorMsg('ネットワークに接続できません')
        } else {
          setErrorMsg('申請中にエラーが発生しました。もう一度お試しください')
        }
      } else {
        setErrorMsg('予期しないエラーが発生しました')
      }
      setScreen('confirm') // confirm 画面に戻る
    }
  }

  // ============================
  // ローディング
  // ============================
  if (screen === 'matching' || screen === 'submitting') {
    return (
      <div className="min-h-screen bg-primary-600 flex flex-col items-center justify-center p-6">
        <div className="text-center text-white">
          <div className="text-5xl mb-6">⚡</div>
          <p className="text-xl font-bold mb-2">
            {screen === 'matching' ? '照合中...' : '申請送信中...'}
          </p>
          <p className="text-primary-200 text-sm">このまましばらくお待ちください</p>
        </div>
      </div>
    )
  }

  // ============================
  // 完了画面
  // ============================
  if (screen === 'done') {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-6">
        <div className="text-center">
          <div className="text-7xl mb-4">✅</div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">申請完了</h1>
          <p className="text-gray-600 mb-6">担当者の承認をお待ちください</p>
          {receiptNumber && (
            <div className="bg-white border border-gray-200 rounded-xl p-4 mb-6 text-left">
              <p className="text-xs text-gray-500 mb-1">受付番号</p>
              <p className="text-2xl font-mono font-bold text-primary-700 tracking-widest">
                {receiptNumber}
              </p>
              <p className="text-xs text-gray-400 mt-2">
                この番号を担当者にお伝えください
              </p>
            </div>
          )}
        </div>
      </div>
    )
  }

  // ============================
  // 照合失敗画面
  // ============================
  if (screen === 'no_match') {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col p-6">
        <div className="flex-1 flex flex-col items-center justify-center">
          <div className="text-6xl mb-4">🔍</div>
          <h1 className="text-xl font-bold text-gray-900 mb-3 text-center">
            一致する登録が見つかりません
          </h1>
          <div className="card w-full max-w-sm mb-6">
            <p className="text-sm text-gray-700 leading-relaxed">
              入力された電話番号・生年月日と一致する登録がありませんでした。
              通常の入場フォームから新規登録または再入力をしてください。
            </p>
          </div>
          <div className="w-full max-w-sm space-y-3">
            <Button
              onClick={() => router.replace(`/entry/${token}/form`)}
            >
              通常フォームで申請する
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setScreen('input')
                setPhone('')
                setBirthMonth('')
                setBirthDay('')
                setInputError(null)
              }}
            >
              入力しなおす
            </Button>
          </div>
        </div>
      </div>
    )
  }

  // ============================
  // エラー画面
  // ============================
  if (screen === 'error') {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col p-6">
        <div className="flex-1 flex flex-col items-center justify-center">
          <div className="text-6xl mb-4">❌</div>
          <div className="card w-full max-w-sm mb-6">
            <p className="text-sm text-gray-700">{errorMsg}</p>
          </div>
          <div className="w-full max-w-sm space-y-3">
            <Button onClick={() => { setScreen('input'); setErrorMsg(null) }}>
              もう一度試す
            </Button>
            <Button
              variant="secondary"
              onClick={() => router.replace(`/entry/${token}/form`)}
            >
              通常フォームへ
            </Button>
          </div>
        </div>
      </div>
    )
  }

  // ============================
  // Screen 2: 確認・送信
  // ============================
  if (screen === 'confirm' && worker) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col">
        {/* ヘッダー */}
        <div className="bg-primary-600 px-4 pt-12 pb-6 text-white text-center">
          <div className="text-3xl mb-2">⚡</div>
          <h1 className="text-xl font-bold">登録情報を確認</h1>
          <p className="text-primary-200 text-sm mt-1">以下の情報で申請します</p>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 p-6 space-y-5">
          {/* 氏名確認 */}
          <div className="card">
            <p className="text-xs text-gray-500 mb-1">氏名</p>
            <p className="text-2xl font-bold text-gray-900">
              {worker.last_name} {worker.first_name}
            </p>
            {worker.last_name_kana && (
              <p className="text-sm text-gray-500">
                {worker.last_name_kana} {worker.first_name_kana}
              </p>
            )}
            {worker.affiliation_company && (
              <p className="text-sm text-gray-600 mt-2">
                📢 {worker.affiliation_company}
              </p>
            )}
            {worker.job_title && (
              <p className="text-sm text-gray-600">
                🔧 {worker.job_title}
              </p>
            )}
          </div>

          {/* エラー表示 */}
          {(inputError || errorMsg) && (
            <ErrorBanner
              type="error"
              message={inputError || errorMsg || ''}
            />
          )}

          {/* 入場予定日 */}
          <div>
            <label className="form-label" htmlFor="planned-date">
              入場予定日
            </label>
            <input
              id="planned-date"
              type="date"
              value={plannedDate}
              onChange={e => setPlannedDate(e.target.value)}
              className="form-input"
            />
          </div>

          {/* 健康チェック */}
          <label className="flex items-center gap-3 min-h-[48px] cursor-pointer">
            <input
              type="checkbox"
              checked={hasHealth}
              onChange={e => setHasHealth(e.target.checked)}
              className="w-5 h-5 rounded border-gray-300 text-primary-600 flex-shrink-0"
            />
            <span className="text-sm text-gray-700">
              本日、体温・体調確認済みです
            </span>
          </label>

          {/* 個人情報同意 */}
          <label className="flex items-start gap-3 min-h-[48px] cursor-pointer">
            <input
              type="checkbox"
              checked={consentAgreed}
              onChange={e => {
                setConsentAgreed(e.target.checked)
                if (inputError?.includes('同意')) setInputError(null)
              }}
              className="mt-1 w-5 h-5 rounded border-gray-300 text-primary-600 flex-shrink-0"
            />
            <span className="text-sm text-gray-700">
              個人情報の取り扱いに同意します
              <span className="text-danger-600 ml-1">*</span>
            </span>
          </label>

          {/* 送信ボタン */}
          <div className="pt-2 space-y-3">
            <Button
              type="submit"
              disabled={!consentAgreed}
              loading={false}
            >
              申請する
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setScreen('input')
                setWorker(null)
                setInputError(null)
                setErrorMsg(null)
              }}
            >
              戻る
            </Button>
          </div>
        </form>
      </div>
    )
  }

  // ============================
  // Screen 1: 入力
  // ============================
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* ヘッダー */}
      <div className="bg-primary-600 px-4 pt-12 pb-8 text-white text-center">
        <div className="text-4xl mb-3">⚡</div>
        <h1 className="text-xl font-bold">かんたん再入場</h1>
        <p className="text-primary-200 text-sm mt-1">
          過去に登録済みの方はこちらから
        </p>
      </div>

      <form onSubmit={handleMatch} className="flex-1 p-6 space-y-6">
        <p className="text-sm text-gray-600">
          電話番号と生年月日（月・日）を入力してください。
        </p>

        {inputError && (
          <ErrorBanner type="error" message={inputError} />
        )}

        {/* 電話番号 */}
        <div>
          <label className="form-label" htmlFor="phone-input">
            電話番号
            <span className="text-danger-600 ml-1">*</span>
          </label>
          <input
            id="phone-input"
            type="tel"
            inputMode="numeric"
            value={phone}
            onChange={e => {
              setPhone(e.target.value)
              setInputError(null)
            }}
            placeholder="例: 090-1234-5678"
            autoFocus
            autoComplete="tel"
            className="form-input"
          />
        </div>

        {/* 生年月日（月・日） */}
        <div>
          <p className="form-label">
            生まれた月・日
            <span className="text-danger-600 ml-1">*</span>
          </p>
          <div className="flex gap-3 items-center">
            <div className="flex-1">
              <input
                type="number"
                inputMode="numeric"
                min={1}
                max={12}
                value={birthMonth}
                onChange={e => {
                  setBirthMonth(e.target.value)
                  setInputError(null)
                }}
                placeholder="月"
                className="form-input text-center text-xl"
              />
              <p className="text-xs text-center text-gray-500 mt-1">月</p>
            </div>
            <span className="text-2xl text-gray-400 font-light">—</span>
            <div className="flex-1">
              <input
                type="number"
                inputMode="numeric"
                min={1}
                max={31}
                value={birthDay}
                onChange={e => {
                  setBirthDay(e.target.value)
                  setInputError(null)
                }}
                placeholder="日"
                className="form-input text-center text-xl"
              />
              <p className="text-xs text-center text-gray-500 mt-1">日</p>
            </div>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            例: 3 月 15 日生まれ → 3 / 15
          </p>
        </div>

        <div className="pt-2 space-y-3">
          <Button type="submit" loading={false}>
            照合する
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => router.replace(`/entry/${token}/form`)}
          >
            通常フォームへ（初めての方・登録変更）
          </Button>
        </div>
      </form>
    </div>
  )
}
