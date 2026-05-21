# 建設工事 新規入場管理システム

QRコード方式の建設現場 新規入場管理システム。

- **外部作業員**: スマホでQRを読んで入場申請
- **現場監督**: スマホで承認
- **社内管理者**: PCで全データ管理

> 設計書: [SYSTEM_DESIGN_V2.md](./SYSTEM_DESIGN_V2.md)  
> 実装計画: [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)

---

## 開発環境 起動手順

### 1. 前提条件

```bash
# 確認コマンド
docker --version      # Docker 24.x 以上
docker compose version # Docker Compose 2.x 以上
```

### 2. 環境変数の設定

```bash
# .env.example をコピーして .env を作成
cp .env.example .env

# .env をエディタで開いて確認（開発環境はデフォルト値でOK）
# 変更が必要な場合は各値を修正する
```

### 3. 起動

```bash
# 全サービスをバックグラウンドで起動
docker compose up -d

# ログをリアルタイムで確認したい場合
docker compose up

# 特定サービスのログを確認
docker compose logs -f backend
docker compose logs -f frontend
```

### 4. 初回起動確認

```bash
# 全サービスの状態確認
docker compose ps

# 期待される出力（全サービスが "Up" または "running"）:
# NAME            STATUS
# nginx           Up
# frontend        Up
# backend         Up
# postgres        Up (healthy)
# redis           Up
# minio           Up (healthy)
# minio-init      Exited (0)  ← 正常（バケット作成後に終了）
```

---

## アクセス URL 一覧

| URL | 説明 |
|-----|------|
| `http://localhost` | トップページ（フロントエンド） |
| `http://localhost/health` | バックエンド疎通確認ページ |
| `http://localhost/api/health` | バックエンド ヘルスチェック API |
| `http://localhost/api/docs` | API ドキュメント（Swagger UI） |
| `http://localhost/api/redoc` | API ドキュメント（ReDoc） |
| `http://localhost:8000/api/health` | バックエンド直接アクセス（開発時のみ） |
| `http://localhost:3000` | フロントエンド直接アクセス（開発時のみ） |
| `http://localhost:9001` | MinIO コンソール（開発時のみ） |

---

## 動作確認手順

### ① フロントエンド確認

```bash
# ブラウザで以下にアクセス
open http://localhost
# → 「建設工事 新規入場管理システム」のトップページが表示される
```

### ② バックエンド /health 確認

```bash
# curl でヘルスチェック
curl http://localhost/api/health

# 期待されるレスポンス:
# {
#   "status": "ok",
#   "service": "entry-management-api",
#   "version": "0.1.0",
#   "timestamp": "2026-05-19T..."
# }
```

```bash
# または: ブラウザで疎通確認ページ
open http://localhost/health
# → 「✅ OK」が表示される
```

### ③ PostgreSQL 接続確認

```bash
# コンテナ内から psql を実行
docker compose exec postgres psql -U app -d entry_db -c "SELECT version();"

# 期待される出力:
# PostgreSQL 16.x ...
```

### ④ MinIO コンソール確認

```bash
# ブラウザで MinIO コンソールを開く
open http://localhost:9001

# ログイン情報 (.env の値を使用):
# Username: minioadmin
# Password: changeme_dev_password

# バケット "entry-documents" が作成されていることを確認
```

### ⑤ Redis ping 確認

```bash
# Redis に ping を送信
docker compose exec redis redis-cli -a changeme_dev_password ping

# 期待される出力:
# PONG
```

### ⑥ 全サービス接続確認（/api/health/full）

```bash
curl http://localhost/api/health/full

# 期待されるレスポンス:
# {
#   "status": "ok",
#   "checks": {
#     "database": {"status": "ok", "version": "PostgreSQL 16.x ..."},
#     "redis":    {"status": "ok"},
#     "minio":    {"status": "ok", "bucket_exists": true}
#   }
# }
```

---

## Alembic マイグレーション

### 初回テーブル作成（コンテナ起動後）

```bash
# マイグレーション実行（HEAD まで適用）
docker compose exec backend alembic upgrade head

# 適用済みリビジョンの確認
docker compose exec backend alembic current

# マイグレーション履歴の確認
docker compose exec backend alembic history
```

### 新しいマイグレーションを作成する

```bash
# モデル変更後、差分を自動生成
docker compose exec backend alembic revision --autogenerate -m "add_column_xxx"

# 内容を確認してから適用
docker compose exec backend alembic upgrade head
```

### ロールバック

```bash
# 1つ前のリビジョンに戻す
docker compose exec backend alembic downgrade -1

# 特定リビジョンに戻す
docker compose exec backend alembic downgrade 0001
```

### psql で直接確認

```bash
# テーブル一覧
make db-tables
# または
docker compose exec postgres psql -U app -d entry_db -c \
  "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;"

# インデックス一覧（部分インデックスの WHERE 句も表示）
make db-indexes
# または
docker compose exec postgres psql -U app -d entry_db -c \
  "SELECT indexname, tablename, indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY tablename, indexname;"

# 制約一覧（UniqueConstraint / CheckConstraint）
make db-constraints

# worker_site_entries の部分インデックス確認
make db-check-entries
# 期待される出力（uq_entries_worker_site_active に WHERE 句があること）:
# uq_entries_worker_site_active | worker_site_entries | CREATE UNIQUE INDEX ... WHERE (status = ANY (...))

# テーブル定義の詳細
docker compose exec postgres psql -U app -d entry_db -c "\d worker_site_entries"
```

---

## 開発ワークフロー

### コードの変更

開発環境では **ホットリロード** が有効なため、ファイルを保存すると自動的にリロードされます。

- **Backend**: ファイル保存 → uvicorn が自動リスタート
- **Frontend**: ファイル保存 → Next.js HMR が自動更新

### サービスの再起動

