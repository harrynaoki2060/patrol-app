/**
 * API クライアント基盤
 *
 * 全 API 呼び出しはここを通す。
 * - JSON の serialize / deserialize
 * - HTTP エラー → ApiError への変換
 * - 認証ヘッダーの付与
 */

export const API_BASE = '/api'

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    public readonly rawBody?: unknown,
  ) {
    super(detail)
    this.name = 'ApiError'
  }
}

interface FetchOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  token?: string          // Bearer トークン（entry_session or access_token）
  timeoutMs?: number
}

/** エラーレスポンスの detail を文字列に変換 */
function extractDetail(body: unknown): string {
  if (!body || typeof body !== 'object') return '予期しないエラーが発生しました'
  const b = body as Record<string, unknown>
  if (typeof b.detail === 'string') return b.detail
  if (Array.isArray(b.detail)) {
    return b.detail.map((e: { msg?: string }) => e?.msg ?? String(e)).join(' / ')
  }
  return '予期しないエラーが発生しました'
}

export async function apiFetch<T>(
  path: string,
  options: FetchOptions = {},
): Promise<T> {
  const { body, token, timeoutMs = 15000, ...rest } = options

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(rest.headers as Record<string, string>),
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const controller = new AbortController()
  const timerId = setTimeout(() => controller.abort(), timeoutMs)

  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...rest,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })
  } catch (err) {
    clearTimeout(timerId)
    if ((err as Error).name === 'AbortError') {
      throw new ApiError(0, 'リクエストがタイムアウトしました')
    }
    throw new ApiError(0, 'ネットワークに接続できません')
  } finally {
    clearTimeout(timerId)
  }

  // 204 No Content
  if (res.status === 204) return undefined as unknown as T

  let responseBody: unknown
  try {
    responseBody = await res.json()
  } catch {
    if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`)
    return undefined as unknown as T
  }

  if (!res.ok) {
    throw new ApiError(res.status, extractDetail(responseBody), responseBody)
  }

  return responseBody as T
}
