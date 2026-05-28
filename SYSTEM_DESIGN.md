# 建設工事 新規入場管理システム 設計書

> 作成日: 2026-05-19  
> バージョン: 1.0

---

## 1. システム構成図

```
┌─────────────────────────────────────────────────────────────────┐
│                          Internet                                │
│                                                                  │
│  ┌──────────────┐        ┌─────────────────────────────────┐    │
│  │ 協力業者/     │  QR   │          Nginx (HTTPS)           │    │
│  │ 一人親方      │──────▶│  ┌──────────────────────────┐   │    │
│  │ スマートフォン │       │  │  /entry/*  公開フォーム   │   │    │
│  └──────────────┘        │  │  /admin/*  社内限定(IP制限)│   │    │
│                           │  └──────────────────────────┘   │    │
│  ┌──────────────┐         │                │                  │    │
│  │ 現場監督/    │ 社内LAN │                ▼                  │    │
│  │ 管理者       │────────▶│        Next.js (PWA)             │    │
│  │ PC/スマホ    │         │     (フロントエンド)               │    │
│  └──────────────┘         └──────────────┬──────────────────┘    │
│                                           │                       │
│                           ┌───────────────▼───────────────┐       │
│                           │         FastAPI                │       │
│                           │      (バックエンドAPI)           │       │
│                           └──┬──────────┬──────────┬──────┘       │
│                              │          │          │               │
│                    ┌─────────▼──┐ ┌─────▼────┐ ┌──▼──────────┐   │
│                    │ PostgreSQL  │ │  MinIO   │ │    Redis     │   │
│                    │  (メインDB) │ │ (ファイル) │ │ (セッション)  │   │
│                    └────────────┘ └──────────┘ └─────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 技術スタック

| レイヤー | 技術 | 理由 |
|---------|------|------|
| フロントエンド | Next.js 14 (App Router) + PWA | SSR/SSG・PWA対応・1リポジトリで公開/管理画面 |
| バックエンド | FastAPI (Python 3.12) | 高速・型安全・自動ドキュメント生成 |
| DB | PostgreSQL 16 | 信頼性・JSON対応・全文検索 |
| ファイルストレージ | MinIO | S3互換・オンプレ運用可能 |
| キャッシュ/セッション | Redis 7 | JWT失効管理・レート制限 |
| リバースプロキシ | Nginx | IP制限・HTTPS終端・静的配信 |
| コンテナ | Docker Compose | 環境統一・デプロイ簡略化 |
| PDF生成 | WeasyPrint | Python統合・HTML→PDF変換 |
| QR生成 | qrcode (Python) | サーバーサイド生成 |

---

## 2. DB設計（ER図）

```
companies ─────────────────────────────────────────┐
    │ 1                                             │
    │ N                                             │
  sites ─────────────────────────────────────────┐  │
    │ 1          1 site_qr_codes                  │  │
    │            (QRコード)                        │  │
    │ N                                            │  │
entry_applications ────────────────────────────────┘  │
    │ 1                                              │
    │ N                                              │
entry_documents                                      │
(添付ファイル)                                         │
    │                                               │
approval_logs ──────────────────── admin_users ──────┘
(承認ログ)                         (管理者)
```

---

## 3. テーブル設計

### 3.1 companies（会社）

```sql
CREATE TABLE companies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,           -- 会社名
    name_kana       VARCHAR(200),                     -- 会社名カナ
    postal_code     VARCHAR(8),                       -- 郵便番号
    address         TEXT,                             -- 住所
    phone           VARCHAR(20),                      -- 電話番号
    representative  VARCHAR(100),                     -- 代表者名
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 3.2 admin_users（管理者・現場監督）

```sql
CREATE TYPE admin_role AS ENUM ('super_admin', 'admin', 'supervisor');

CREATE TABLE admin_users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID NOT NULL REFERENCES companies(id),
    email           VARCHAR(254) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    name            VARCHAR(100) NOT NULL,
    role            admin_role NOT NULL DEFAULT 'supervisor',
    is_active       BOOLEAN NOT NULL DEFAULT true,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_admin_users_company ON admin_users(company_id);
CREATE INDEX idx_admin_users_email ON admin_users(email);
```

### 3.3 sites（現場）

