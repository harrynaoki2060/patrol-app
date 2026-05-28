/**
 * バックエンド疎通確認ページ
 * http://localhost/health でアクセス
 *
 * サーバーコンポーネントとして実装:
 * - Docker 内部ネットワーク (http://backend:8000) に直接アクセス
 * - ブラウザを経由しないため nginx のプロキシに依存しない
 */

interface HealthData {
  status: string
  service: string
  version: string
  timestamp: string
}

interface ServiceCheck {
  name: string
  url: string
  ok: boolean
  data?: HealthData
  error?: string
}

async function checkBackend(): Promise<ServiceCheck> {
  const url =
    process.env.INTERNAL_API_URL
      ? `${process.env.INTERNAL_API_URL}/api/health`
      : 'http://backend:8000/api/health'

  try {
    const res = await fetch(url, {
      cache: 'no-store',
      signal: AbortSignal.timeout(5000),
    })

    if (!res.ok) {
      return { name: 'Backend (FastAPI)', url, ok: false, error: `HTTP ${res.status}` }
    }

    const data: HealthData = await res.json()
    return { name: 'Backend (FastAPI)', url, ok: data.status === 'ok', data }
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown error'
    return { name: 'Backend (FastAPI)', url, ok: false, error: message }
  }
}

function StatusBadge({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-semibold ${
        ok
          ? 'bg-green-100 text-green-800'
          : 'bg-red-100 text-red-800'
      }`}
    >
      {ok ? '✅ OK' : '❌ エラー'}
    </span>
  )
}

function ServiceRow({ check }: { check: ServiceCheck }) {
  return (
    <div className="flex items-start justify-between gap-4 py-4 border-b border-gray-100 last:border-0">
      <div className="flex-1 min-w-0">
        <p className="font-medium text-gray-900">{check.name}</p>
        <p className="text-xs text-gray-400 truncate mt-0.5">{check.url}</p>
        {check.error && (
          <p className="text-xs text-red-600 mt-1">エラー: {check.error}</p>
        )}
        {check.data && (
          <p className="text-xs text-gray-500 mt-1">
            v{check.data.version} · {new Date(check.data.timestamp).toLocaleTimeString('ja-JP')}
          </p>
        )}
      </div>
      <StatusBadge ok={check.ok} />
    </div>
  )
}

export default async function HealthPage() {
  const backendCheck = await checkBackend()

  // TODO: Day2 で以下のチェックを追加
  // const dbCheck = await checkDatabase()
  // const redisCheck = await checkRedis()
  // const minioCheck = await checkMinio()

  const allOk = backendCheck.ok

  return (
    <div className="min-h-screen bg-gray-50 p-4">
      <div className="max-w-lg mx-auto">
        {/* ヘッダー */}
        <div className="mb-6">
          <h1 className="text-xl font-bold text-gray-900">
            🏥 システム疎通確認
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            各サービスの起動状態を確認します
          </p>
        </div>

        {/* 総合ステータス */}
        <div
          className={`rounded-2xl p-4 mb-4 ${
            allOk
              ? 'bg-green-50 border border-green-200'
              : 'bg-red-50 border border-red-200'
          }`}
        >
          <p className="font-semibold text-gray-800">
            総合ステータス:{' '}
            <span className={allOk ? 'text-green-700' : 'text-red-700'}>
              {allOk ? '✅ すべて正常' : '❌ 異常あり'}
            </span>
          </p>
        </div>

        {/* サービス一覧 */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 px-4">
          <ServiceRow check={backendCheck} />

          {/* TODO: Day2 で以下のサービスチェックを追加 */}
          <div className="py-4 border-b border-gray-100">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-gray-400">PostgreSQL</p>
                <p className="text-xs text-gray-300 mt-0.5">Day2 で実装予定</p>
              </div>
              <span className="text-xs text-gray-300 bg-gray-50 px-3 py-1 rounded-full">
                TODO
              </span>
            </div>
          </div>

          <div className="py-4 border-b border-gray-100">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-gray-400">Redis</p>
                <p className="text-xs text-gray-300 mt-0.5">Day2 で実装予定</p>
              </div>
              <span className="text-xs text-gray-300 bg-gray-50 px-3 py-1 rounded-full">
                TODO
              </span>
            </div>
          </div>

          <div className="py-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-gray-400">MinIO</p>
                <p className="text-xs text-gray-300 mt-0.5">Day2 で実装予定</p>
              </div>
              <span className="text-xs text-gray-300 bg-gray-50 px-3 py-1 rounded-full">
                TODO
              </span>
            </div>
          </div>
        </div>

        {/* リンク */}
        <div className="mt-4 flex gap-2">
          <a
            href="/"
            className="flex-1 text-center py-3 bg-white border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-gray-50"
          >
            ← トップへ
          </a>
          <a
            href="/api/health/full"
            className="flex-1 text-center py-3 bg-white border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-gray-50"
            target="_blank"
            rel="noopener noreferrer"
          >
            API詳細 →
          </a>
        </div>

        <p className="text-center text-xs text-gray-400 mt-4">
          このページはサーバーサイドレンダリングです（毎回最新の状態を表示）
        </p>
      </div>
    </div>
  )
}