```bash
# バックエンドのみ再起動
docker compose restart backend

# フロントエンドのみ再起動
docker compose restart frontend

# 全サービス停止
docker compose down

# データを含めて全削除（注意: DB データも消える）
docker compose down -v
```

### ログ確認

```bash
# 全サービスのログ
docker compose logs -f

# 特定サービス
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f postgres
```

### バックエンドの依存ライブラリを更新した場合

```bash
# requirements.txt を変更したら再ビルドが必要
docker compose build backend
docker compose up -d backend
```

### フロントエンドの依存ライブラリを更新した場合

```bash
# package.json を変更したら再ビルドが必要
docker compose build frontend
docker compose up -d frontend
```

---

## ディレクトリ構成

```
.
├── docker-compose.yml          # 全サービス定義（本番ベース）
├── docker-compose.override.yml # 開発用オーバーライド（自動適用）
├── .env.example               # 環境変数テンプレート
├── .env                       # 環境変数（git管理外）
│
├── nginx/
│   └── conf.d/
│       └── default.conf       # リバースプロキシ設定
│
├── backend/                   # FastAPI バックエンド
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini            # Alembic 設定
│   ├── alembic/
│   │   ├── env.py             # async マイグレーション環境
│   │   └── versions/
│   │       └── 0001_initial_tables.py
│   └── app/
│       ├── main.py            # エントリポイント
│       ├── core/
│       │   └── config.py      # 設定（環境変数）
│       ├── db/
│       │   ├── base.py        # Base / BaseModel
│       │   └── session.py     # AsyncSession / get_db
│       ├── models/            # SQLAlchemy ORM モデル
│       │   ├── company.py
│       │   ├── admin_user.py
│       │   ├── site.py
│       │   ├── qr_code.py
│       │   ├── worker.py
│       │   └── entry.py
│       ├── repositories/      # データアクセス層
│       │   ├── base.py
│       │   ├── worker.py
│       │   └── site.py
│       └── api/
│           └── health.py      # ヘルスチェック API（DB/Redis/MinIO）
│
├── frontend/                  # Next.js 14 フロントエンド
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       └── app/
│           ├── layout.tsx     # ルートレイアウト
│           ├── page.tsx       # トップページ
│           └── health/
│               └── page.tsx   # 疎通確認ページ
│
├── postgres/
│   └── init.sql               # DB 初期化 SQL
│
├── scripts/
│   └── create_admin.py        # 初期管理者作成スクリプト
│
└── docs/
    ├── SYSTEM_DESIGN_V2.md    # システム設計書
    └── IMPLEMENTATION_PLAN.md # 実装計画書
```

---

## 初期管理者の作成

```bash
# 1. サービスを起動してマイグレーション実行
make up
make migrate

# 2. 初期管理者を作成（対話モード）
docker compose exec backend python scripts/create_admin.py \
    --email admin@example.com \
    --name "システム管理者" \
    --role super_admin \
    --company-name "管理会社"
# → パスワードを対話入力（エコーバックなし）

# または環境変数で非対話実行（CI/CD 向け）
docker compose exec -e ADMIN_EMAIL=admin@example.com \
    -e ADMIN_PASSWORD=Secret1234! \
    backend python scripts/create_admin.py \
    --name "システム管理者" --role super_admin

# Makefile ショートカット
make create-admin EMAIL=admin@example.com PASSWORD=Secret1234! NAME="管理者" ROLE=super_admin
```

---

## 認証 API

### JWT の仕様

| 項目 | 値 |
|---|---|
| アルゴリズム | HS256 |
| アクセストークン有効期限 | 30 分 |
| リフレッシュトークン有効期限 | 7 日 |
| ペイロード（access） | `sub` / `email` / `role` / `name` / `type` / `jti` |
| ペイロード（refresh） | `sub` / `type` / `jti` |

### ログインしてトークンを取得

```bash
curl -X POST http://localhost/api/admin/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "Secret1234!"}'

# レスポンス例:
# {
#   "access_token": "eyJ...",
#   "refresh_token": "eyJ...",
#   "token_type": "bearer",
#   "expires_in": 1800,
#   "user": {"id": "...", "email": "...", "name": "...", "role": "super_admin"}
# }
```

### Bearer トークンを使ったリクエスト

```bash
ACCESS_TOKEN="eyJ..."

# 自分の情報を取得
curl http://localhost/api/admin/auth/me \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# アクセストークンの再発行
curl -X POST http://localhost/api/admin/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJ..."}'
```

### Swagger UI でのテスト

1. `http://localhost/api/docs` にアクセス
2. `POST /api/admin/auth/login` でログインして `access_token` をコピー
3. 右上の「Authorize 🔒」ボタンをクリック
4. `BearerAuth` に `access_token` の値を貼り付けて「Authorize」
5. 以降の認証必須エンドポイントが自動的に Bearer ヘッダー付きで実行される

### ロール一覧

| ロール | 権限 |
|---|---|
| `super_admin` | 全操作（管理者ユーザー管理・会社設定含む） |
| `admin` | 現場管理・QR コード発行 |
| `supervisor` | 申請確認・承認のみ |

---

## 公開 QR 認証 API

作業員（未ログイン）が QR コードを読み込んで入場申請セッションを開始するための API です。

### フロー概要

```
QR コードスキャン
    │
    ▼
POST /api/public/qr/verify
    │  body: { token: "<QR埋め込みトークン>", pin: "1234" }
    │
    ├─ 成功 ──▶  entry_session_token (30分有効)
    │               └─ 以降の入場申請 API で Authorization: Bearer として使用
    │
    ├─ QR無効/期限切れ ──▶ 401
    ├─ PIN誤り ──▶ 401
    └─ 試行回数超過 ──▶ 429 (Retry-After ヘッダーあり)
```

### QR コード認証