```sql
CREATE TABLE sites (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID NOT NULL REFERENCES companies(id),
    name            VARCHAR(200) NOT NULL,            -- 現場名
    address         TEXT,                             -- 現場住所
    start_date      DATE,                             -- 工期開始
    end_date        DATE,                             -- 工期終了
    supervisor_id   UUID REFERENCES admin_users(id),  -- 担当監督
    description     TEXT,                             -- 備考
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sites_company ON sites(company_id);
CREATE INDEX idx_sites_supervisor ON sites(supervisor_id);
```

### 3.4 site_qr_codes（QRコード）

```sql
CREATE TABLE site_qr_codes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id         UUID NOT NULL REFERENCES sites(id),
    token           VARCHAR(64) NOT NULL UNIQUE,      -- URLトークン（推測不可能）
    qr_image_path   VARCHAR(500),                     -- QR画像保存パス
    is_active       BOOLEAN NOT NULL DEFAULT true,
    expires_at      TIMESTAMPTZ,                      -- 有効期限（NULL=無期限）
    created_by      UUID REFERENCES admin_users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_qr_codes_site ON site_qr_codes(site_id);
CREATE INDEX idx_qr_codes_token ON site_qr_codes(token);
```

### 3.5 entry_applications（入場申請）

```sql
CREATE TYPE application_status AS ENUM (
    'pending',      -- 申請中
    'approved',     -- 承認済
    'rejected',     -- 差戻し
    'withdrawn'     -- 取下げ
);

CREATE TYPE worker_type AS ENUM (
    'company_employee',   -- 協力会社社員
    'sole_proprietor'     -- 一人親方
);

CREATE TABLE entry_applications (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id             UUID NOT NULL REFERENCES sites(id),
    qr_code_id          UUID NOT NULL REFERENCES site_qr_codes(id),

    -- 申請者情報
    worker_type         worker_type NOT NULL,
    last_name           VARCHAR(50) NOT NULL,          -- 姓
    first_name          VARCHAR(50) NOT NULL,          -- 名
    last_name_kana      VARCHAR(50),                   -- 姓カナ
    first_name_kana     VARCHAR(50),                   -- 名カナ
    birth_date          DATE NOT NULL,                 -- 生年月日
    gender              VARCHAR(10),                   -- 性別
    postal_code         VARCHAR(8),                    -- 郵便番号
    address             TEXT,                          -- 住所
    phone               VARCHAR(20) NOT NULL,          -- 電話番号
    emergency_contact   VARCHAR(20),                   -- 緊急連絡先

    -- 所属情報
    affiliation_company VARCHAR(200),                  -- 所属会社名（一人親方はNULL可）
    job_title           VARCHAR(100),                  -- 職種・工種
    experience_years    INTEGER,                       -- 経験年数

    -- 資格情報（JSON配列）
    certifications      JSONB DEFAULT '[]',

    -- 保険情報
    insurance_type      VARCHAR(100),                  -- 保険種別
    insurance_number    VARCHAR(100),                  -- 保険番号

    -- 健康情報
    has_health_check    BOOLEAN DEFAULT false,         -- 健康診断受診済
    health_check_date   DATE,                          -- 健康診断日

    -- 申請ステータス
    status              application_status NOT NULL DEFAULT 'pending',
    rejection_reason    TEXT,                          -- 差戻し理由

    -- メタ情報
    submit_ip           INET,                          -- 送信元IP（個人情報保護のため暗号化推奨）
    submit_user_agent   TEXT,                          -- UA
    submitted_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_applications_site ON entry_applications(site_id);
CREATE INDEX idx_applications_status ON entry_applications(status);
CREATE INDEX idx_applications_submitted ON entry_applications(submitted_at DESC);
```

### 3.6 entry_documents（添付書類）

```sql
CREATE TYPE document_type AS ENUM (
    'health_check',        -- 健康診断書
    'certification',       -- 資格証明書
    'insurance_card',      -- 保険証
    'skill_training',      -- 技能講習修了証
    'other'                -- その他
);

CREATE TABLE entry_documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id  UUID NOT NULL REFERENCES entry_applications(id) ON DELETE CASCADE,
    document_type   document_type NOT NULL,
    original_name   VARCHAR(500) NOT NULL,            -- 元ファイル名
    storage_path    VARCHAR(1000) NOT NULL,           -- ストレージパス（暗号化済）
    mime_type       VARCHAR(100) NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    checksum        VARCHAR(64),                       -- SHA256
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_documents_application ON entry_documents(application_id);
```

### 3.7 approval_logs（承認ログ）

```sql
CREATE TYPE approval_action AS ENUM ('approved', 'rejected', 'pending_reset');

CREATE TABLE approval_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id  UUID NOT NULL REFERENCES entry_applications(id),
    admin_user_id   UUID NOT NULL REFERENCES admin_users(id),
    action          approval_action NOT NULL,
    comment         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_approval_logs_application ON approval_logs(application_id);
```

