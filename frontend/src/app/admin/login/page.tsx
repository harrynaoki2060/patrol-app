'use client'

export const dynamic = 'force-dynamic'

/**
 * /admin/login — 管理者ログインページ
 */

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAdminAuth } from '@/lib/context/AdminAuthContext'
import { ApiError } from '@/lib/api/client'
import { Button } from '@/components/ui/Button'
import { InputField } from '@/components/ui/FormField'
import { ErrorBanner } from '@/components/ui/ErrorBanner'

export default function AdminLoginPage() {
  const router = useRouter()
  const { login, isAuthenticated, isLoading } = useAdminAuth()

  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [error,    setError]    = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // 既にログイン済みなら pending へ
  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.replace('/admin/pending')
    }
  }, [isLoading, isAuthenticated, router])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!email.trim() || !password) {
      setError('メールアドレスとパスワードを入力してください')
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      await login({ email: email.trim(), password })
      router.replace('/admin/pending')
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401 || err.status === 423) {
          setError('メールアドレスまたはパスワードが正しくありません')
        } else if (err.status === 0) {
          setError('ネットワークに接続できません')
        } else {
          setError('ログインに失敗しました。しばらくしてから再試行してください')
        }
      } else {
        setError('予期しないエラーが発生しました')
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (isLoading) return null

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-sm space-y-6">
        {/* ヘッダー */}
        <div className="text-center">
          <div className="text-5xl mb-3">🔐</div>
          <h1 className="text-2xl font-bold text-gray-900">管理者ログイン</h1>
          <p className="text-gray-500 text-sm mt-1">建設工事 新規入場管理システム</p>
        </div>

        {/* フォーム */}
        <form onSubmit={handleSubmit} className="card space-y-4">
          {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

          <InputField
            label="メールアドレス"
            required
            value={email}
            onChange={setEmail}
            type="email"
            inputMode="email"
            placeholder="admin@example.com"
            autoFocus
            autoComplete="email"
          />

          <InputField
            label="パスワード"
            required
            value={password}
            onChange={setPassword}
            type="password"
            autoComplete="current-password"
          />

          <Button type="submit" loading={submitting}>
            ログイン
          </Button>
        </form>

        <p className="text-xs text-gray-400 text-center">
          アカウントについては管理者にお問い合わせください
        </p>
      </div>
    </div>
  )
}