```bash
# PIN 不要の QR コード
curl -X POST http://localhost/api/public/qr/verify \
  -H "Content-Type: application/json" \
  -d '{"token": "<QRコードに埋め込まれたトークン>"}'

# PIN 必要の QR コード
curl -X POST http://localhost/api/public/qr/verify \
  -H "Content-Type: application/json" \
  -d '{"token": "<token>", "pin": "1234"}'

# レスポンス例（成功）:
# {
#   "entry_session_token": "eyJ...",
#   "token_type": "bearer",
#   "expires_in": 1800,
#   "site": {
#     "id": "...",
#     "name": "○○新築工事",
#     "require_health_check": true,
#     "require_insurance": true,
#     "custom_notice": "安全帯を必ず着用してください"
#   }
# }
```

### entry_session_token の使い方

```bash
ENTRY_TOKEN="eyJ..."

# 入場申請フォーム送信（Day 4 以降で実装）
curl -X POST http://localhost/api/public/entries \
  -H "Authorization: Bearer $ENTRY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{ ... }'
```

### トークン種別の比較

| 種別 | 取得方法 | 有効期限 | 用途 |
|---|---|---|---|
| `access` | `/api/admin/auth/login` | 30 分 | 管理 API |
| `refresh` | `/api/admin/auth/login` | 7 日 | アクセストークン再発行 |
| `entry_session` | `/api/public/qr/verify` | 30 分 | 公開入場申請 API のみ |

> ⚠️ `entry_session_token` を管理 API に使うと `type` 不一致で **401** になります。逆も同様です。

### ブルートフォース保護

PIN の連続失敗はバックエンドと Nginx の二重で防護します。

| レイヤー | 制限 | 設定 |
|---|---|---|
| Nginx `qr_verify` ゾーン | IP ごとに 10 req/min（burst=5） | `nginx/conf.d/default.conf` |
| バックエンド `failed_attempts` | `max_attempts` 回失敗で `QR_BLOCK_MINUTES` 分ブロック | `config.py` `QR_BLOCK_MINUTES=15` |

ブロック中は `Retry-After` ヘッダー（残り秒数）付きの **429** を返します。

---

## 作業員入力・Draft 管理 API

### Draft ライフサイクル

```
[QR 認証]
    └─▶ POST /api/public/qr/verify          entry_session_token 取得（30 分）
            │
            ▼
[作業員検索（任意）]
    └─▶ POST /api/public/workers/lookup     phone → exists / WorkerSummary
            │   exists=true の場合: worker.id をメモ
            │
            ▼
[Draft 作成]
    └─▶ POST /api/public/entries/draft      receipt_number 発行、status=draft
            │
            ▼                    ← autosave（何度でも呼べる）
[Draft 更新]
    └─▶ PATCH /api/public/entries/{id}      部分更新 + last_saved_at 更新
            │
            ▼
[申請確定]
    └─▶ POST /api/public/entries/{id}/submit 必須チェック → status=pending
```

### Worker 再利用フロー

既存作業員が再訪問した場合、前回の登録情報を再利用できます。

```bash
# 1. 電話番号で検索
curl -X POST http://localhost/api/public/workers/lookup \
  -H "Authorization: Bearer $ENTRY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"phone": "090-1234-5678"}'
# → {"exists": true, "worker": {"id": "...", "last_name": "田中", ...}}

# 2. Draft 作成（既存 worker を再利用）
curl -X POST http://localhost/api/public/entries/draft \
  -H "Authorization: Bearer $ENTRY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"phone": "090-1234-5678", "worker_id": "<lookup で取得した worker.id>"}'
```

### Autosave 設計

```bash
# PATCH は部分更新（送ったフィールドのみ更新）
curl -X PATCH http://localhost/api/public/entries/{id} \
  -H "Authorization: Bearer $ENTRY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "last_name": "田中",
    "first_name": "太郎",
    "birth_date": "1990-01-15",
    "job_title": "型枠大工",
    "worker_type": "company_employee",
    "consent_agreed": true
  }'
# → {"status": "draft", "last_saved_at": "2026-...", "warnings": [...]}
```

**推奨フロントエンド実装**: 入力変更から 1〜2 秒後に自動 PATCH。ネットワーク障害時はローカルストレージに退避して復帰後に再送。

### Submit（申請確定）

```bash
curl -X POST http://localhost/api/public/entries/{id}/submit \
  -H "Authorization: Bearer $ENTRY_TOKEN"
# → {"receipt_number": "A3F7KM2P", "status": "pending", ...}
```

submit 前の必須チェック:
- `last_name`, `first_name`, `birth_date`, `job_title`, `worker_type`
- `consent_agreed`（個人情報同意）
- 現場設定に応じて: `has_health_check`, `insurance_type`, `insurance_number`

### 重複申請ポリシー

同一作業員が同一現場に `draft / pending / approved` のいずれかが存在する状態で Draft Create を実行すると **409 Conflict** を返します。

| 状態 | 新規 Draft Create |
|---|---|
| draft が存在 | 409（既存 draft を使い続けてください） |
| pending が存在 | 409（承認待ちです） |
| approved が存在 | 409（承認済みです） |
| rejected / withdrawn | 新規作成可能 |

---

## 承認・審査フロー API

### ステータス遷移

```
draft ──→ pending ──→ approved
                 └──→ rejected
                 └──→ withdrawn
```

| 遷移 | トリガー | 操作者 |
|------|---------|--------|
| `draft → pending` | `POST /entries/{id}/submit` | 作業員（公開側） |
| `pending → approved` | `POST /admin/entries/{id}/approve` | SUPERVISOR 以上 |
| `pending → rejected` | `POST /admin/entries/{id}/reject` | SUPERVISOR 以上 |
| `pending → withdrawn` | （将来実装） | — |

