/** @type {import('next').NextConfig} */

/**
 * バックエンド API の URL
 *
 * - Docker Compose 環境: NEXT_PUBLIC_API_URL 未設定 → Nginx が /api/* を転送するので不要
 * - Docker 外で frontend を直接起動する場合: NEXT_PUBLIC_API_URL=http://localhost:8000 を設定
 *   例: NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
 */
const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || ''

const nextConfig = {
  /**
   * API プロキシ（Docker 外での開発用）
   *
   * NEXT_PUBLIC_API_URL が設定されている場合のみ有効。
   * Docker Compose 環境では Nginx がプロキシを担うため不要。
   */
  async rewrites() {
    if (!BACKEND_URL) return []

    return [
      {
        source:      '/api/:path*',
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ]
  },

  // TODO: 本番では実際のドメインを追加
  // images: {
  //   domains: ['your-cdn-domain.com'],
  // },
}

module.exports = nextConfig
