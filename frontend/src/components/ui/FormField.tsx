/**
 * FormField — ラベル + input + エラー/ヒントをまとめたコンポーネント
 *
 * スマホ最適化:
 * - min-height 48px のタップ領域
 * - エラーは赤字で即時表示
 * - type="tel" など、inputMode も受け付ける
 */

import React, { useId } from 'react'

interface FormFieldProps {
  label: string
  error?: string | null
  hint?: string
  required?: boolean
  children?: React.ReactNode  // custom input（select等）を渡す場合
}

interface InputFieldProps extends FormFieldProps {
  value: string
  onChange: (value: string) => void
  type?: string
  inputMode?: React.HTMLAttributes<HTMLInputElement>['inputMode']
  placeholder?: string
  autoFocus?: boolean
  autoComplete?: string
  maxLength?: number
  readOnly?: boolean
}

/** テキスト入力フィールド */
export function InputField({
  label,
  error,
  hint,
  required,
  value,
  onChange,
  type = 'text',
  inputMode,
  placeholder,
  autoFocus,
  autoComplete,
  maxLength,
  readOnly,
}: InputFieldProps) {
  const id = useId()
  return (
    <div>
      <label htmlFor={id} className="form-label">
        {label}
        {required && <span className="text-danger-600 ml-1" aria-hidden>*</span>}
      </label>
      <input
        id={id}
        type={type}
        inputMode={inputMode}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
        autoComplete={autoComplete}
        maxLength={maxLength}
        readOnly={readOnly}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
        className={`form-input ${error ? 'border-danger-500 focus:border-danger-500 focus:ring-danger-500/20' : ''} ${readOnly ? 'bg-gray-50 text-gray-500' : ''}`}
      />
      {error && (
        <p id={`${id}-error`} role="alert" className="form-error">
          {error}
        </p>
      )}
      {!error && hint && (
        <p id={`${id}-hint`} className="text-xs text-gray-500 mt-1">
          {hint}
        </p>
      )}
    </div>
  )
}

/** セレクトフィールド */
interface SelectFieldProps extends FormFieldProps {
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
}

export function SelectField({
  label,
  error,
  hint,
  required,
  value,
  onChange,
  options,
}: SelectFieldProps) {
  const id = useId()
  return (
    <div>
      <label htmlFor={id} className="form-label">
        {label}
        {required && <span className="text-danger-600 ml-1" aria-hidden>*</span>}
      </label>
      <select
        id={id}
        value={value}
        onChange={e => onChange(e.target.value)}
        aria-invalid={!!error}
        className={`form-input ${error ? 'border-danger-500' : ''}`}
      >
        <option value="">選択してください</option>
        {options.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      {error && <p role="alert" className="form-error">{error}</p>}
      {!error && hint && <p className="text-xs text-gray-500 mt-1">{hint}</p>}
    </div>
  )
}

/** チェックボックスフィールド */
interface CheckFieldProps {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
  description?: string
  error?: string | null
  required?: boolean
}

export function CheckField({
  label,
  checked,
  onChange,
  description,
  error,
  required,
}: CheckFieldProps) {
  const id = useId()
  return (
    <div>
      <label htmlFor={id} className="flex items-start gap-3 cursor-pointer">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={e => onChange(e.target.checked)}
          className="mt-1 w-5 h-5 min-w-[20px] rounded border-gray-300 text-primary-600 focus:ring-primary-500"
          aria-required={required}
        />
        <span>
          <span className="text-sm font-medium text-gray-700">
            {label}
            {required && <span className="text-danger-600 ml-1" aria-hidden>*</span>}
          </span>
          {description && (
            <span className="block text-xs text-gray-500 mt-0.5">{description}</span>
          )}
        </span>
      </label>
      {error && <p role="alert" className="form-error mt-1">{error}</p>}
    </div>
  )
}