承認・差戻しはすべて `approval_logs` テーブルに記録される（不変の監査証跡）。

### ロールスコープ

| ロール | 閲覧できる申請 |
|--------|--------------|
| `super_admin` | 全現場の申請 |
| `admin` | 自社（`company_id` が一致）の現場の申請 |
| `supervisor` | `site.supervisor_id` が自分の ID の現場の申請のみ |

### pending 申請一覧

```bash
curl -X GET "http://localhost/api/admin/entries/pending" \
  -H "Authorization: Bearer <access_token>"

# ページネーション
curl "http://localhost/api/admin/entries/pending?page=1&per_page=20"

# キーワード検索（氏名・受付番号の部分一致）
curl "http://localhost/api/admin/entries/pending?keyword=田中"

# 現場フィルタ
curl "http://localhost/api/admin/entries/pending?site_id=<site_id>"
```

レスポンス:
```json
{
  "items": [
    {
      "id": "...",
      "receipt_number": "A3F7KM2P",
      "status": "pending",
      "site_id": "...",
      "site_name": "第一工事現場",
      "planned_entry_date": "2026-06-01",
      "submitted_at": "2026-05-20T10:30:00Z",
      "worker": {
        "id": "...",
        "last_name": "田中",
        "first_name": "太郎",
        "worker_type": "company_employee",
        ...
      }
    }
  ],
  "total": 42,
  "page": 1,
  "per_page": 20,
  "has_next": true
}
```

### 申請詳細

```bash
curl -X GET "http://localhost/api/admin/entries/{entry_id}" \
  -H "Authorization: Bearer <access_token>"
```

- `worker` フィールドに全情報（`birth_date` / `phone` / `address` 等を含む）
- `approval_logs` フィールドに過去の操作履歴（時系列）

### 承認

```bash
curl -X POST "http://localhost/api/admin/entries/{entry_id}/approve" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"reason": "問題なし"}'  # reason は任意
```

### 差戻し

```bash
curl -X POST "http://localhost/api/admin/entries/{entry_id}/reject" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"reason": "保険証のコピーが不鮮明です。再提出をお願いします。"}'  # reason は必須
```

---

## 実装ステータス

### Day 1 完了 ✅
- Docker 環境構築（nginx / backend / postgres / redis / minio / frontend）
- Backend: FastAPI 起動・`/api/health` 実装
- Frontend: Next.js 起動・トップページ・疎通確認ページ
- Nginx: リバースプロキシ + Rate Limiting 設定
- MinIO: バケット自動作成（`minio-init` コンテナ）

### Day 2 完了 ✅
- SQLAlchemy 非同期設定（`AsyncSession` / `asyncpg` / `pool_pre_ping`）
- ORM モデル 6 テーブル（Company, AdminUser, Site, SiteQrCode, Worker, WorkerSiteEntry）
- Repository 層（BaseRepository, WorkerRepository, SiteRepository）
- Alembic 非同期マイグレーション設定 + 初回マイグレーション（0001）
- `/api/health/full` で DB・Redis・MinIO 接続確認（タイムアウト付き）

### Day 2 検証フェーズ 完了 ✅
- バグ修正（MinIO healthcheck / `asyncio.to_thread` / settings 統一）
- pytest 基盤（`conftest.py` SAVEPOINT 分離 / Repository テスト / Health API テスト）
- RequestLoggingMiddleware（`X-Request-ID` ヘッダー付与）
- Makefile（`make migrate` / `make test` 等 15 コマンド）
- TECH_DEBT.md 作成

### Day 3 完了 ✅（認証・権限基盤）
- HS256 JWT 発行・検証（`app/core/security.py`）
- bcrypt パスワードハッシュ（`hash_password` / `verify_password`）
- `AuthService`（ログイン失敗カウント・アカウントロック・リフレッシュ）
- `POST /api/admin/auth/login` / `POST /api/admin/auth/refresh` / `GET /api/admin/auth/me`
- `Depends` ベース Role 制御（`require_supervisor` / `require_admin` / `require_super_admin`）
- 初期管理者作成スクリプト（`scripts/create_admin.py`）
- pytest 36テスト（security / AuthService / API エンドポイント / Role）
- Swagger UI に Bearer Auth スキーム追加

### Day 3 追加フェーズ 完了 ✅（公開側 QR アクセス基盤）
- `SiteQrCode` ブルートフォース保護カラム追加（`failed_attempts` / `blocked_until` / `max_attempts` / `last_accessed_at`）
- Alembic マイグレーション `0002_qr_security_columns`
- `QrCodeRepository`（`get_by_token_with_site` / `increment_failed_attempts` / `reset_failed_attempts` / `block` / `deactivate`）
- `entry_session` JWT 種別（`app/core/security.py`）— sub なし最小 payload・30 分有効
- `QrVerifyService`（QR 有効性チェック / PIN bcrypt 検証 / ブロック制御 / 監査ログ）
- `POST /api/public/qr/verify` — QR トークン + PIN → `entry_session_token` 発行
- `get_current_entry_session()` Depends（`app/api/public_deps.py`）
- Nginx `qr_verify` 専用レート制限ゾーン（10 req/min、burst=5、`limit_req_status 429`）
- Swagger UI に `EntrySessionAuth` セキュリティスキーム追加
- pytest 35テスト（entry_session token / QrVerifyService / brute-force / public_deps / API エンドポイント / 逆流防止）