---

## 4. API一覧

### 公開API（認証不要 / レート制限あり）

| メソッド | エンドポイント | 説明 |
|---------|--------------|------|
| GET | `/api/public/qr/{token}` | QRトークン検証・現場情報取得 |
| POST | `/api/public/applications` | 入場申請送信 |
| POST | `/api/public/applications/{id}/documents` | 書類アップロード |
| GET | `/api/public/applications/{id}/status` | 申請状況確認（受付番号方式） |

### 管理者API（JWT認証必須 / 社内IP限定）

#### 認証

| メソッド | エンドポイント | 説明 |
|---------|--------------|------|
| POST | `/api/admin/auth/login` | ログイン |
| POST | `/api/admin/auth/logout` | ログアウト |
| POST | `/api/admin/auth/refresh` | トークンリフレッシュ |
| GET | `/api/admin/auth/me` | 自分の情報取得 |

#### 現場管理

| メソッド | エンドポイント | 説明 | 権限 |
|---------|--------------|------|------|
| GET | `/api/admin/sites` | 現場一覧 | admin+ |
| POST | `/api/admin/sites` | 現場作成 | admin+ |
| GET | `/api/admin/sites/{id}` | 現場詳細 | supervisor+ |
| PUT | `/api/admin/sites/{id}` | 現場更新 | admin+ |
| DELETE | `/api/admin/sites/{id}` | 現場削除 | super_admin |

#### QRコード管理

| メソッド | エンドポイント | 説明 | 権限 |
|---------|--------------|------|------|
| GET | `/api/admin/sites/{id}/qrcodes` | QR一覧 | supervisor+ |
| POST | `/api/admin/sites/{id}/qrcodes` | QR発行 | admin+ |
| PUT | `/api/admin/sites/{id}/qrcodes/{qid}/deactivate` | QR無効化 | admin+ |
| GET | `/api/admin/sites/{id}/qrcodes/{qid}/image` | QR画像取得 | supervisor+ |

#### 入場申請管理

| メソッド | エンドポイント | 説明 | 権限 |
|---------|--------------|------|------|
| GET | `/api/admin/applications` | 申請一覧（フィルタ・ページネーション） | supervisor+ |
| GET | `/api/admin/applications/{id}` | 申請詳細 | supervisor+ |
| PUT | `/api/admin/applications/{id}/approve` | 承認 | supervisor+ |
| PUT | `/api/admin/applications/{id}/reject` | 差戻し | supervisor+ |
| GET | `/api/admin/applications/{id}/documents/{did}` | 書類取得 | supervisor+ |
| GET | `/api/admin/applications/{id}/pdf` | PDF出力 | supervisor+ |

#### ユーザー管理

| メソッド | エンドポイント | 説明 | 権限 |
|---------|--------------|------|------|
| GET | `/api/admin/users` | ユーザー一覧 | admin+ |
| POST | `/api/admin/users` | ユーザー作成 | admin+ |
| PUT | `/api/admin/users/{id}` | ユーザー更新 | admin+ |
| DELETE | `/api/admin/users/{id}` | ユーザー削除 | super_admin |

#### レポート・エクスポート

| メソッド | エンドポイント | 説明 | 権限 |
|---------|--------------|------|------|
| GET | `/api/admin/reports/summary` | サマリーダッシュボードデータ | supervisor+ |
| GET | `/api/admin/sites/{id}/applications/export` | CSV一括エクスポート | admin+ |

---

## 5. 画面一覧

### 公開画面（スマートフォン向け・外部アクセス可）

| 画面名 | URL | 説明 |
|--------|-----|------|
| QRランディング | `/entry/{token}` | QR読込後の最初の画面。現場名・注意事項表示 |
| 個人情報同意 | `/entry/{token}/consent` | 個人情報取り扱い同意 |
| 入場申請フォーム | `/entry/{token}/form` | 申請情報入力（多段階フォーム） |
| 書類アップロード | `/entry/{token}/documents` | 資格証等の写真アップロード |
| 申請完了 | `/entry/{token}/complete` | 受付番号表示・保存案内 |
| 申請状況確認 | `/entry/status/{application_id}` | 承認状況確認ページ |

