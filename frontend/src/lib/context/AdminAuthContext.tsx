'use client'

/**
 * AdminAuthContext — 管理者認証状態の管理
 *
 * - access_token / refresh_token を sessionStorage に保管
 * - 401 発生時に自動リフレッシュを試みる
 * - Phase 8: ログアウト時にサーバー側で refresh_token を失効させる
 * - Phase 8: refresh 成功時に新しい refresh_token を保存（トークンローテーション）
 */

import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { adminLogin, adminRefresh, adminLogout, getMe, adminTokens } from '@/lib/api/auth'
import { ApiError } from '@/lib/api/client'
import type { CurrentUser, LoginRequest } from '@/types/api'

interface AdminAuthState {
  user: CurrentUser | null
  isLoading: boolean
  isAuthenticated: boolean
  login:  (req: LoginRequest) => Promise<void>
  logout: () => void
  getAccessToken: () => string | null
  /** 401 時に refresh を試みて新しい access_token を返す */
  refreshIfNeeded: () => Promise<string | null>
}

const AdminAuthContext = createContext<AdminAuthState | null>(null)

export function AdminAuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser]         = useState<CurrentUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  // 初期化: sessionStorage にトークンがあれば /me を叩いて復元
  useEffect(() => {
    const token = adminTokens.getAccess()
    if (!token) { setIsLoading(false); return }

    getMe(token)
      .then(u => setUser(u))
      .catch(() => adminTokens.clear())
      .finally(() => setIsLoading(false))
  }, [])

  const login = useCallback(async (req: LoginRequest) => {
    const res = await adminLogin(req)
    adminTokens.save(res.access_token, res.refresh_token)
    const u = await getMe(res.access_token)
    setUser(u)
  }, [])

  const logout = useCallback(() => {
    // サーバー側で refresh_token を即時失効させる（エラーは無視）
    const refreshToken = adminTokens.getRefresh()
    if (refreshToken) {
      adminLogout(refreshToken).catch(() => {
        // ログアウト API 失敗は無視: クライアント側のクリアは必ず実行
      })
    }
    adminTokens.clear()
    setUser(null)
  }, [])

  const getAccessToken = useCallback(() => adminTokens.getAccess(), [])

  const refreshIfNeeded = useCallback(async (): Promise<string | null> => {
    const refresh = adminTokens.getRefresh()
    if (!refresh) return null
    try {
      const res = await adminRefresh(refresh)
      // Phase 8: 新しい refresh_token も保存（トークンローテーション対応）
      adminTokens.save(res.access_token, res.refresh_token)
      return res.access_token
    } catch {
      adminTokens.clear()
      setUser(null)
      return null
    }
  }, [])

  return (
    <AdminAuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        logout,
        getAccessToken,
        refreshIfNeeded,
      }}
    >
      {children}
    </AdminAuthContext.Provider>
  )
}

export function useAdminAuth(): AdminAuthState {
  const ctx = useContext(AdminAuthContext)
  if (!ctx) throw new Error('useAdminAuth must be used within AdminAuthProvider')
  return ctx
}

/** 認証済みの access_token を取得するヘルパー（ページ内で使う） */
export function useRequiredToken(): string {
  const { getAccessToken } = useAdminAuth()
  const token = getAccessToken()
  if (!token) throw new Error('Not authenticated')
  return token
}