### Day 4 完了 ✅（作業員入力・Draft 管理基盤）
- Alembic マイグレーション `0003_draft_entry_columns`（`draft_started_at` / `last_saved_at` / `submitted_at` nullable 化）
- `workers.birth_date` / `workers.job_title` を nullable 化（draft-first フロー対応）
- バリデーションユーティリティ（`app/core/validators.py`）— phone 正規化 / カナ検証 / 生年月日 / 郵便番号
- 受付番号生成（`app/core/receipt.py`）— 8 文字英数字（I/O/0/1 除外）・DB 重複チェック付き
- `WorkerRepository` 拡張（`create_worker` / `update_worker` / `set_consent_agreed`）
- `EntryRepository` 新規（`create_draft` / `get_draft_by_id_and_site` / `update_entry_fields` / `submit`）
- `WorkerLookupService`（電話番号検索・最小情報返却・inactive 作業員非公開）
- `DraftEntryService`（Draft 作成 / autosave / submit / 重複チェック / IP ハッシュ / 監査ログ）
- `POST /api/public/workers/lookup` — 電話番号 → WorkerSummary（個人情報最小化）
- `POST /api/public/entries/draft` — Draft 作成 + receipt_number 発行
- `PATCH /api/public/entries/{id}` — Autosave（部分更新 + last_saved_at 更新）
- `POST /api/public/entries/{id}/submit` — Draft → Pending 遷移（必須フィールド検証 + IP ハッシュ）
- Nginx `submit_api` ゾーンに `limit_req_status 429` 追加
- pytest 60+テスト（validators / receipt / WorkerLookup / DraftCreate / Autosave / Submit / API endpoints）

### Day 5 完了 ✅（管理側承認・審査フロー基盤）
- Alembic マイグレーション `0004_approval_logs`（`approval_logs` テーブル新規作成）
- `ApprovalLog` モデル（`app/models/approval_log.py`）— 不変の監査証跡
- ステータス遷移ステートマシン（`app/core/state_machine.py`）— 不正遷移は 409
- `SiteRepository.get_site_ids_for_user()` — ロール別スコープ解決（SUPER_ADMIN=全現場 / ADMIN=自社 / SUPERVISOR=担当）
- `EntryRepository` 拡張（`get_pending_entries` / `get_entry_detail` / `approve` / `reject`）
- `ApprovalLogRepository`（`create_log` / `get_by_entry`）
- `ApprovalService`（`list_pending` / `get_detail` / `approve` / `reject` — ロールスコープ適用済み）
- `GET /api/admin/entries/pending` — ロールスコープ・ページネーション・キーワード検索・現場フィルタ
- `GET /api/admin/entries/{id}` — 申請詳細（作業員情報 + 承認ログ）
- `POST /api/admin/entries/{id}/approve` — 承認（pending→approved + ログ記録）
- `POST /api/admin/entries/{id}/reject` — 差戻し（pending→rejected + reason必須 + ログ記録）
- pytest 40+テスト（state_machine / SiteScope / EntryRepo / ApprovalLog / ApprovalService / API endpoints）

### Phase 6 完了 ✅（最小実運用 UI）
- **TypeScript 型定義** — `src/types/api.ts`（全バックエンドスキーマに対応）
- **API クライアント層** — `src/lib/api/`（client / public / auth / entries）
  - `AbortController` 15 秒タイムアウト、`ApiError` クラス（status コード対応）
- **フォームバリデーション** — `src/lib/validation.ts`（phone 正規化・カナ・生年月日・郵便番号）
- **カスタムフック** — `useAutosave`（3 秒デバウンス）/ `useOnlineStatus` / `useBeforeUnload`
- **UI コンポーネント** — `Button` / `FormField` / `Spinner` / `SaveIndicator` / `ErrorBanner` / `StepHeader` / `FixedBottom`
- **作業員公開フロー**
  - `/entry/[token]` — QR スキャン後 PIN 入力画面（429 ブロック対応）
  - `/entry/[token]/form` — 5 ステップ入力フォーム（autosave / Worker 再利用プロンプト / submit 完了）
- **管理者 UI**
  - `/admin/login` — JWT ベース管理者ログイン
  - `/admin/pending` — 承認待ち一覧（行ごと承認 / インライン差戻しフォーム）
  - `/admin/entries/[id]` — 申請詳細（承認・差戻し + 監査ログ表示）
- **フロントエンドテスト** — Vitest + @testing-library/react
  - `validation.test.ts`（phone / kana / birthdate / postal / required / maxLength）
  - `useAutosave.test.ts`（debounce / flush / enabled / エラーハンドリング）
  - `admin/pending/page.test.tsx`（一覧表示 / 承認フロー / 差戻しフロー / 検索）

### Phase 7 完了 ✅（QR 発行・現場管理 UI）
- Alembic マイグレーション `0005_qr_analytics_columns`（`max_uses` / `use_count` / `blocked_count` 追加）
- `SiteQrCode` モデル更新（新カラム対応）
- `QrCodeRepository` 拡張（`create_qr` / `update_fields` / `activate` / `increment_use_count` / `increment_blocked_count`）
- `QrVerifyService` 更新（`use_count` インクリメント / `max_uses` 制限チェック / `blocked_count` 累積）
- `SiteRepository` 拡張（`list_sites_for_user` — active_qr_count + pending_entry_count 付与 / `get_site_with_qr_codes`）
- スキーマ `schemas/site_admin.py`（SiteListItem / SiteDetailResponse / QrCodeItem / QrCreate* / QrUpdate*）
- `SiteAdminService`（list_sites / get_detail / create_qr / update_qr / deactivate_qr / activate_qr — ロールスコープ適用）
- `GET /api/admin/sites` / `GET /api/admin/sites/{id}` / `POST /api/admin/sites/{id}/qr`
- `PATCH /api/admin/qr/{id}` / `POST /api/admin/qr/{id}/deactivate` / `POST /api/admin/qr/{id}/activate`
- pytest 30+テスト（role scope / deactivate / max_uses / expired / blocked_count / API）
- フロントエンド: `types/api.ts` 拡張（SiteListItem / QrCodeItem / QrCreateResponse 他）
- フロントエンド: `lib/api/sites.ts`（getSites / getSiteDetail / createQr / updateQr / deactivateQr / activateQr）
- フロントエンド: `/admin/sites` 現場一覧（カード形式 / QR 数 / pending 数）
- フロントエンド: `/admin/sites/[id]` 現場詳細 + QR 管理
  - QR 一覧（use_count / last_accessed / expires_at / blocked_count）
  - QR 新規発行フォーム（ラベル / PIN / 有効期限 / 最大使用回数）
  - 発行直後 QR 画像表示（`qrcode` ライブラリ）+ PNG / SVG ダウンロード
  - 印刷専用ウィンドウ（A4 最適化、現場名・注意事項・入場手順付き）
  - 無効化 / 再有効化ボタン