**フォームのステップ構成（公開フォーム）:**
```
Step 1: 申請者区分選択（協力会社社員 / 一人親方）
Step 2: 基本情報（氏名・生年月日・住所・電話）
Step 3: 所属・職種情報
Step 4: 資格・保険情報
Step 5: 書類アップロード
Step 6: 確認・送信
```

### 管理画面（PC向け・社内限定）

| 画面名 | URL | 説明 |
|--------|-----|------|
| ログイン | `/admin/login` | メール＋パスワード認証 |
| ダッシュボード | `/admin` | 未承認件数・現場別状況サマリー |
| 現場一覧 | `/admin/sites` | 現場の一覧・検索・新規作成 |
| 現場詳細 | `/admin/sites/{id}` | 現場情報・QRコード管理・申請一覧 |
| 現場作成/編集 | `/admin/sites/new` | 現場情報入力フォーム |
| QRコード管理 | `/admin/sites/{id}/qrcodes` | QR発行・印刷・無効化 |
| 申請一覧 | `/admin/applications` | 全現場の申請一覧・フィルタ |
| 申請詳細 | `/admin/applications/{id}` | 申請内容確認・書類閲覧・承認操作 |
| PDF出力 | `/admin/applications/{id}/pdf` | 申請書PDFプレビュー |
| ユーザー管理 | `/admin/users` | 管理者・監督者アカウント管理 |
| 設定 | `/admin/settings` | 会社情報・システム設定 |

---

## 6. 権限設計

### ロール定義

| ロール | 説明 |
|--------|------|
| `super_admin` | 全機能＋会社設定・ユーザー削除 |
| `admin` | 現場管理・QR発行・ユーザー作成・エクスポート |
| `supervisor` | 担当現場の申請確認・承認・差戻し |

### 権限マトリクス

| 機能 | super_admin | admin | supervisor |
|------|:-----------:|:-----:|:----------:|
| 会社設定変更 | ✅ | ❌ | ❌ |
| ユーザー作成 | ✅ | ✅ | ❌ |
| ユーザー削除 | ✅ | ❌ | ❌ |
| 現場作成・編集 | ✅ | ✅ | ❌ |
| 現場削除 | ✅ | ❌ | ❌ |
| QRコード発行 | ✅ | ✅ | ❌ |
| QRコード無効化 | ✅ | ✅ | ❌ |
| 申請一覧閲覧 | 全現場 | 全現場 | 担当現場のみ |
| 申請承認・差戻し | ✅ | ✅ | ✅ |
| 書類閲覧 | ✅ | ✅ | ✅ |
| PDF出力 | ✅ | ✅ | ✅ |
| CSVエクスポート | ✅ | ✅ | ❌ |

### アクセス制御実装方針

- 認証: JWT (アクセストークン 1h / リフレッシュトークン 7d)
- リフレッシュトークンはRedisで管理（失効処理可能）
- supervisorは `site.supervisor_id = user.id` で担当現場のみアクセス可
- 管理画面全体をNginxのIP制限で社内ネットワーク限定に絞る

---

## 7. Docker構成

### ディレクトリ構成

```
patrol-entry/
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
├── nginx/
│   ├── Dockerfile
│   ├── nginx.conf
│   └── conf.d/
│       ├── public.conf       # 公開フォーム
│       └── admin.conf        # 管理画面（IP制限）
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
├── minio/
│   └── init-buckets.sh
└── postgres/
    └── init.sql
```

### docker-compose.yml

```yaml
version: '3.9'

services:
  nginx:
    build: ./nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/conf.d:/etc/nginx/conf.d
      - ./certs:/etc/ssl/certs:ro
    depends_on:
      - frontend
      - backend
    restart: unless-stopped

  frontend:
    build: ./frontend
    environment:
      - NEXT_PUBLIC_API_URL=/api
    depends_on:
      - backend
    restart: unless-stopped

  backend:
    build: ./backend
    environment:
      - DATABASE_URL=postgresql://app:${DB_PASSWORD}@postgres:5432/entry_db
      - REDIS_URL=redis://redis:6379
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ACCESS_KEY=${MINIO_ACCESS_KEY}
      - MINIO_SECRET_KEY=${MINIO_SECRET_KEY}
      - JWT_SECRET=${JWT_SECRET}
      - ALLOWED_ADMIN_IPS=${ALLOWED_ADMIN_IPS}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
      minio:
        condition: service_started
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    environment:
      - POSTGRES_DB=entry_db
      - POSTGRES_USER=app
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./postgres/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d entry_db"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    restart: unless-stopped

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      - MINIO_ROOT_USER=${MINIO_ACCESS_KEY}
      - MINIO_ROOT_PASSWORD=${MINIO_SECRET_KEY}
    volumes:
      - minio_data:/data
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  minio_data:
```

