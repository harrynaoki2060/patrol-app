'use client'

/**
 * /entry/[token]/form — 入場申請フォーム（5ステップ）
 *
 * ステップ構成:
 *   Step 1: 電話番号入力 → 作業員検索
 *   Step 1b: 既存作業員の再利用確認（作業員が見つかった場合）
 *   Step 2: お名前・カナ（新規作業員のみ変更可）
 *   Step 3: 生年月日・性別・職種
 *   Step 4: 緊急連絡先・住所
 *   Step 5: 入場情報・同意 → 申請送信
 *
 * セキュリティ:
 *   - entry_session_token を sessionStorage から取得
 *   - 存在しない場合は / へリダイレクト
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter, useParams } from 'next/navigation'

import { lookupWorker, createDraft, updateDraft, submitEntry } from '@/lib/api/public'
import { ApiError } from '@/lib/api/client'
import { useAutosave }     from '@/lib/hooks/useAutosave'
import { useOnlineStatus } from '@/lib/hooks/useOnlineStatus'
import { useBeforeUnload } from '@/lib/hooks/useBeforeUnload'

import {
  validatePhone, normalizePhone,
  validateKana, validateBirthDate, getAgeWarning,
  validatePostalCode, required,
} from '@/lib/validation'

import { Button }       from '@/components/ui/Button'
import { InputField, SelectField, CheckField } from '@/components/ui/FormField'
import { StepHeader }   from '@/components/ui/StepHeader'
import { FixedBottom }  from '@/components/ui/FixedBottom'
import { SaveIndicator } from '@/components/ui/SaveIndicator'
import { ErrorBanner, OfflineBanner } from '@/components/ui/ErrorBanner'
import { Spinner } from '@/components/ui/Spinner'

import type { DraftUpdateRequest, PublicSiteInfo, SubmitResponse, WorkerSummary } from '@/types/api'

// ============================================================
// 定数
// ============================================================
const SESSION_TOKEN_KEY = 'entry_session_token'
const SITE_INFO_KEY     = 'entry_site_info'

const GENDER_OPTIONS = [
  { value: 'male',   label: '男性' },
  { value: 'female', label: '女性' },
  { value: 'other',  label: 'その他' },
]

const WORKER_TYPE_OPTIONS = [
  { value: 'company_employee', label: '協力会社社員' },
  { value: 'sole_proprietor',  label: '一人親方' },
  { value: 'part_time',        label: 'アルバイト・パート' },
]

const BLOOD_TYPE_OPTIONS = [
  { value: 'A',       label: 'A型' },
  { value: 'B',       label: 'B型' },
  { value: 'O',       label: 'O型' },
  { value: 'AB',      label: 'AB型' },
  { value: 'unknown', label: '不明' },
]

// ============================================================
// Form state
// ============================================================
interface FormData {
  phone:        string
  last_name:    string
  first_name:   string
  last_name_kana:  string
  first_name_kana: string
  birth_date:   string
  gender:       string
  blood_type:   string
  worker_type:  string
  job_title:    string
  affiliation_company: string
  emergency_contact:         string
  emergency_contact_name:    string
  emergency_contact_relation: string
  postal_code:  string
  address:      string
  planned_entry_date: string
  has_health_check:   boolean
  health_check_date:  string
  consent_agreed:     boolean
}

const INITIAL_FORM: FormData = {
  phone: '', last_name: '', first_name: '',
  last_name_kana: '', first_name_kana: '',
  birth_date: '', gender: '', blood_type: 'unknown',
  worker_type: 'company_employee', job_title: '', affiliation_company: '',
  emergency_contact: '', emergency_contact_name: '', emergency_contact_relation: '',
  postal_code: '', address: '',
  planned_entry_date: '', has_health_check: false, health_check_date: '',
  consent_agreed: false,
}

type FormStep = 1 | 2 | 3 | 4 | 5

// ============================================================
// メインコンポーネント
// ============================================================
export default function EntryFormPage() {
  const router = useRouter()
  const params = useParams<{ token: string }>()

  // セッション
  const [sessionToken, setSessionToken] = useState<string | null>(null)
  const [siteInfo, setSiteInfo]         = useState<PublicSiteInfo | null>(null)

  // フォーム状態
  const [form, setForm]   = useState<FormData>(INITIAL_FORM)
  const [step, setStep]   = useState<FormStep>(1)
  const [errors, setErrors] = useState<Partial<Record<keyof FormData, string>>>({})
  const [globalError, setGlobalError] = useState<string | null>(null)

  // 作業員
  const [foundWorker,    setFoundWorker]    = useState<WorkerSummary | null>(null)
  const [useExisting,    setUseExisting]    = useState<boolean | null>(null)
  const [isLookingUp,    setIsLookingUp]    = useState(false)
  const [showReusePrompt, setShowReusePrompt] = useState(false)

  // Draft
  const [entryId,       setEntryId]       = useState<string | null>(null)
  const [receiptNumber, setReceiptNumber] = useState<string | null>(null)
  const [isDirty,       setIsDirty]       = useState(false)
  const [isSubmitting,  setIsSubmitting]  = useState(false)
  const [submitResult,  setSubmitResult]  = useState<SubmitResponse | null>(null)

  const isOnline = useOnlineStatus()

  // ---------------------------------------------------------------------------
  // セッション取得
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const token = sessionStorage.getItem(SESSION_TOKEN_KEY)
    const siteRaw = sessionStorage.getItem(SITE_INFO_KEY)
    if (!token) {
      router.replace('/')
      return
    }
    setSessionToken(token)
    if (siteRaw) {
      try { setSiteInfo(JSON.parse(siteRaw)) } catch { /* ignore */ }
    }
  }, [router])

  // ---------------------------------------------------------------------------
  // Autosave
  // ---------------------------------------------------------------------------
  const buildPatchData = useCallback((f: FormData): DraftUpdateRequest => {
    const d: DraftUpdateRequest = {}
    if (f.last_name)    d.last_name    = f.last_name
    if (f.first_name)   d.first_name   = f.first_name
    if (f.last_name_kana)  d.last_name_kana  = f.last_name_kana
    if (f.first_name_kana) d.first_name_kana = f.first_name_kana
    if (f.birth_date)   d.birth_date   = f.birth_date
    if (f.gender)       d.gender       = f.gender
    if (f.blood_type)   d.blood_type   = f.blood_type
    if (f.worker_type)  d.worker_type  = f.worker_type
    if (f.job_title)    d.job_title    = f.job_title
    if (f.affiliation_company) d.affiliation_company = f.affiliation_company
    if (f.emergency_contact)   d.emergency_contact   = f.emergency_contact
    if (f.emergency_contact_name) d.emergency_contact_name = f.emergency_contact_name
    if (f.emergency_contact_relation) d.emergency_contact_relation = f.emergency_contact_relation
    if (f.postal_code)  d.postal_code  = f.postal_code
    if (f.address)      d.address      = f.address
    if (f.planned_entry_date) d.planned_entry_date = f.planned_entry_date
    d.has_health_check = f.has_health_check
    if (f.health_check_date) d.health_check_date = f.health_check_date
    if (f.consent_agreed)    d.consent_agreed     = f.consent_agreed
    return d
  }, [])

  const { status: saveStatus, lastSaved, triggerSave, flush } = useAutosave({
    data: form,
    enabled: !!entryId && !!sessionToken && isDirty,
    onSave: async (f) => {
      if (!entryId || !sessionToken) return
      await updateDraft(entryId, buildPatchData(f), sessionToken)
      setIsDirty(false)
    },
  })

  useBeforeUnload(flush, isDirty)

  // ---------------------------------------------------------------------------
  // フォーム更新ヘルパー
  // ---------------------------------------------------------------------------
  function updateField<K extends keyof FormData>(key: K, value: FormData[K]) {
    setForm(prev => ({ ...prev, [key]: value }))
    setErrors(prev => ({ ...prev, [key]: undefined }))
    setIsDirty(true)
    if (entryId) triggerSave()
  }

  // ---------------------------------------------------------------------------
  // Step 1: 電話番号検索
  // ---------------------------------------------------------------------------
  async function handlePhoneLookup() {
    const phoneErr = validatePhone(form.phone)
    if (phoneErr) { setErrors({ phone: phoneErr }); return }

    if (!sessionToken) return
    setIsLookingUp(true)
    setGlobalError(null)

    try {
      const normalized = normalizePhone(form.phone)
      const res = await lookupWorker({ phone: normalized }, sessionToken)

      if (res.exists && res.worker) {
        setFoundWorker(res.worker)
        setShowReusePrompt(true)
      } else {
        // 新規: name 入力へ
        setFoundWorker(null)
        setUseExisting(false)
        await handleCreateDraft(null)
        setStep(2)
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setGlobalError('セッションが切れました。QRコードを再度読み取ってください')
      } else if (err instanceof ApiError && err.status === 0) {
        setGlobalError('ネットワークに接続できません')
      } else {
        setGlobalError('エラーが発生しました。もう一度お試しください')
      }
    } finally {
      setIsLookingUp(false)
    }
  }

  async function handleReuseChoice(reuse: boolean) {
    setUseExisting(reuse)
    setShowReusePrompt(false)

    if (reuse && foundWorker) {
      // 既存作業員: worker データをフォームに反映
      setForm(prev => ({
        ...prev,
        last_name:    foundWorker.last_name,
        first_name:   foundWorker.first_name,
        last_name_kana:  foundWorker.last_name_kana ?? '',
        first_name_kana: foundWorker.first_name_kana ?? '',
        worker_type:  foundWorker.worker_type,
        affiliation_company: foundWorker.affiliation_company ?? '',
        job_title:    foundWorker.job_title ?? '',
      }))
      await handleCreateDraft(foundWorker.id)
    } else {
      // 新規として入力
      setFoundWorker(null)
      await handleCreateDraft(null)
    }
    setStep(2)
  }

  async function handleCreateDraft(workerId: string | null) {
    if (!sessionToken) return
    const normalized = normalizePhone(form.phone)
    try {
      const req = workerId
        ? { phone: normalized, worker_id: workerId }
        : { phone: normalized, last_name: form.last_name || '（未入力）', first_name: form.first_name || '（未入力）' }

      const draft = await createDraft(req, sessionToken)
      setEntryId(draft.id)
      setReceiptNumber(draft.receipt_number)

      // バックエンドの worker データでフォームを補完
      if (draft.worker) {
        const w = draft.worker
        setForm(prev => ({
          ...prev,
          last_name:    w.last_name || prev.last_name,
          first_name:   w.first_name || prev.first_name,
          last_name_kana:  w.last_name_kana  ?? prev.last_name_kana,
          first_name_kana: w.first_name_kana ?? prev.first_name_kana,
          birth_date:   w.birth_date ?? prev.birth_date,
          gender:       w.gender ?? prev.gender,
          blood_type:   w.blood_type ?? prev.blood_type,
          worker_type:  w.worker_type || prev.worker_type,
          affiliation_company: w.affiliation_company ?? prev.affiliation_company,
          job_title:    w.job_title ?? prev.job_title,
          postal_code:  w.postal_code ?? prev.postal_code,
          address:      w.address ?? prev.address,
          emergency_contact: w.emergency_contact ?? prev.emergency_contact,
          emergency_contact_name: w.emergency_contact_name ?? prev.emergency_contact_name,
        }))
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setGlobalError('この現場への申請が既に存在します。現場の担当者にご連絡ください')
      } else {
        setGlobalError('申請の作成に失敗しました。もう一度お試しください')
      }
      throw err
    }
  }

  // ---------------------------------------------------------------------------
  // ステップ間ナビゲーション
  // ---------------------------------------------------------------------------
  async function handleNext() {
    const errs = validateCurrentStep()
    if (Object.keys(errs).length > 0) { setErrors(errs); return }

    // ステップ遷移前に即時保存
    if (entryId && isDirty) await flush()

    if (step < 5) setStep((step + 1) as FormStep)
  }

  function handleBack() {
    setErrors({})
    setGlobalError(null)
    if (step === 2 && useExisting !== null) {
      // 名前ステップ → 電話番号に戻る
      setStep(1)
      setShowReusePrompt(false)
      setFoundWorker(null)
      setUseExisting(null)
      setEntryId(null)
      setReceiptNumber(null)
    } else if (step > 1) {
      setStep((step - 1) as FormStep)
    }
  }

  // ---------------------------------------------------------------------------
  // バリデーション
  // ---------------------------------------------------------------------------
  function validateCurrentStep(): Partial<Record<keyof FormData, string>> {
    const e: Partial<Record<keyof FormData, string>> = {}

    if (step === 1) {
      const phoneErr = validatePhone(form.phone)
      if (phoneErr) e.phone = phoneErr
    }

    if (step === 2) {
      if (!form.last_name.trim())   e.last_name   = '姓を入力してください'
      if (!form.first_name.trim())  e.first_name  = '名を入力してください'
      const kana1 = validateKana(form.last_name_kana, 'セイ')
      const kana2 = validateKana(form.first_name_kana, 'メイ')
      if (kana1) e.last_name_kana  = kana1
      if (kana2) e.first_name_kana = kana2
    }

    if (step === 3) {
      const bdErr = validateBirthDate(form.birth_date)
      if (bdErr) e.birth_date = bdErr
      if (!form.gender)     e.gender    = '性別を選択してください'
      if (!form.job_title.trim()) e.job_title = '職種を入力してください'
    }

    if (step === 4) {
      if (form.emergency_contact) {
        const ecErr = validatePhone(form.emergency_contact)
        if (ecErr) e.emergency_contact = ecErr
      } else {
        e.emergency_contact = '緊急連絡先を入力してください'
      }
      const pcErr = validatePostalCode(form.postal_code)
      if (pcErr) e.postal_code = pcErr
    }

    if (step === 5) {
      if (!form.planned_entry_date) e.planned_entry_date = '入場予定日を選択してください'
      if (!form.consent_agreed) e.consent_agreed = '個人情報の取り扱いに同意してください' as never
    }

    return e
  }

  // ---------------------------------------------------------------------------
  // 申請送信
  // ---------------------------------------------------------------------------
  async function handleSubmit() {
    const errs = validateCurrentStep()
    if (Object.keys(errs).length > 0) { setErrors(errs); return }

    if (!entryId || !sessionToken) return
    setIsSubmitting(true)
    setGlobalError(null)

    try {
      // 最終保存
      await flush()
      const result = await submitEntry(entryId, sessionToken)
      // セッション情報をクリア
      sessionStorage.removeItem(SESSION_TOKEN_KEY)
      sessionStorage.removeItem(SITE_INFO_KEY)
      setSubmitResult(result)
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 422) {
          setGlobalError('必須項目が不足しています。入力内容をご確認ください')
        } else if (err.status === 409) {
          setGlobalError('この申請は既に送信済みです')
        } else if (err.status === 0) {
          setGlobalError('ネットワークに接続できません。接続を確認してもう一度お試しください')
        } else {
          setGlobalError('送信に失敗しました。もう一度お試しください')
        }
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  // ===========================================================================
  // 送信完了画面
  // ===========================================================================
  if (submitResult) {
    return <SubmitComplete result={submitResult} />
  }

  // ===========================================================================
  // セッション未取得
  // ===========================================================================
  if (!sessionToken) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Spinner size="lg" className="text-primary-600" />
      </div>
    )
  }

  // ===========================================================================
  // 作業員再利用確認画面
  // ===========================================================================
  if (showReusePrompt && foundWorker) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col">
        <div className="bg-primary-600 px-4 pt-12 pb-6 text-white">
          <h1 className="text-xl font-bold">前回の情報が見つかりました</h1>
          <p className="text-primary-200 text-sm mt-1">この情報で申請しますか？</p>
        </div>

        <div className="p-4 space-y-4 flex-1">
          {globalError && <ErrorBanner message={globalError} onDismiss={() => setGlobalError(null)} />}

          <div className="card space-y-3">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-primary-100 flex items-center justify-center text-2xl flex-shrink-0">
                👷
              </div>
              <div>
                <p className="text-lg font-bold text-gray-900">
                  {foundWorker.last_name} {foundWorker.first_name}
                </p>
                {(foundWorker.last_name_kana || foundWorker.first_name_kana) && (
                  <p className="text-sm text-gray-500">
                    {foundWorker.last_name_kana} {foundWorker.first_name_kana}
                  </p>
                )}
              </div>
            </div>
            {foundWorker.affiliation_company && (
              <div className="flex gap-2 text-sm">
                <span className="text-gray-500">会社：</span>
                <span className="text-gray-800">{foundWorker.affiliation_company}</span>
              </div>
            )}
            {foundWorker.job_title && (
              <div className="flex gap-2 text-sm">
                <span className="text-gray-500">職種：</span>
                <span className="text-gray-800">{foundWorker.job_title}</span>
              </div>
            )}
          </div>

          <p className="text-sm text-gray-600 text-center">
            上記の情報で申請を続けますか？<br />
            変更がある場合は「いいえ」を選択して新規入力してください
          </p>
        </div>

        <FixedBottom>
          <div className="space-y-2">
            <Button onClick={() => handleReuseChoice(true)} loading={isLookingUp}>
              はい、この情報で申請する
            </Button>
            <Button variant="secondary" onClick={() => handleReuseChoice(false)}>
              いいえ、新しく入力する
            </Button>
          </div>
        </FixedBottom>
      </div>
    )
  }

  // ===========================================================================
  // メインフォーム
  // ===========================================================================
  const totalSteps = 5
  const stepTitles = ['電話番号', 'お名前', '個人情報', '連絡先・住所', '入場情報']

  const ageWarning = step === 3 ? getAgeWarning(form.birth_date) : null

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {!isOnline && <OfflineBanner />}

      {/* ヘッダー */}
      <div className={`${!isOnline ? 'mt-10' : ''}`}>
        <StepHeader
          currentStep={step}
          totalSteps={totalSteps}
          title={stepTitles[step - 1]}
          subtitle={siteInfo?.name}
        />
        <div className="px-4 pb-2 flex justify-between items-center">
          {receiptNumber && (
            <span className="text-xs text-gray-400">受付番号: {receiptNumber}</span>
          )}
          <div className="ml-auto">
            <SaveIndicator status={saveStatus} lastSaved={lastSaved} />
          </div>
        </div>
      </div>

      {/* フォームエリア */}
      <div className="flex-1 px-4 pb-4 space-y-5 overflow-y-auto">
        {globalError && (
          <ErrorBanner message={globalError} onDismiss={() => setGlobalError(null)} />
        )}

        {/* ===== STEP 1: 電話番号 ===== */}
        {step === 1 && (
          <>
            {/* 超短縮再入場フローへのショートカット */}
            <a
              href={`/entry/${params.token}/quick`}
              className="block w-full p-3 rounded-xl bg-primary-50 border border-primary-200 hover:bg-primary-100 transition-colors text-center"
            >
              <p className="text-sm font-bold text-primary-700">⚡ かんたん再入場（30秒）</p>
              <p className="text-xs text-primary-600 mt-0.5">
                登録済みの方: 電話番号 + 生年月日(月日)だけで申請できます
              </p>
            </a>

            <div className="relative flex items-center">
              <div className="flex-1 border-t border-gray-200" />
              <span className="px-3 text-xs text-gray-400">または通常フォームで入力</span>
              <div className="flex-1 border-t border-gray-200" />
            </div>

            <InputField
              label="電話番号"
              required
              value={form.phone}
              onChange={v => updateField('phone', v)}
              type="tel"
              inputMode="tel"
              placeholder="09012345678"
              autoFocus
              autoComplete="tel"
              error={errors.phone}
              hint="ハイフン不要。携帯・固定どちらでも可"
            />
          </>
        )}

        {/* ===== STEP 2: お名前 ===== */}
        {step === 2 && (
          <>
            {useExisting && foundWorker && (
              <div className="bg-primary-50 border border-primary-200 rounded-xl p-3 text-sm text-primary-800">
                ℹ️ 前回の情報が入力されています。変更がある場合は修正してください
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <InputField
                label="姓"
                required
                value={form.last_name}
                onChange={v => updateField('last_name', v)}
                placeholder="田中"
                autoFocus
                autoComplete="family-name"
                error={errors.last_name}
              />
              <InputField
                label="名"
                required
                value={form.first_name}
                onChange={v => updateField('first_name', v)}
                placeholder="太郎"
                autoComplete="given-name"
                error={errors.first_name}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <InputField
                label="セイ（カナ）"
                required
                value={form.last_name_kana}
                onChange={v => updateField('last_name_kana', v)}
                placeholder="タナカ"
                autoComplete="off"
                error={errors.last_name_kana}
              />
              <InputField
                label="メイ（カナ）"
                required
                value={form.first_name_kana}
                onChange={v => updateField('first_name_kana', v)}
                placeholder="タロウ"
                autoComplete="off"
                error={errors.first_name_kana}
              />
            </div>
            <SelectField
              label="所属区分"
              required
              value={form.worker_type}
              onChange={v => updateField('worker_type', v)}
              options={WORKER_TYPE_OPTIONS}
              error={errors.worker_type}
            />
            <InputField
              label="所属会社名"
              value={form.affiliation_company}
              onChange={v => updateField('affiliation_company', v)}
              placeholder="株式会社テスト建設"
              autoComplete="organization"
              error={errors.affiliation_company}
            />
          </>
        )}

        {/* ===== STEP 3: 個人情報 ===== */}
        {step === 3 && (
          <>
            <InputField
              label="生年月日"
              required
              value={form.birth_date}
              onChange={v => updateField('birth_date', v)}
              type="date"
              autoFocus
              error={errors.birth_date}
            />
            {ageWarning && (
              <ErrorBanner type="warning" message={ageWarning} />
            )}
            <SelectField
              label="性別"
              required
              value={form.gender}
              onChange={v => updateField('gender', v)}
              options={GENDER_OPTIONS}
              error={errors.gender}
            />
            <InputField
              label="職種・工種"
              required
              value={form.job_title}
              onChange={v => updateField('job_title', v)}
              placeholder="型枠大工"
              error={errors.job_title}
            />
            <SelectField
              label="血液型"
              value={form.blood_type}
              onChange={v => updateField('blood_type', v)}
              options={BLOOD_TYPE_OPTIONS}
              error={errors.blood_type}
              hint="わからない場合は「不明」を選択"
            />
          </>
        )}

        {/* ===== STEP 4: 連絡先・住所 ===== */}
        {step === 4 && (
          <>
            <InputField
              label="緊急連絡先（電話番号）"
              required
              value={form.emergency_contact}
              onChange={v => updateField('emergency_contact', v)}
              type="tel"
              inputMode="tel"
              placeholder="09012345678"
              autoFocus
              autoComplete="off"
              error={errors.emergency_contact}
              hint="ご家族や会社の連絡先"
            />
            <InputField
              label="緊急連絡先（お名前）"
              value={form.emergency_contact_name}
              onChange={v => updateField('emergency_contact_name', v)}
              placeholder="田中 花子"
              autoComplete="off"
              error={errors.emergency_contact_name}
            />
            <InputField
              label="緊急連絡先（続柄）"
              value={form.emergency_contact_relation}
              onChange={v => updateField('emergency_contact_relation', v)}
              placeholder="配偶者・会社など"
              autoComplete="off"
            />
            <InputField
              label="郵便番号"
              value={form.postal_code}
              onChange={v => updateField('postal_code', v)}
              inputMode="numeric"
              placeholder="1234567"
              error={errors.postal_code}
              hint="ハイフン不要（7桁）"
            />
            <InputField
              label="住所"
              value={form.address}
              onChange={v => updateField('address', v)}
              placeholder="東京都千代田区..."
              autoComplete="street-address"
            />
          </>
        )}

        {/* ===== STEP 5: 入場情報・同意 ===== */}
        {step === 5 && (
          <>
            <InputField
              label="入場予定日"
              required
              value={form.planned_entry_date}
              onChange={v => updateField('planned_entry_date', v)}
              type="date"
              autoFocus
              error={errors.planned_entry_date}
            />

            {siteInfo?.require_health_check && (
              <>
                <CheckField
                  label="健康診断を受診済みですか？"
                  checked={form.has_health_check}
                  onChange={v => updateField('has_health_check', v)}
                  description="直近1年以内の健康診断を受診している場合にチェック"
                />
                {form.has_health_check && (
                  <InputField
                    label="健康診断実施日"
                    value={form.health_check_date}
                    onChange={v => updateField('health_check_date', v)}
                    type="date"
                    error={errors.health_check_date}
                  />
                )}
              </>
            )}

            {/* 個人情報同意 */}
            <div className="card bg-gray-50 border-gray-200">
              <h3 className="text-sm font-semibold text-gray-800 mb-2">
                個人情報の取り扱いについて
              </h3>
              <p className="text-xs text-gray-600 leading-relaxed mb-3">
                入力いただいた個人情報は、建設工事の新規入場管理のみに使用します。
                第三者への提供は行いません。
                申請完了後、担当者が内容を確認いたします。
              </p>
              <CheckField
                label="個人情報の取り扱いに同意する"
                checked={form.consent_agreed}
                onChange={v => updateField('consent_agreed', v as FormData['consent_agreed'])}
                error={errors.consent_agreed as string}
                required
              />
            </div>
          </>
        )}
      </div>

      {/* 固定下部ボタン */}
      <FixedBottom>
        <div className={`space-y-2 ${step > 1 ? '' : ''}`}>
          {step < 5 ? (
            <Button
              onClick={step === 1 ? handlePhoneLookup : handleNext}
              loading={isLookingUp || (step === 1 && false)}
            >
              {step === 1 ? '次へ（作業員を検索）' : `次へ　${step + 1}/${totalSteps}`}
            </Button>
          ) : (
            <Button onClick={handleSubmit} loading={isSubmitting}>
              申請を送信する
            </Button>
          )}
          {step > 1 && (
            <Button variant="ghost" onClick={handleBack}>
              ← 戻る
            </Button>
          )}
        </div>
      </FixedBottom>
    </div>
  )
}

