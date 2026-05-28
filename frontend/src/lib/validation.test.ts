/**
 * フォームバリデーション テスト
 *
 * カバー範囲:
 *   - normalizePhone / validatePhone
 *   - validateKana
 *   - validateBirthDate / getAgeWarning
 *   - validatePostalCode / normalizePostalCode
 *   - required, maxLength, validateFutureDate
 */

import { describe, it, expect } from 'vitest'
import {
  normalizePhone,
  validatePhone,
  validateKana,
  validateBirthDate,
  getAgeWarning,
  normalizePostalCode,
  validatePostalCode,
  required,
  maxLength,
  validateFutureDate,
} from './validation'

// =============================================================================
// 電話番号
// =============================================================================

describe('normalizePhone', () => {
  it('全角数字を半角に変換する', () => {
    expect(normalizePhone('０９０１２３４５６７８')).toBe('09012345678')
  })

  it('+81 プレフィックスを 0 に変換する', () => {
    expect(normalizePhone('+819012345678')).toBe('09012345678')
  })

  it('ハイフン・スペース・括弧を除去する', () => {
    expect(normalizePhone('090-1234-5678')).toBe('09012345678')
    expect(normalizePhone('(090) 1234 5678')).toBe('09012345678')
    expect(normalizePhone('（090）１２３４−５６７８')).toBe('09012345678')
  })

  it('既に正規化済みの番号はそのまま返す', () => {
    expect(normalizePhone('09012345678')).toBe('09012345678')
  })
})

describe('validatePhone', () => {
  it('正常な携帯番号（11桁）を受け付ける', () => {
    expect(validatePhone('09012345678')).toBeNull()
    expect(validatePhone('080-1234-5678')).toBeNull()
  })

  it('正常な固定電話番号（10桁）を受け付ける', () => {
    expect(validatePhone('0312345678')).toBeNull()
  })

  it('空文字はエラーを返す', () => {
    expect(validatePhone('')).not.toBeNull()
  })

  it('9桁以下はエラーを返す', () => {
    expect(validatePhone('090123456')).not.toBeNull()
  })

  it('12桁以上はエラーを返す', () => {
    expect(validatePhone('090123456789')).not.toBeNull()
  })

  it('0 で始まらない番号はエラーを返す', () => {
    expect(validatePhone('1901234567')).not.toBeNull()
  })

  it('数字以外が含まれるとエラーを返す', () => {
    expect(validatePhone('090-abcd-5678')).not.toBeNull()
  })

  it('+81 形式を正しく検証する', () => {
    expect(validatePhone('+819012345678')).toBeNull()
  })
})

// =============================================================================
// カタカナ
// =============================================================================

describe('validateKana', () => {
  it('全角カタカナのみを受け付ける', () => {
    expect(validateKana('タナカ')).toBeNull()
    expect(validateKana('タロウ')).toBeNull()
  })

  it('長音符・拗音・促音を受け付ける', () => {
    expect(validateKana('ヴァイオリン')).toBeNull()
    expect(validateKana('コーポレーション')).toBeNull()
    expect(validateKana('ショッキング')).toBeNull()
  })

  it('スペース（全角・半角）を含む名前を受け付ける', () => {
    expect(validateKana('タナカ タロウ')).toBeNull()
    expect(validateKana('タナカ　タロウ')).toBeNull()
  })

  it('空文字はエラーを返す', () => {
    const err = validateKana('', '姓カナ')
    expect(err).toContain('姓カナ')
  })

  it('ひらがなはエラーを返す', () => {
    expect(validateKana('たなか')).not.toBeNull()
  })

  it('漢字はエラーを返す', () => {
    expect(validateKana('田中')).not.toBeNull()
  })

  it('アルファベットはエラーを返す', () => {
    expect(validateKana('Tanaka')).not.toBeNull()
  })

  it('カスタムフィールド名をエラーメッセージに含める', () => {
    const err = validateKana('', '名カナ')
    expect(err).toBe('名カナを入力してください')
  })
})

// =============================================================================
// 生年月日
// =============================================================================