### Nginx IP制限設定（admin.conf）

```nginx
# 管理画面：社内IPのみ許可
server {
    listen 443 ssl;
    server_name admin.example.com;

    # 社内IPホワイトリスト
    allow 192.168.0.0/16;
    allow 10.0.0.0/8;
    deny all;

    location / {
        proxy_pass http://frontend:3000;
    }

    location /api/admin/ {
        proxy_pass http://backend:8000;
    }
}

# 公開フォーム：全アクセス許可（レート制限あり）
server {
    listen 443 ssl;
    server_name entry.example.com;

    limit_req_zone $binary_remote_addr zone=entry_limit:10m rate=10r/m;

    location /entry/ {
        limit_req zone=entry_limit burst=5 nodelay;
        proxy_pass http://frontend:3000;
    }

    location /api/public/ {
        limit_req zone=entry_limit burst=5 nodelay;
        proxy_pass http://backend:8000;
    }
}
```

---

## 8. セキュリティ設計

### 8.1 通信セキュリティ

| 対策 | 実装方法 |
|------|---------|
| HTTPS強制 | Nginx + Let's Encrypt / 自社証明書 |
| HSTS | `Strict-Transport-Security: max-age=31536000` |
| セキュリティヘッダー | CSP・X-Frame-Options・X-Content-Type-Options |
| CORS | 公開フォームドメインのみ許可 |

### 8.2 認証・認可

| 対策 | 実装方法 |
|------|---------|
| パスワード | bcrypt (cost=12) ハッシュ化 |
| JWT | RS256署名・短期アクセストークン(1h) |
| リフレッシュトークン | Redis管理・明示的失効可能 |
| ログイン失敗制限 | 5回失敗で15分ロック（Redis） |
| 管理画面IPホワイトリスト | Nginxで社内IPのみ通過 |

### 8.3 入力バリデーション

| 対策 | 実装方法 |
|------|---------|
| 入力検証 | Pydantic (FastAPI) でスキーマ検証 |
| SQLインジェクション | SQLAlchemy ORM・パラメータバインド |
| XSS | DOMPurify (フロント) + HTMLエスケープ |
| ファイルアップロード | MIMEタイプ検証・ファイルサイズ制限(10MB) |
| ファイル種別 | PDF・JPEG・PNG・GIF のみ許可 |
| ウイルススキャン | ClamAV連携（オプション） |

### 8.4 個人情報保護

| 対策 | 実装方法 |
|------|---------|
| 送信元IP暗号化 | DBに保存する前にAES暗号化 |
| アクセスログ | 個人情報をマスキングしてログ出力 |
| ファイル保存 | MinIOバケット非公開・署名付きURL方式 |
| データ保持期間 | 申請から3年後に自動削除（設定可能） |
| 監査ログ | 書類閲覧・承認操作を全記録 |
| バックアップ | 暗号化バックアップ |

### 8.5 QRコードセキュリティ

| 対策 | 実装方法 |
|------|---------|
| トークン | 64文字のランダム文字列（推測不可能） |
| 有効期限 | 現場工期に連動した自動期限設定 |
| 無効化 | 管理者が即時無効化可能 |
| レート制限 | 1IPから10リクエスト/分の制限 |
| ワンタイム制限 | 同一IPから同一QRへの繰り返し申請を検知 |

### 8.6 レート制限設計

```
公開API:
  - QRトークン検証: 30回/時/IP
  - 申請送信: 5回/時/IP
  - ファイルアップロード: 20回/時/IP

管理API:
  - ログイン試行: 5回/15分/IP
  - 一般操作: 300回/時/ユーザー
```

---

## 9. MVP機能一覧

### Phase 1 MVP（最小リリース）

| # | 機能 | 優先度 |
|---|------|--------|
| 1 | 現場作成・QRコード発行 | 必須 |
| 2 | QR読込→入場申請フォーム（基本項目） | 必須 |
| 3 | 申請送信・受付番号発行 | 必須 |
| 4 | 管理者ログイン（メール＋パスワード） | 必須 |
| 5 | 申請一覧・詳細閲覧 | 必須 |
| 6 | 承認・差戻し操作 | 必須 |
| 7 | 基本的な個人情報保護対策 | 必須 |
| 8 | HTTPS・IP制限 | 必須 |

### Phase 2（リリース後1〜2ヶ月）