- `qrcode` npm パッケージ追加（QR 画像生成）
- 管理者ナビゲーションに「現場」リンク追加
- `@media print` グローバルスタイル追加

### 次フェーズ予定
- 管理者ユーザー管理 API（`/api/admin/users/`）
- 現場 CRUD（新規作成・編集）API
- QR トークン再取得 API（既存 QR の印刷・ダウンロードに必要）

詳細は [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) を参照してください。
技術負債は [TECH_DEBT.md](./TECH_DEBT.md) を参照してください。

---

## スマートフォン動作確認手順

### 推奨ブラウザ

| OS | 推奨ブラウザ | 備考 |
|---|---|---|
| iOS 15 以上 | **Safari**（標準ブラウザ） | カメラ QR スキャンに Safari が必要 |
| Android 8 以上 | **Chrome**（標準ブラウザ） | QR スキャンは標準カメラアプリから |

> **注意**: LINE 内ブラウザ・Instagram 内ブラウザ等のアプリ内 WebView は動作保証外です。

---

### 作業員 — 新規入場申請フロー

#### STEP 1: QR コードをスキャンする

1. 現場掲示の **QR コードをカメラアプリで読み込む**（端末標準カメラ推奨）
2. ブラウザが自動で開き `http://localhost/entry/<token>` に遷移する

#### STEP 2: PIN 入力（現場で PIN が設定されている場合）

- 現場担当者から教えてもらった **4 桁の PIN** を入力する
- PIN を 5 回以上誤ると **15 分ブロック**（画面にカウントダウン表示）
- PIN が不要な現場は自動でフォームに進む

#### STEP 3: 申請フォームを入力する（5 ステップ）

| ステップ | 入力内容 |
|---|---|
| 1. 本人確認 | 携帯電話番号（既存作業員の場合は前回情報を再利用できます） |
| 2. 基本情報 | 氏名・フリガナ・生年月日・性別・血液型 |
| 3. 勤務情報 | 雇用形態・職種・所属会社 |
| 4. 緊急連絡先 | 緊急連絡先電話番号・氏名・続柄 |
| 5. 安全確認 | 健康診断・保険情報・個人情報同意 |

> **自動保存**: 入力内容は 3 秒ごとに自動保存されます。通信が切れても入力内容は保持されます。

#### STEP 4: 申請を確定する

- 「申請を送信する」ボタンをタップ
- 受付番号（例: `A3F7KM2P`）が表示されたら完了
- この番号を担当者に伝えてください

---

### 現場監督 — 承認フロー（スマホ操作）

#### ログイン

1. ブラウザで `http://localhost/admin/login` にアクセス
2. 管理者メールアドレスとパスワードを入力してログイン
3. ログイン情報は **セッション中のみ保持**（ブラウザを閉じるとログアウト）

#### 承認待ち一覧を確認する

1. ログイン後、自動的に「承認待ち申請」一覧に遷移
2. 各申請のカードに **氏名 / 会社名 / 受付番号 / 提出時刻** が表示される
3. 右上の検索ボックスで氏名・受付番号を絞り込める

#### 申請を承認する

1. 一覧カードの **「✓ 承認」ボタン** をタップ
2. 「承認しました」メッセージが表示されたら完了

#### 申請を差戻す

1. 一覧カードの **「✕ 差戻し」ボタン** をタップ
2. 差戻し理由を入力（作業員に伝わる内容で記述）
3. **「差戻しを確定」ボタン** をタップ

#### 詳細を確認する

- 各カード右端の **「→」ボタン** または氏名リンクをタップ
- 作業員の全情報・保険証情報・健康診断情報・監査ログを確認できる

---

### 現場担当者 — QR コード運用手順

> ⚠️ QR コード発行 UI は次フェーズで実装予定。現在は API 経由で操作します。

#### QR コードの運用ルール

| 項目 | 推奨設定 |
|---|---|
| QR コードの掲示場所 | 現場入口の見やすい場所（高さ 1.2〜1.5m） |
| PIN の更新頻度 | 週次推奨（長期工事の場合） |
| QR コードの有効期限 | 工事期間に合わせて設定 |
| PIN の共有方法 | 朝礼時に口頭で伝達（紙に書かない） |

#### トラブル対応

| 症状 | 対処方法 |
|---|---|
| QR を読んでも画面が開かない | URL を直接コピーして Safari/Chrome で開く |
| PIN を忘れた | 管理者に PIN のリセットを依頼 |
| 「ブロックされています」と表示 | 15 分待つか管理者にブロック解除を依頼 |
| 申請フォームが途中で消えた | 同じ QR を再スキャンしてフォームを開き直す（入力内容は自動保存済み） |
| オフライン時に申請したい | Wi-Fi / モバイルデータ接続を確認してから再試行 |

---

## テスト実行

### バックエンドテスト（Python / pytest）

