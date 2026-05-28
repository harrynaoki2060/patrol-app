import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: '建設工事 新規入場管理システム',
  description: '建設現場の新規入場者管理・QRコード入場申請システム',
  // PWA 設定 (TODO: manifest.json を追加)
  // manifest: '/manifest.json',
}

export const viewport: Viewport = {
  // スマホでのピンチズーム防止（フォーム入力時の自動ズームを防ぐ）
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  // テーマカラー（ブラウザのUIに反映）
  themeColor: '#2563eb',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  )
}