// ============================================================
// 送信完了コンポーネント
// ============================================================
function SubmitComplete({ result }: { result: SubmitResponse }) {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-sm space-y-5">
        {/* 成功アイコン */}
        <div className="text-center">
          <div className="text-6xl mb-3">✅</div>
          <h1 className="text-2xl font-bold text-gray-900">申請完了</h1>
          <p className="text-gray-500 text-sm mt-1">入場申請を受け付けました</p>
        </div>

        {/* 受付番号 */}
        <div className="card text-center border-2 border-primary-200 bg-primary-50">
          <p className="text-xs text-gray-500 mb-1">受付番号</p>
          <p className="text-3xl font-bold text-primary-700 tracking-widest font-mono">
            {result.receipt_number}
          </p>
          <p className="text-xs text-gray-500 mt-2">
            現場の担当者に提示してください
          </p>
        </div>

        {/* ステータス */}
        <div className="card flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-yellow-100 flex items-center justify-center text-xl flex-shrink-0">
            ⏳
          </div>
          <div>
            <p className="font-semibold text-gray-800">審査待ち</p>
            <p className="text-sm text-gray-500">
              担当者が内容を確認しています
            </p>
          </div>
        </div>

        {/* 現場名 */}
        {result.site_name && (
          <div className="text-center">
            <p className="text-sm text-gray-500">申請現場</p>
            <p className="font-medium text-gray-800">{result.site_name}</p>
          </div>
        )}

        {/* 注意事項 */}
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4 text-sm text-yellow-800">
          <p className="font-medium mb-1">⚠️ ご注意</p>
          <p>申請が承認されるまでは現場への入場はできません。担当者からの連絡をお待ちください。</p>
        </div>
      </div>
    </div>
  )
}