```bash
# 全テストを実行（コンテナ内で）
make test

# 詳細出力
make test-v

# テスト種別ごとに実行
make test-session   # AsyncSession / rollback テスト
make test-repo      # Worker / Site Repository テスト
make test-health    # Health API テスト
make test-auth      # 認証・権限基盤テスト
make test-qr        # 公開 QR 認証基盤テスト
make test-worker    # 作業員入力・Draft 管理基盤テスト
make test-approval    # 管理側承認・審査フローテスト
make test-site-admin  # 現場・QR 管理フローテスト

# カバレッジ付き（pytest-cov が必要）
make test-cov
```

**注意**: バックエンドテストは PostgreSQL に実際に接続します。`make up` でサービスを起動してから実行してください。

### フロントエンドテスト（TypeScript / Vitest）

```bash
# フロントエンドテストを実行（コンテナ内）
make test-fe

# ウォッチモード（開発中）
make test-fe-watch

# または npm 直接実行（Docker 外で frontend を起動している場合）
cd frontend
npm test           # 一回実行
npm run test:watch # ウォッチモード
npm run test:ui    # ブラウザ UI 付き（Vitest UI）
npm run test:coverage  # カバレッジレポート付き
```

**テスト対象ファイル**:

| ファイル | テスト内容 |
|---|---|
| `src/lib/validation.test.ts` | phone 正規化・カナ・生年月日・郵便番号・必須チェック・文字数 |
| `src/lib/hooks/useAutosave.test.ts` | デバウンス・flush・enabled フラグ・エラー処理・重複防止 |
| `src/app/admin/pending/page.test.tsx` | 一覧表示・承認フロー・差戻しフロー・キーワード検索 |

### Docker 外でのフロントエンド開発（テスト込み）

```bash
# バックエンドを Docker で起動しつつ、フロントエンドはローカル実行
docker compose up -d backend postgres redis

# フロントエンドをローカルで起動（API は localhost:8000 に向ける）
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev

# テストはローカルで実行（DB 不要）
npm test
```

---

## トラブルシューティング

### `docker compose up` 後に backend が起動しない

```bash
# ログを確認
make logs-backend
# または
docker compose logs backend

# よくある原因:
# 1. postgres の起動を待っている（healthcheck が通るまで最大 50 秒）
# 2. requirements.txt のインストールエラー → make build で再ビルド
```

### Alembic マイグレーションが失敗する

```bash
# 現在の状態を確認
docker compose exec backend alembic current

# エラーの原因を特定
docker compose exec backend alembic upgrade head --sql  # SQL を出力して確認

# テーブルが中途半端な状態の場合 → DBをリセット
make migrate-reset

# それでも解決しない場合 → volumes ごとリセット（データ消去）
make clean
make up
make migrate
```

### MinIO コンソールにログインできない

```bash
# .env の値を確認
cat .env | grep MINIO

# minio-init のログを確認（バケット作成が完了しているか）
docker compose logs minio-init

# MinIO が healthy になっているか確認
docker compose ps minio
```

### `/api/health/full` が degraded になる

```bash
# 各サービスの状態を確認
docker compose ps

# 個別のサービスログを確認
docker compose logs redis
docker compose logs minio

# Redis の疎通確認
docker compose exec redis redis-cli -a <REDIS_PASSWORD> ping

# MinIO の疎通確認
curl http://localhost:9000/minio/health/live
```

### DB をリセットしたい

```bash
# マイグレーションのみリセット（データ消去・テーブル再作成）
make migrate-reset

# volumes ごと完全削除（全データ消去・要注意）
make clean
make up
make migrate
```

### フロントエンドのホットリロードが効かない（Windows Docker Desktop）

```bash
# docker-compose.override.yml に WATCHPACK_POLLING が設定されているか確認
grep WATCHPACK docker-compose.override.yml
# → WATCHPACK_POLLING: "true" が表示されれば OK

# もし効かない場合は frontend を再起動
docker compose restart frontend
```

### Windows で `make` コマンドが使えない

```bash
# Git Bash または WSL2 から実行する
# PowerShell / コマンドプロンプトからは make が使えない場合がある

# make なしで同等の操作をする場合:
docker compose up -d                             # make up
docker compose exec backend alembic upgrade head # make migrate
docker compose exec backend pytest -v            # make test-v
```

### ポートが既に使用されている

```bash
# 使用中のポートを確認（Windows）
netstat -ano | findstr :80
netstat -ano | findstr :5432
netstat -ano | findstr :6379

# または別プロセスの Docker Compose を停止
docker compose down
```

### ポートが既に使用されている

```bash
# 使用中のポートを確認
netstat -ano | findstr :80
netstat -ano | findstr :3000
netstat -ano | findstr :8000

# または Docker の別プロジェクトを停止
docker compose down
```

---

## Phase 8 — 本番デプロイ・運用基盤（実装済み）

### 実装内容

| # | 機能 | ファイル |
|---|------|---------|
| 1 | セッションハードニング — refresh token ローテーション + Redis jti 失効 | `backend/app/core/token_store.py`, `backend/app/services/auth.py` |
| 2 | ログアウトエンドポイント — `POST /api/admin/auth/logout` | `backend/app/api/admin/auth.py` |
| 3 | 監査ログ — JSON 構造化ログ（全セキュリティイベント） | `backend/app/core/audit.py` |
| 4 | 5xx エラー監視 — スタックトレース付き ERROR ログ + リクエスト ID | `backend/app/middleware/logging.py`, `backend/app/main.py` |
| 5 | レートリミット強化 — admin_login (5r/min), admin_refresh (10r/min) | `nginx/conf.d/default.prod.conf.template` |
| 6 | セキュリティヘッダー — HSTS, CSP, X-Frame-Options, Referrer-Policy | `nginx/conf.d/default.prod.conf.template` |
| 7 | 本番 Docker Compose — リソース制限, ログローテーション, ネットワーク分離 | `docker-compose.prod.yml` |
| 8 | Nginx 本番設定 — HTTPS/TLS, Let's Encrypt, HTTP→HTTPS リダイレクト | `nginx/conf.d/default.prod.conf.template` |
| 9 | 環境分離 — `.env.production` テンプレート | `.env.production` |
| 10 | バックアップ — PostgreSQL 日次 dump (30 日保持) + MinIO ミラー | `scripts/backup_postgres.sh`, `scripts/backup_minio.sh` |
| 11 | バックアップ Cron コンテナ — 毎日 UTC 02:00 に自動実行 | `scripts/entrypoint_backup.sh`, `scripts/Dockerfile.backup` |
| 12 | リストアスクリプト | `scripts/restore_postgres.sh` |
| 13 | デプロイドキュメント — VPS セットアップ, SSL, バックアップ, 更新手順 | `docs/production-deploy.md` |

