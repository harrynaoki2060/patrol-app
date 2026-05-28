import Link from 'next/link'

/**
 * トップページ
 * 開発・動作確認用のランディングページ
 * TODO: 本番では /entry/{token} へのリダイレクトか案内ページに変更
 */
export default function HomePage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-primary-600 to-primary-700 flex flex-col items-center justify-center p-6">
      {/* ロゴ・タイトル */}
      <div className="text-center mb-10">
        <div className="text-6xl mb-4">🏗️</div>
        <h1 className="text-2xl font-bold text-white mb-2">
          建設工事
        </h1>
        <h2 className="text-xl font-bold text-white mb-3">
          新規入場管理システム
        </h2>
        <p className="text-primary-100 text-sm">
          QRコードで簡単・安全な入場申請
        </p>
      </div>

      {/* カード */}
      <div className="w-full max-w-sm space-y-4">
        {/* 作業員向け案内 */}
        <div className="bg-white rounded-2xl p-5 shadow-lg">
          <h3 className="font-semibold text-gray-800 mb-2 flex items-center gap-2">
            <span>📱</span>
            <span>作業員の方へ</span>
          </h3>
          <p className="text-sm text-gray-600 mb-4">
            現場に掲示されているQRコードを<br />
            スマートフォンで読み取ってください
          </p>
          <div className="bg-gray-50 rounded-xl p-3 text-xs text-gray-500">
            ※ アプリのインストール不要<br />
            ブラウザのみで申請できます
          </div>
        </div>

        {/* 管理者向けリンク */}
        <div className="bg-white/10 rounded-2xl p-5">
          <h3 className="font-semibold text-white mb-3 flex items-center gap-2">
            <span>🔐</span>
            <span>管理者・現場監督の方へ</span>
          </h3>
          <Link
            href="/admin/login"
            className="block w-full text-center bg-white text-primary-700 font-semibold py-3 px-4 rounded-xl hover:bg-primary-50 transition-colors"
          >
            管理画面へログイン
          </Link>
        </div>

        {/* 開発用リンク（本番では削除） */}
        <div className="bg-yellow-500/20 border border-yellow-300/30 rounded-xl p-4">
          <p className="text-yellow-100 text-xs font-medium mb-2">
            🛠 開発用リンク（本番では削除）
          </p>
          <div className="space-y-2">
            <Link
              href="/health"
              className="block text-yellow-100 text-sm underline"
            >
              → バックエンド疎通確認
            </Link>
            <a
              href="/api/docs"
              className="block text-yellow-100 text-sm underline"
              target="_blank"
              rel="noopener noreferrer"
            >
              → API ドキュメント（Swagger UI）
            </a>
          </div>
        </div>
      </div>

      {/* フッター */}
      <p className="mt-8 text-primary-200 text-xs">
        v0.1.0 - 開発環境
      </p>
    </div>
  )
}
