/**
 * 管理者認証 API
 *
 * - POST /api/admin/auth/login   → ログイン
 * - POST /api/admin/auth/refresh → アクセストークン再発行（トークンローテーション）
 * - POST /api/admin/auth/logout  → ログアウト（refresh token 即時失効）
 * - GET  /api/admin/auth/me      → 現在のユーザー情報
 */

import { apiFetch } from './client'
import type {
  AccessTokenResponse,
  CurrentUser,
  LoginRequest,
  LogoutResponse,
  TokenResponse,
} from '@/types/api'

export async function adminLogin(req: LoginRequest): Promise<TokenResponse> {
  return apiFetch<TokenResponse>('/admin/auth/login', {
    method: 'POST',
    body: req,
  })
}

export async function adminRefresh(refreshToken: string): Promise<AccessTokenResponse> {
  return apiFetch<AccessTokenResponse>('/admin/auth/refresh', {
    method: 'POST',
    body: { refresh_token: refreshToken },
  })
}

/**
 * ログアウト — refresh token を即時失効させる。
 * エラーが発生しても呼び出し元は無視して sessionStorage をクリアすること。
 */
export async function adminLogout(refreshToken: string): Promise<LogoutResponse> {
  return apiFetch<LogoutResponse>('/admin/auth/logout', {
    method: 'POST',
    body: { refresh_token: refreshToken },
  })
}

export async function getMe(accessToken: string): Promise<CurrentUser> {
  return apiFetch<CurrentUser>('/admin/auth/me', {
    method: 'GET',
    token: accessToken,
  })
}

// ---------------------------------------------------------------------------
// トークン管理ユーティリティ
// ---------------------------------------------------------------------------

const ACCESS_TOKEN_KEY  = 'admin_access_token'
const REFRESH_TOKEN_KEY = 'admin_refresh_token'

export const adminTokens = {
  save(access: string, refresh: string) {
    if (typeof window === 'undefined') return
    sessionStorage.setItem(ACCESS_TOKEN_KEY, access)
    sessionStorage.setItem(REFRESH_TOKEN_KEY, refresh)
  },
  getAccess(): string | null {
    if (typeof window === 'undefined') return null
    return sessionStorage.getItem(ACCESS_TOKEN_KEY)
  },
  getRefresh(): string | null {
    if (typeof window === 'undefined') return null
    return sessionStorage.getItem(REFRESH_TOKEN_KEY)
  },
  clear() {
    if (typeof window === 'undefined') return
    sessionStorage.removeItem(ACCESS_TOKEN_KEY)
    sessionStorage.removeItem(REFRESH_TOKEN_KEY)
  },
}