| # | 機能 | 優先度 |
|---|------|--------|
| 9 | 書類（PDF・画像）アップロード | 高 |
| 10 | 申請書PDF出力 | 高 |
| 11 | ダッシュボード（集計・グラフ） | 高 |
| 12 | メール通知（申請受付・承認完了） | 高 |
| 13 | PWAマニフェスト・オフライン対応 | 中 |

### Phase 3（リリース後3〜4ヶ月）

| # | 機能 | 優先度 |
|---|------|--------|
| 14 | CSVエクスポート | 中 |
| 15 | 申請データ検索・高度フィルタ | 中 |
| 16 | QRコード印刷用デザイン | 中 |
| 17 | 多現場一括管理ビュー | 低 |
| 18 | 申請履歴・再申請機能 | 低 |
| 19 | データ自動削除スケジューラ | 低 |

---

## 10. 開発ステップ

### Step 1: 環境構築（1週間）

```
□ Dockerfileとdocker-compose.yml作成
□ PostgreSQL・Redis・MinIO起動確認
□ Nginx設定（IP制限・SSL）
□ FastAPI骨格プロジェクト作成
□ Next.js骨格プロジェクト作成
□ GitHub Actions CI設定（lint・typecheck）
□ .env.exampleと環境変数整理
```

### Step 2: DBとバックエンド基盤（2週間）

```
□ Alembicでマイグレーション設定
□ 全テーブル作成
□ SQLAlchemy ORMモデル定義
□ 管理者認証API（ログイン・JWT発行・リフレッシュ）
□ 権限ミドルウェア（role_required デコレータ）
□ レート制限ミドルウェア（Redis）
□ ファイルアップロード基盤（MinIO連携）
□ API自動テスト基盤（pytest）
```

### Step 3: 公開フォーム実装（2週間）

```
□ QRランディングページ
□ 個人情報同意ページ
□ 多段階入場申請フォーム（React Hook Form + Zod）
□ 書類アップロードUI
□ 申請完了・受付番号表示
□ 申請状況確認ページ
□ スマートフォン最適化（レスポンシブ）
□ PWAマニフェスト設定
□ バリデーション・エラーハンドリング
```

### Step 4: 管理画面実装（2週間）

```
□ ログイン画面
□ ダッシュボード（基本サマリー）
□ 現場一覧・作成・編集
□ QRコード発行・表示・印刷
□ 申請一覧（フィルタ・ページネーション）
□ 申請詳細・書類閲覧
□ 承認・差戻しアクション
□ ユーザー管理画面
```

### Step 5: PDF・エクスポート（1週間）

```
□ WeasyPrint環境構築
□ 申請書PDFテンプレート（HTML→PDF）
□ QRコード印刷用PDFシート
□ CSVエクスポート機能
```

### Step 6: セキュリティ強化・テスト（1週間）

```
□ 全API入力バリデーション確認
□ OWASP Top 10 チェックリスト確認
□ ファイルアップロード制限テスト
□ ログイン失敗ロック動作確認
□ IP制限動作確認
□ 負荷テスト（locust）
□ 個人情報マスキング確認
□ 全機能E2Eテスト（Playwright）
```

### Step 7: 本番デプロイ・引き渡し（1週間）

```
□ 本番環境サーバー構築
□ SSL証明書設定
□ バックアップ設定
□ 監視設定（Uptime・エラー通知）
□ 運用マニュアル作成
□ 管理者向け操作説明
□ データ削除ポリシー設定
```

### 開発スケジュール概要

```
Week 1:  環境構築
Week 2-3: バックエンド基盤
Week 4-5: 公開フォーム
Week 6-7: 管理画面
Week 8:  PDF・エクスポート
Week 9:  セキュリティテスト
Week 10: 本番デプロイ

合計目安: 約10週間（2.5ヶ月）
```

---

## 付録: ファイルアップロード制限仕様

| 項目 | 制限値 |
|------|--------|
| 最大ファイルサイズ | 10MB / ファイル |
| 申請あたり最大ファイル数 | 10ファイル |
| 許可MIMEタイプ | image/jpeg, image/png, image/gif, application/pdf |
| ファイル名サニタイズ | UUIDに変換してMinIOに保存 |
| アクセス方式 | 署名付きURL（有効期限15分）|

## 付録: PWA設定

```json
// public/manifest.json
{
  "name": "新規入場申請",
  "short_name": "入場申請",
  "description": "建設現場 新規入場申請システム",
  "start_url": "/entry",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#1a56db",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```