### 本番起動方法

```bash
# 環境変数を設定
cp .env.production .env
nano .env  # DOMAIN, SECRET_KEY, パスワード類を必ず変更

# イメージをビルド
make prod-build

# SSL 証明書を取得（初回のみ）
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm certbot \
  certonly --webroot -w /var/www/certbot -d YOUR_DOMAIN \
  --email YOUR_EMAIL --agree-tos --no-eff-email

# 本番起動
make prod-up

# マイグレーション（初回のみ）
docker compose exec backend alembic upgrade head

# 管理者作成（初回のみ）
make create-admin EMAIL=admin@example.com PASSWORD="StrongPass!" NAME="管理者" ROLE=super_admin
```

### セキュリティ機能の概要

```
認証フロー（Phase 8 以降）:
  POST /api/admin/auth/login
    → access_token (30 min) + refresh_token (7 days) を発行
    → 監査ログ: auth.login_success / auth.login_failure / auth.login_locked

  POST /api/admin/auth/refresh
    → refresh_token の jti が Redis に失効登録されていないか確認
    → 新しい access_token + 新しい refresh_token を発行（ローテーション）
    → 旧 refresh_token の jti を Redis に失効登録
    → 監査ログ: auth.token_refresh

  POST /api/admin/auth/logout
    → refresh_token の jti を Redis に即時失効登録
    → 以降の refresh 試行は 401 で拒否
    → 監査ログ: auth.logout

監査ログの確認:
  make audit-logs       # 最新 50 件
  docker compose logs backend | grep '"event":'
```

詳細は [`docs/production-deploy.md`](./docs/production-deploy.md) を参照してください。

---

## Phase 9: 実地運用テスト・UX 改善

目的: **「朝の現場で止まらない」** — 実際の建設現場で試験運用して現場 UX の問題点を潰す。

### 実装済み機能

| # | 機能 | 説明 | 主なファイル |
|---|------|------|-------------|
| 1 | **超短縮再入場フロー** | 電話番号+生年月日(月日)で 30 秒以内の再入場申請 | `POST /api/public/workers/quick-match`, `/entry/[token]/quick/page.tsx` |
| 2 | **Pending バッジ通知** | ヘッダーに未承認件数バッジ（90 秒ポーリング）、30 分超過で警告 | `GET /api/admin/badges`, `admin/layout.tsx` |
| 3 | **朝礼モード** | 本日の申請一覧（pending 優先）+ 過去 30 日運用メトリクス | `GET /api/admin/morning-brief`, `/admin/morning/page.tsx` |
| 4 | **運用メトリクス** | 申請数・承認数・平均承認時間・30 分超過件数 | `GET /api/admin/metrics/summary` |
| 5 | **オフラインキュー** | ネットワーク断絶時にドラフトを localStorage に保存、復帰後に自動再送 | `lib/hooks/useOfflineQueue.ts` |
| 6 | **高齢者モード** | フォント拡大・ボタン拡大・高コントラスト（localStorage 永続化） | `lib/context/ElderlyModeContext.tsx`, `globals.css` |
| 7 | **トラブル対応 UI** | QR エラー画面に紙フォールバック案内・担当者連絡ガイド | `components/admin/TroubleHelp.tsx` |
| 8 | **UX フィードバック** | 管理者が「入力しにくい」等のカテゴリ+コメントを送信 | `POST /api/admin/feedback`, `admin/layout.tsx（💬ボタン）` |

### エンドポイント一覧（Phase 9 追加分）

```
# 公開 API（entry_session 必須）
POST /api/public/workers/quick-match   超短縮再入場フロー（電話番号+月日照合）

# 管理者 API（access_token 必須）
GET  /api/admin/badges                 pending バッジカウント（ロールスコープ付き）
GET  /api/admin/morning-brief          朝礼モード: 本日の申請一覧
GET  /api/admin/metrics/summary        過去 30 日の運用メトリクス
POST /api/admin/feedback               UX フィードバック（4 カテゴリ）
```

### DB マイグレーション（Phase 9）

```bash
# Migration 0006: ux_feedback テーブル追加
make migrate
```

### 超短縮再入場フロー の使い方

```
1. 作業員がスマホで QR を読む（通常通り）
2. /entry/[token]/form の Step 1 に「⚡ かんたん再入場（30秒）」ボタン
3. タップ → 電話番号 + 生まれ月・日を入力
4. 一致 → 氏名確認 + 入場日 + 健康チェック + 同意 → 申請完了
5. 不一致 → 通常フォームへ案内
```

### 朝礼モード の使い方

```
1. 管理者ヘッダーの「朝礼」リンク → /admin/morning
2. 本日の申請一覧（pending 優先、30 分超過は赤表示）
3. 過去 30 日の運用メトリクス（平均承認時間が 30 分超えると赤）
4. 「更新」ボタンで手動更新
```

### 高齢者モード の使い方

```
1. 管理者ヘッダーの「👴」ボタンをタップ
2. フォントサイズ・ボタン高さが大きくなる
3. 設定は localStorage に保存（次回ログイン時も引き継がれる）
4. もう一度タップでオフに
```

