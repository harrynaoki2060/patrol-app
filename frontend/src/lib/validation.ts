/**
 * フロントエンド フォームバリデーション
 *
 * バックエンド app/core/validators.py と同様のロジックをフロント側でも実装し、
 * 即時フィードバックを提供する（API 往復不要）。
 */

// =============================================================================
// 電話番号
// =============================================================================

/** 全角数字・ハイフン・括弧を正規化して数字のみにする */
export function normalizePhone(phone: string): string {
  // 全角 → 半角
  let s = phone.normalize('NFKC')
  // +81 → 0
  s = s.replace(/^\+81/, '0')
  // ハイフン・スペース・括弧を除去
  s = s.replace(/[-\s()（）]/g, '')
  return s
}

export function validatePhone(phone: string): string | null {
  const normalized = normalizePhone(phone)
  if (!normalized) return '電話番号を入力してください'
  if (!/^\d+$/.test(normalized)) return '電話番号は数字のみで入力してください'
  if (normalized.length < 10 || normalized.length > 11) {
    return '電話番号は10〜11桁で入力してください'
  }
  if (!normalized.startsWith('0')) {
    return '電話番号は0から始まる番号を入力してください'
  }
  return null
}

// =============================================================================
// カタカナ
// =============================================================================

export function validateKana(value: string, fieldName = 'カナ'): string | null {
  if (!value.trim()) return `${fieldName}を入力してください`
  if (!/^[ァ-ヶーヴ\s　]+$/.test(value)) {
    return `${fieldName}はカタカナで入力してください`
  }
  return null
}

// =============================================================================
// 生年月日
// =============================================================================

export function validateBirthDate(value: string): string | null {
  if (!value) return '生年月日を入力してください'
  const d = new Date(value)
  if (isNaN(d.getTime())) return '正しい日付を入力してください'
  const now = new Date()
  if (d > now) return '生年月日は今日以前の日付を入力してください'
  const minDate = new Date()
  minDate.setFullYear(minDate.getFullYear() - 120)
  if (d < minDate) return '正しい生年月日を入力してください'
  return null
}

export function getAgeWarning(value: string): string | null {
  if (!value) return null
  const d = new Date(value)
  if (isNaN(d.getTime())) return null
  const now = new Date()
  const age = now.getFullYear() - d.getFullYear()
    - (now < new Date(now.getFullYear(), d.getMonth(), d.getDate()) ? 1 : 0)
  if (age < 15) return `年齢が${age}歳です。15歳未満の場合は要確認`
  if (age >= 75) return `年齢が${age}歳です。高齢者の場合は体調を確認してください`
  return null
}

// =============================================================================
// 郵便番号
// =============================================================================

export function normalizePostalCode(value: string): string {
  return value.normalize('NFKC').replace(/[-\s]/g, '')
}

export function validatePostalCode(value: string): string | null {
  if (!value) return null // 任意項目
  const normalized = normalizePostalCode(value)
  if (!/^\d{7}$/.test(normalized)) return '郵便番号は7桁の数字で入力してください'
  return null
}

// =============================================================================
// 必須チェック
// =============================================================================

export function required(value: string | boolean | null | undefined, label: string): string | null {
  if (value === null || value === undefined || value === '' || value === false) {
    return `${label}を入力してください`
  }
  return null
}

// =============================================================================
// 日付（未来日 OK）
// =============================================================================

export function validateFutureDate(value: string, label: string): string | null {
  if (!value) return null  // 任意項目は呼び出し元でチェック
  const d = new Date(value)
  if (isNaN(d.getTime())) return `${label}は正しい日付を入力してください`
  return null
}

// =============================================================================
// テキスト長
// =============================================================================

export function maxLength(value: string, max: number, label: string): string | null {
  if (value && value.length > max) return `${label}は${max}文字以内で入力してください`
  return null
}