describe('validateBirthDate', () => {
  it('正常な過去の日付を受け付ける', () => {
    expect(validateBirthDate('1990-01-15')).toBeNull()
    expect(validateBirthDate('1955-12-31')).toBeNull()
  })

  it('空文字はエラーを返す', () => {
    expect(validateBirthDate('')).not.toBeNull()
  })

  it('未来の日付はエラーを返す', () => {
    const future = new Date()
    future.setFullYear(future.getFullYear() + 1)
    expect(validateBirthDate(future.toISOString().slice(0, 10))).not.toBeNull()
  })

  it('120年以上前の日付はエラーを返す', () => {
    expect(validateBirthDate('1900-01-01')).not.toBeNull()
  })

  it('不正な日付文字列はエラーを返す', () => {
    expect(validateBirthDate('not-a-date')).not.toBeNull()
  })
})

describe('getAgeWarning', () => {
  it('15歳以上75歳未満は警告なし', () => {
    const d = new Date()
    d.setFullYear(d.getFullYear() - 30)
    expect(getAgeWarning(d.toISOString().slice(0, 10))).toBeNull()
  })

  it('15歳未満は警告を返す', () => {
    const d = new Date()
    d.setFullYear(d.getFullYear() - 10)
    const warn = getAgeWarning(d.toISOString().slice(0, 10))
    expect(warn).toContain('15歳未満')
  })

  it('75歳以上は警告を返す', () => {
    const d = new Date()
    d.setFullYear(d.getFullYear() - 80)
    const warn = getAgeWarning(d.toISOString().slice(0, 10))
    expect(warn).toContain('高齢者')
  })

  it('空文字は null を返す', () => {
    expect(getAgeWarning('')).toBeNull()
  })
})

// =============================================================================
// 郵便番号
// =============================================================================

describe('normalizePostalCode', () => {
  it('ハイフンを除去する', () => {
    expect(normalizePostalCode('123-4567')).toBe('1234567')
  })

  it('全角数字を半角に変換する', () => {
    expect(normalizePostalCode('１２３４５６７')).toBe('1234567')
  })
})

describe('validatePostalCode', () => {
  it('7桁の数字を受け付ける', () => {
    expect(validatePostalCode('1234567')).toBeNull()
    expect(validatePostalCode('123-4567')).toBeNull()
  })

  it('空文字は null を返す（任意項目）', () => {
    expect(validatePostalCode('')).toBeNull()
  })

  it('6桁以下はエラーを返す', () => {
    expect(validatePostalCode('123456')).not.toBeNull()
  })

  it('8桁以上はエラーを返す', () => {
    expect(validatePostalCode('12345678')).not.toBeNull()
  })
})

// =============================================================================
// 必須チェック
// =============================================================================

describe('required', () => {
  it('値がある場合は null を返す', () => {
    expect(required('値あり', 'フィールド')).toBeNull()
    expect(required(true, 'フィールド')).toBeNull()
  })

  it('空文字はエラーを返す', () => {
    expect(required('', '名前')).not.toBeNull()
  })

  it('null はエラーを返す', () => {
    expect(required(null, '名前')).not.toBeNull()
  })

  it('undefined はエラーを返す', () => {
    expect(required(undefined, '名前')).not.toBeNull()
  })

  it('false はエラーを返す', () => {
    expect(required(false, '同意')).not.toBeNull()
  })

  it('エラーメッセージにフィールド名を含める', () => {
    expect(required('', '電話番号')).toContain('電話番号')
  })
})

// =============================================================================
// 文字数チェック
// =============================================================================

describe('maxLength', () => {
  it('最大文字数以内は null を返す', () => {
    expect(maxLength('abc', 10, 'フィールド')).toBeNull()
    expect(maxLength('1234567890', 10, 'フィールド')).toBeNull()
  })

  it('最大文字数超過はエラーを返す', () => {
    const err = maxLength('12345678901', 10, 'フィールド')
    expect(err).not.toBeNull()
    expect(err).toContain('10文字以内')
  })

  it('空文字は null を返す', () => {
    expect(maxLength('', 10, 'フィールド')).toBeNull()
  })
})

// =============================================================================
// 未来日バリデーション
// =============================================================================

describe('validateFutureDate', () => {
  it('正常な日付を受け付ける', () => {
    expect(validateFutureDate('2025-01-01', '予定日')).toBeNull()
  })

  it('空文字は null を返す（任意項目）', () => {
    expect(validateFutureDate('', '予定日')).toBeNull()
  })

  it('不正な日付文字列はエラーを返す', () => {
    const err = validateFutureDate('not-a-date', '健康診断日')
    expect(err).toContain('健康診断日')
  })
})
