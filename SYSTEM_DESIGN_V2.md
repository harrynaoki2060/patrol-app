# 建設工事 新規入場管理システム 設計書 V2

> 作成日: 2026-05-19  
> バージョン: 2.0（実運用向け改訂版）  
> 前バージョン: SYSTEM_DESIGN.md (v1.0)

---

## 1. 改善後システム概要

### 設計思想の転換

| 観点 | V1（申請中心） | V2（作業員中心） |
|------|--------------|----------------|
| データ構造 | 申請ごとに個人情報を保存 | 作業員マスター＋現場入場レコードで分離 |
| 再利用性 | 現場が変わるたびに全情報を再入力 | 2回目以降は電話番号照合→確認のみ |
| 資格管理 | JSONB列に埋め込み | 専用テーブルで期限管理可能 |
| QRセキュリティ | トークンのみ | トークン＋PIN＋使用回数制限 |
| ファイル | JPG/PNG/PDFのみ | HEIC変換・自動圧縮・サムネイル生成 |
| 監督UI | PC管理画面のみ | モバイル最適化の承認専用ビュー追加 |

### 技術スタック（更新）

| レイヤー | 技術 | 変更点 |
|---------|------|--------|
| フロントエンド | Next.js 14 (App Router) + PWA | 変更なし |
| バックエンド | FastAPI (Python 3.12) | 画像処理ライブラリ追加 |
| DB | PostgreSQL 16 | スキーマ大幅拡張 |
| ファイルストレージ | MinIO | バケット構成変更 |
| 画像処理 | Pillow + pillow-heif | **NEW**: HEIC変換・自動圧縮 |
| サムネイル | Pillow | **NEW**: 書類サムネイル生成 |
| PDF生成 | WeasyPrint | 帳票テンプレート拡充 |
| キャッシュ | Redis 7 | QR使用回数・一時保存追加 |
| リバースプロキシ | Nginx | レート制限強化 |
| コンテナ | Docker Compose | 変更なし |

### システム全体構成

```
┌──────────────────────────────────────────────────────────────────────┐
│                             Internet                                   │
│                                                                        │
│  ┌──────────────────┐   QR読込    ┌──────────────────────────────┐   │
│  │  協力業者/一人親方  │ ──────────▶│         Nginx (HTTPS)         │   │
│  │  スマートフォン    │            │  ┌─────────────────────────┐  │   │
│  └──────────────────┘            │  │ entry.example.com        │  │   │
│                                   │  │ 公開フォーム (全IP許可)    │  │   │
│  ┌──────────────────┐            │  ├─────────────────────────┤  │   │
│  │  現場監督          │  社内LAN  │  │ admin.example.com        │  │   │
│  │  スマホ（承認用）   │ ─────────▶│  │ 管理画面 (社内IPのみ)    │  │   │
│  └──────────────────┘            │  └─────────────────────────┘  │   │
│                                   └──────────────┬───────────────┘   │
│  ┌──────────────────┐                            │                    │
│  │  社内管理者        │  社内LAN                  ▼                    │
│  │  PC               │ ─────────▶        Next.js (PWA)               │
│  └──────────────────┘            ┌──────────────┴───────────────┐    │
│                                   │           FastAPI              │    │
│                                   │  ┌────────────────────────┐  │    │
│                                   │  │ 公開Router  管理Router  │  │    │
│                                   │  │ 画像処理    PDF生成      │  │    │
│                                   │  └────────────────────────┘  │    │
│                                   └──┬──────────┬───────────┬────┘    │
│                                      │          │           │          │
│                             ┌────────▼──┐ ┌─────▼────┐ ┌───▼──────┐  │
│                             │ PostgreSQL │ │  MinIO   │ │  Redis   │  │
│                             │  (メインDB)│ │ (ファイル)│ │(QR/Session│  │
│                             └───────────┘ └──────────┘ └──────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. 更新DB設計

### 設計方針

```
【作業員ライフサイクル】

初回入場時:
  スマホでQR読込 → 電話番号入力 → 「初めてですか？」
  → YES: フル情報入力 → workers テーブルに登録
  → NO:  既存データ確認・修正 → worker_site_entries に追加

2回目以降:
  QR読込 → 電話番号入力 → 本人確認 → 現場入場申請のみ
  （氏名・住所等の再入力不要）

【データの分離原則】
  workers            : 作業員の固定情報（変わりにくいもの）
  worker_qualifications : 資格・期限（更新が必要なもの）
  worker_site_entries   : 現場単位の入場記録（現場ごとに作成）
  worker_documents      : 書類ファイル（資格証・健康診断等）
```

### MinIOバケット構成

```
バケット: entry-documents/
  workers/{worker_id}/face/            # 顔写真
  workers/{worker_id}/qualifications/  # 資格証画像
  workers/{worker_id}/health/          # 健康診断書
  workers/{worker_id}/insurance/       # 保険証
  workers/{worker_id}/thumbnails/      # 全画像のサムネイル
  sites/{site_id}/qrcodes/             # QR画像
  exports/{date}/                      # CSV/PDFエクスポート（7日TTL）
```

---

## 3. テーブル設計（全テーブル）

### 3.1 companies（会社マスター）

```sql
CREATE TABLE companies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,
    name_kana       VARCHAR(200),
    postal_code     VARCHAR(8),
    address         TEXT,
    phone           VARCHAR(20),
    representative  VARCHAR(100),
    logo_path       VARCHAR(500),       -- PDF帳票用ロゴ
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 3.2 admin_users（管理者・現場監督）

```sql
CREATE TYPE admin_role AS ENUM ('super_admin', 'admin', 'supervisor');

CREATE TABLE admin_users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id          UUID NOT NULL REFERENCES companies(id),
    email               VARCHAR(254) NOT NULL UNIQUE,
    password_hash       VARCHAR(255) NOT NULL,
    name                VARCHAR(100) NOT NULL,
    role                admin_role NOT NULL DEFAULT 'supervisor',
    phone               VARCHAR(20),
    is_active           BOOLEAN NOT NULL DEFAULT true,
    login_failure_count INTEGER NOT NULL DEFAULT 0,
    locked_until        TIMESTAMPTZ,               -- ログイン失敗ロック
    last_login_at       TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_admin_users_company ON admin_users(company_id);
CREATE INDEX idx_admin_users_email ON admin_users(email);
```

### 3.3 sites（現場）

```sql
CREATE TABLE sites (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID NOT NULL REFERENCES companies(id),
    name            VARCHAR(200) NOT NULL,
    address         TEXT,
    start_date      DATE,
    end_date        DATE,
    supervisor_id   UUID REFERENCES admin_users(id),
    description     TEXT,
    -- 入場フォームのカスタム設定
    require_health_check    BOOLEAN NOT NULL DEFAULT true,
    require_insurance       BOOLEAN NOT NULL DEFAULT true,
    custom_notice           TEXT,      -- QRランディングに表示する注意事項
    is_active               BOOLEAN NOT NULL DEFAULT true,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sites_company ON sites(company_id);
CREATE INDEX idx_sites_supervisor ON sites(supervisor_id);
CREATE INDEX idx_sites_active ON sites(is_active, end_date);
```

### 3.4 site_qr_codes（QRコード・セキュリティ強化版）

```sql
CREATE TABLE site_qr_codes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id             UUID NOT NULL REFERENCES sites(id),
    token               VARCHAR(64) NOT NULL UNIQUE,   -- URLトークン（32バイトランダム）
    pin_code            VARCHAR(6),                    -- 4〜6桁PIN（bcryptハッシュ）
    pin_required        BOOLEAN NOT NULL DEFAULT false,
    qr_image_path       VARCHAR(500),
    label               VARCHAR(100),                  -- 「北ゲート用」等の管理ラベル
    -- セキュリティ制限
    is_active           BOOLEAN NOT NULL DEFAULT true,
    expires_at          TIMESTAMPTZ,                   -- 有効期限（NULL=工期終了日に連動）
    max_uses            INTEGER,                       -- 最大使用回数（NULL=無制限）
    use_count           INTEGER NOT NULL DEFAULT 0,    -- 現在の使用回数
    allowed_hours_start TIME,                          -- 受付時間帯（例: 06:00）
    allowed_hours_end   TIME,                          -- 受付時間帯（例: 09:00）
    -- 管理
    created_by          UUID REFERENCES admin_users(id),
    deactivated_by      UUID REFERENCES admin_users(id),
    deactivated_at      TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_qr_codes_site ON site_qr_codes(site_id);
CREATE INDEX idx_qr_codes_token ON site_qr_codes(token);
CREATE INDEX idx_qr_codes_active ON site_qr_codes(is_active, expires_at);
```

### 3.5 workers（作業員マスター）★NEW★

```sql
CREATE TYPE worker_type AS ENUM ('company_employee', 'sole_proprietor');
CREATE TYPE blood_type AS ENUM ('A', 'B', 'O', 'AB', 'unknown');

CREATE TABLE workers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- 識別・照合用（2回目以降の再利用に使用）
    phone               VARCHAR(20) NOT NULL,          -- 主キー的な照合キー
    phone_normalized    VARCHAR(20) NOT NULL,          -- ハイフン除去・正規化済（検索用）
    -- 基本情報
    last_name           VARCHAR(50) NOT NULL,
    first_name          VARCHAR(50) NOT NULL,
    last_name_kana      VARCHAR(50),
    first_name_kana     VARCHAR(50),
    birth_date          DATE NOT NULL,
    gender              VARCHAR(10),
    blood_type          blood_type DEFAULT 'unknown',
    -- 連絡先
    postal_code         VARCHAR(8),
    address             TEXT,
    emergency_contact   VARCHAR(20),
    emergency_contact_name VARCHAR(50),
    emergency_contact_relation VARCHAR(30),
    -- 所属
    worker_type         worker_type NOT NULL,
    affiliation_company VARCHAR(200),                  -- 所属会社名
    job_title           VARCHAR(100),                  -- 職種・工種
    experience_years    INTEGER,
    -- 保険
    insurance_type      VARCHAR(100),
    insurance_number    VARCHAR(100),
    -- 顔写真
    face_photo_path     VARCHAR(500),
    face_photo_thumbnail_path VARCHAR(500),
    -- 個人情報同意
    consent_agreed_at   TIMESTAMPTZ,                  -- 同意日時
    consent_ip_hash     VARCHAR(64),                  -- 同意時IPのSHA256（原文は保持しない）
    -- 管理
    is_active           BOOLEAN NOT NULL DEFAULT true,
    first_registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_workers_phone ON workers(phone_normalized);
CREATE INDEX idx_workers_name ON workers(last_name, first_name);
CREATE INDEX idx_workers_company ON workers(affiliation_company);
```

### 3.6 worker_site_entries（現場入場管理）★NEW★

```sql
CREATE TYPE entry_status AS ENUM (
    'draft',        -- 一時保存（フォーム途中離脱）
    'pending',      -- 申請中（承認待ち）
    'approved',     -- 承認済
    'rejected',     -- 差戻し
    'withdrawn'     -- 取下げ
);

CREATE TABLE worker_site_entries (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_id           UUID NOT NULL REFERENCES workers(id),
    site_id             UUID NOT NULL REFERENCES sites(id),
    qr_code_id          UUID NOT NULL REFERENCES site_qr_codes(id),
    -- 申請ステータス
    status              entry_status NOT NULL DEFAULT 'pending',
    rejection_reason    TEXT,
    -- 入場情報（現場ごとに異なる可能性あり）
    planned_entry_date  DATE,                          -- 予定入場日
    planned_exit_date   DATE,                          -- 予定退場日
    actual_entry_date   DATE,                          -- 実入場日
    -- 健康確認（現場入場時点の確認）
    has_health_check    BOOLEAN DEFAULT false,
    health_check_date   DATE,
    -- 承認情報
    approved_by         UUID REFERENCES admin_users(id),
    approved_at         TIMESTAMPTZ,
    -- 提出情報（送信元追跡・個人情報保護）
    submit_ip_hash      VARCHAR(64),                  -- SHA256（原文保持しない）
    submit_user_agent   TEXT,
    submitted_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 同一作業員が同一現場に重複申請しないよう制約
CREATE UNIQUE INDEX idx_entries_worker_site
    ON worker_site_entries(worker_id, site_id)
    WHERE status NOT IN ('rejected', 'withdrawn');

CREATE INDEX idx_entries_site ON worker_site_entries(site_id);
CREATE INDEX idx_entries_worker ON worker_site_entries(worker_id);
CREATE INDEX idx_entries_status ON worker_site_entries(status);
CREATE INDEX idx_entries_submitted ON worker_site_entries(submitted_at DESC);
```

### 3.7 qualifications_master（資格マスター）★NEW★

```sql
CREATE TABLE qualifications_master (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code            VARCHAR(50) NOT NULL UNIQUE,      -- 資格コード（例: SCAFFOLD_SUPERVISOR）
    name            VARCHAR(200) NOT NULL,             -- 資格名称
    name_short      VARCHAR(50),                      -- 略称（フォーム表示用）
    category        VARCHAR(100),                     -- カテゴリ（足場・電気・クレーン等）
    has_expiry      BOOLEAN NOT NULL DEFAULT true,    -- 有効期限有無
    expiry_years    INTEGER,                          -- 標準有効年数（NULL=無期限）
    warn_days_before INTEGER DEFAULT 90,             -- 期限切れ警告日数（期限X日前）
    display_order   INTEGER DEFAULT 999,             -- フォーム表示順
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 初期データ例（マイグレーションで投入）
-- INSERT INTO qualifications_master (code, name, category, has_expiry, expiry_years) VALUES
--   ('HEALTH_SUPERVISOR',    '職長・安全衛生責任者', '安全', true, 5),
--   ('SCAFFOLD_SUPERVISOR',  '足場の組立て等作業主任者', '足場', false, NULL),
--   ('CRANE_UNDER_5T',       '小型移動式クレーン運転技能講習', 'クレーン', false, NULL),
--   ('HEALTH_CHECK',         '健康診断', '健康', true, 1),
--   ('SPECIAL_EDUCATION',    '特別教育修了', '安全', false, NULL);
```

### 3.8 worker_qualifications（作業員資格）★NEW★

```sql
CREATE TABLE worker_qualifications (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_id           UUID NOT NULL REFERENCES workers(id) ON DELETE CASCADE,
    qualification_id    UUID NOT NULL REFERENCES qualifications_master(id),
    acquired_date       DATE,                          -- 取得日
    expires_at          DATE,                          -- 有効期限（NULL=無期限）
    certificate_number  VARCHAR(100),                  -- 証明書番号
    issuing_authority   VARCHAR(200),                  -- 発行機関
    -- ファイル添付
    document_path       VARCHAR(500),                  -- MinIOパス
    thumbnail_path      VARCHAR(500),                  -- サムネイルパス
    original_filename   VARCHAR(500),
    mime_type           VARCHAR(100),
    file_size_bytes     INTEGER,
    -- 警告ステータス（バッチで更新）
    expiry_status       VARCHAR(20) DEFAULT 'valid',  -- valid / warning / expired
    -- 管理
    uploaded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_worker_quals_worker ON worker_qualifications(worker_id);
CREATE INDEX idx_worker_quals_expiry ON worker_qualifications(expires_at)
    WHERE expires_at IS NOT NULL;
CREATE INDEX idx_worker_quals_status ON worker_qualifications(expiry_status);
```

### 3.9 worker_documents（作業員書類）

```sql
CREATE TYPE document_category AS ENUM (
    'face_photo',         -- 顔写真
    'health_check',       -- 健康診断書
    'insurance_card',     -- 保険証
    'employment_contract',-- 雇用契約書
    'other'               -- その他
);

CREATE TABLE worker_documents (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_id           UUID NOT NULL REFERENCES workers(id) ON DELETE CASCADE,
    category            document_category NOT NULL,
    original_filename   VARCHAR(500) NOT NULL,
    storage_path        VARCHAR(1000) NOT NULL,        -- MinIO パス
    thumbnail_path      VARCHAR(500),                  -- サムネイル
    mime_type           VARCHAR(100) NOT NULL,
    file_size_bytes     INTEGER NOT NULL,
    file_size_compressed INTEGER,                      -- 圧縮後サイズ
    checksum            VARCHAR(64),                   -- SHA256
    uploaded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_worker_docs_worker ON worker_documents(worker_id);
CREATE INDEX idx_worker_docs_category ON worker_documents(worker_id, category);
```

### 3.10 approval_logs（承認ログ・監査証跡）

```sql
CREATE TYPE approval_action AS ENUM (
    'approved',
    'rejected',
    'pending_reset',      -- 承認取消し・差戻しリセット
    'document_viewed'     -- 書類閲覧ログ
);

CREATE TABLE approval_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_id        UUID NOT NULL REFERENCES worker_site_entries(id),
    admin_user_id   UUID NOT NULL REFERENCES admin_users(id),
    action          approval_action NOT NULL,
    comment         TEXT,
    -- 差戻し理由テンプレート
    rejection_template_id INTEGER,                    -- よく使う差戻し理由のID
    ip_address      INET,                             -- 操作元IP（管理者操作なのでIP記録可）
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_approval_logs_entry ON approval_logs(entry_id);
CREATE INDEX idx_approval_logs_admin ON approval_logs(admin_user_id);
CREATE INDEX idx_approval_logs_created ON approval_logs(created_at DESC);
```

### 3.11 rejection_templates（差戻し理由テンプレート）

```sql
CREATE TABLE rejection_templates (
    id          SERIAL PRIMARY KEY,
    company_id  UUID NOT NULL REFERENCES companies(id),
    label       VARCHAR(100) NOT NULL,                -- 「書類不鮮明」等
    body        TEXT NOT NULL,                        -- 本文
    display_order INTEGER DEFAULT 999,
    is_active   BOOLEAN NOT NULL DEFAULT true
);

-- 初期データ例
-- INSERT INTO rejection_templates (company_id, label, body) VALUES
--   (..., '書類不鮮明', '添付いただいた書類が不鮮明で確認できません。再撮影のうえ再申請してください。'),
--   (..., '資格期限切れ', '添付された資格証の有効期限が切れています。更新後に再申請してください。'),
--   (..., '情報不足', '必要な情報が不足しています。全項目を入力のうえ再申請してください。');
```

---

## 4. ER図（Mermaid）

```mermaid
erDiagram
    companies {
        uuid id PK
        varchar name
        varchar name_kana
        varchar logo_path
        boolean is_active
    }

    admin_users {
        uuid id PK
        uuid company_id FK
        varchar email
        varchar name
        admin_role role
        integer login_failure_count
        timestamptz locked_until
    }

    sites {
        uuid id PK
        uuid company_id FK
        uuid supervisor_id FK
        varchar name
        text address
        date start_date
        date end_date
        boolean require_health_check
        text custom_notice
    }

    site_qr_codes {
        uuid id PK
        uuid site_id FK
        uuid created_by FK
        varchar token
        varchar pin_code
        boolean pin_required
        varchar label
        boolean is_active
        timestamptz expires_at
        integer max_uses
        integer use_count
        time allowed_hours_start
        time allowed_hours_end
    }

    workers {
        uuid id PK
        varchar phone
        varchar phone_normalized
        varchar last_name
        varchar first_name
        date birth_date
        blood_type blood_type
        worker_type worker_type
        varchar affiliation_company
        varchar job_title
        integer experience_years
        varchar face_photo_path
        timestamptz consent_agreed_at
    }

    worker_site_entries {
        uuid id PK
        uuid worker_id FK
        uuid site_id FK
        uuid qr_code_id FK
        uuid approved_by FK
        entry_status status
        text rejection_reason
        date planned_entry_date
        boolean has_health_check
        timestamptz approved_at
        timestamptz submitted_at
    }

    qualifications_master {
        uuid id PK
        varchar code
        varchar name
        varchar category
        boolean has_expiry
        integer expiry_years
        integer warn_days_before
    }

    worker_qualifications {
        uuid id PK
        uuid worker_id FK
        uuid qualification_id FK
        date acquired_date
        date expires_at
        varchar certificate_number
        varchar document_path
        varchar thumbnail_path
        varchar expiry_status
    }

    worker_documents {
        uuid id PK
        uuid worker_id FK
        document_category category
        varchar storage_path
        varchar thumbnail_path
        varchar mime_type
        integer file_size_bytes
    }

    approval_logs {
        uuid id PK
        uuid entry_id FK
        uuid admin_user_id FK
        approval_action action
        text comment
        integer rejection_template_id
    }

    rejection_templates {
        serial id PK
        uuid company_id FK
        varchar label
        text body
    }

    companies ||--o{ admin_users : "has"
    companies ||--o{ sites : "manages"
    companies ||--o{ rejection_templates : "defines"
    admin_users ||--o{ sites : "supervises"
    sites ||--o{ site_qr_codes : "has"
    sites ||--o{ worker_site_entries : "accepts"
    site_qr_codes ||--o{ worker_site_entries : "used_for"
    workers ||--o{ worker_site_entries : "applies"
    workers ||--o{ worker_qualifications : "holds"
    workers ||--o{ worker_documents : "attaches"
    qualifications_master ||--o{ worker_qualifications : "defines"
    admin_users ||--o{ worker_site_entries : "approves"
    admin_users ||--o{ approval_logs : "records"
    worker_site_entries ||--o{ approval_logs : "has"
```

---

## 5. API一覧

### 公開API（認証不要 / レート制限あり）

#### QR・入場フロー

| メソッド | エンドポイント | 説明 | レート制限 |
|---------|--------------|------|-----------|
| POST | `/api/public/qr/verify` | QRトークン＋PIN検証、現場情報返却 | 30回/時/IP |
| POST | `/api/public/workers/lookup` | 電話番号で既存作業員を照合 | 10回/時/IP |
| POST | `/api/public/workers` | 新規作業員登録 | 5回/時/IP |
| PUT | `/api/public/workers/{id}/update` | 既存作業員情報更新（本人確認後） | 5回/時/IP |
| POST | `/api/public/entries` | 現場入場申請送信 | 5回/時/IP |
| POST | `/api/public/entries/{id}/documents` | 書類アップロード（分割可） | 20回/時/IP |
| GET | `/api/public/entries/{id}/status` | 申請ステータス確認 | 30回/時/IP |
| PUT | `/api/public/entries/draft` | 一時保存（途中離脱対応） | 20回/時/IP |

#### QR検証フロー詳細

```
POST /api/public/qr/verify
リクエスト:
  { "token": "xxx...", "pin": "1234" }  ← PIN不要の場合はpin省略可

レスポンス（成功）:
  {
    "session_token": "tmp_...",   ← 30分有効の一時トークン
    "site": {
      "name": "○○工事現場",
      "address": "東京都...",
      "custom_notice": "作業前に検温を実施してください"
    },
    "requires_fields": {          ← 現場ごとの必須設定
      "health_check": true,
      "insurance": true
    }
  }

エラー（PIN不一致）: 429 Too Many Requests（3回失敗で10分ブロック）
エラー（期限切れ）: 410 Gone
エラー（使用回数超過）: 403 Forbidden
```

```
POST /api/public/workers/lookup
リクエスト:
  { "phone": "090-1234-5678", "session_token": "tmp_..." }

レスポンス（既存作業員あり）:
  {
    "found": true,
    "worker_id": "uuid...",
    "preview": {            ← 本人確認用（フルの個人情報は返さない）
      "name": "田中 ○郎",   ← 名前は一部マスキング
      "affiliation": "○○建設",
      "last_entry_site": "△△工事"
    },
    "needs_update": false   ← 情報が古い場合true（1年以上更新なし等）
  }

レスポンス（新規）:
  { "found": false }
```

### 管理者API（JWT認証必須 / 社内IP限定）

#### 認証

| メソッド | エンドポイント | 説明 |
|---------|--------------|------|
| POST | `/api/admin/auth/login` | ログイン（失敗5回で15分ロック） |
| POST | `/api/admin/auth/logout` | ログアウト（Redisトークン失効） |
| POST | `/api/admin/auth/refresh` | アクセストークン更新 |
| GET | `/api/admin/auth/me` | 自分の情報 |

#### 現場管理

| メソッド | エンドポイント | 説明 | 権限 |
|---------|--------------|------|------|
| GET | `/api/admin/sites` | 現場一覧（ページネーション） | admin+ |
| POST | `/api/admin/sites` | 現場作成 | admin+ |
| GET | `/api/admin/sites/{id}` | 現場詳細（入場者数サマリー付き） | supervisor+ |
| PUT | `/api/admin/sites/{id}` | 現場更新 | admin+ |
| DELETE | `/api/admin/sites/{id}` | 現場削除（論理削除） | super_admin |

#### QRコード管理

| メソッド | エンドポイント | 説明 | 権限 |
|---------|--------------|------|------|
| GET | `/api/admin/sites/{id}/qrcodes` | QR一覧（使用回数付き） | supervisor+ |
| POST | `/api/admin/sites/{id}/qrcodes` | QR発行（PIN設定可） | admin+ |
| PUT | `/api/admin/qrcodes/{qid}/deactivate` | QR即時無効化 | admin+ |
| GET | `/api/admin/qrcodes/{qid}/image` | QR画像（PNG/PDF選択） | supervisor+ |
| GET | `/api/admin/qrcodes/{qid}/stats` | QR利用統計 | admin+ |

#### 作業員管理（管理側）

| メソッド | エンドポイント | 説明 | 権限 |
|---------|--------------|------|------|
| GET | `/api/admin/workers` | 作業員一覧・検索 | admin+ |
| GET | `/api/admin/workers/{id}` | 作業員詳細（全資格・書類付き） | supervisor+ |
| GET | `/api/admin/workers/{id}/qualifications` | **資格一覧（期限状況付き）** | supervisor+ |
| GET | `/api/admin/workers/{id}/entries` | 現場入場履歴 | supervisor+ |
| PUT | `/api/admin/workers/{id}` | 作業員情報修正（管理者権限） | admin+ |

#### 入場申請管理

| メソッド | エンドポイント | 説明 | 権限 |
|---------|--------------|------|------|
| GET | `/api/admin/entries` | 申請一覧（フィルタ・ページネーション） | supervisor+ |
| GET | `/api/admin/entries/pending` | **承認待ち一覧（監督モバイル向け高速取得）** | supervisor+ |
| GET | `/api/admin/entries/{id}` | 申請詳細（作業員情報・資格警告付き） | supervisor+ |
| PUT | `/api/admin/entries/{id}/approve` | **承認（ワンタップ）** | supervisor+ |
| PUT | `/api/admin/entries/{id}/reject` | 差戻し（テンプレート選択可） | supervisor+ |
| PUT | `/api/admin/entries/{id}/reset` | 差戻しをリセット→再申請促す | supervisor+ |

#### 書類・ファイル

| メソッド | エンドポイント | 説明 | 権限 |
|---------|--------------|------|------|
| GET | `/api/admin/workers/{id}/documents/{did}/url` | 署名付きURL取得（15分有効） | supervisor+ |
| GET | `/api/admin/workers/{id}/qualifications/{qid}/document/url` | 資格証署名付きURL | supervisor+ |

#### PDF生成

| メソッド | エンドポイント | 説明 | 権限 |
|---------|--------------|------|------|
| GET | `/api/admin/entries/{id}/pdf` | **個人別申請書PDF** | supervisor+ |
| GET | `/api/admin/sites/{id}/pdf/entry-list` | **新規入場者一覧PDF（A4）** | supervisor+ |
| GET | `/api/admin/sites/{id}/pdf/ledger` | **現場別台帳PDF** | admin+ |
| GET | `/api/admin/sites/{id}/pdf/company-list` | **協力会社別一覧PDF** | admin+ |
| GET | `/api/admin/sites/{id}/pdf/document-list` | **添付資料一覧PDF** | admin+ |
| GET | `/api/admin/qrcodes/{qid}/pdf` | QR掲示用PDFシート | admin+ |

#### エクスポート・レポート

| メソッド | エンドポイント | 説明 | 権限 |
|---------|--------------|------|------|
| GET | `/api/admin/reports/dashboard` | ダッシュボードデータ | supervisor+ |
| GET | `/api/admin/reports/expiring-qualifications` | **期限切れ間近資格一覧** | admin+ |
| GET | `/api/admin/sites/{id}/entries/export.csv` | CSV一括エクスポート | admin+ |

#### ユーザー・マスター管理

| メソッド | エンドポイント | 説明 | 権限 |
|---------|--------------|------|------|
| GET | `/api/admin/users` | ユーザー一覧 | admin+ |
| POST | `/api/admin/users` | ユーザー作成 | admin+ |
| PUT | `/api/admin/users/{id}` | ユーザー更新 | admin+ |
| DELETE | `/api/admin/users/{id}` | ユーザー削除 | super_admin |
| GET | `/api/admin/qualifications-master` | 資格マスター一覧 | admin+ |
| POST | `/api/admin/qualifications-master` | 資格マスター追加 | super_admin |
| GET | `/api/admin/rejection-templates` | 差戻し理由テンプレート | supervisor+ |
| POST | `/api/admin/rejection-templates` | テンプレート追加 | admin+ |

---

## 6. スマホUX方針

### 6.1 基本設計原則

```
「朝の7時、手袋をしながら、電波が弱い中での操作」を想定する

- タップターゲット: 最小 48×48px（推奨 56px以上）
- フォント: 16px以上（iOS自動ズーム防止）
- 縦スクロール: 1画面あたり最大3〜4項目
- ボタン: 画面下部固定（親指操作範囲）
- エラー表示: 赤背景ではなくインライン・大きく明確に
- ローディング: スケルトンUI（処理中が分かる）
```

### 6.2 フォームフロー（初回 vs 2回目以降）

```
【初回入場フロー（約5分）】

Step 0: QRランディング
  ┌─────────────────────────────┐
  │  📍 ○○工事現場               │
  │  新規入場の申請を行います      │
  │                              │
  │  ⚠ 作業前に検温を実施して     │
  │    ください                   │
  │                              │
  │  ┌──────────────────────┐   │
  │  │   申請を開始する →    │   │  ← 大きなCTAボタン（画面下部）
  │  └──────────────────────┘   │
  └─────────────────────────────┘

Step 1: 電話番号入力（既存照合）
  └→ [新規] → Step 2〜6（フル入力）

Step 2: 個人情報同意
  └→ 同意 → Step 3

Step 3: 基本情報（2画面に分割）
  3a: 氏名・フリガナ・生年月日
  3b: 住所・緊急連絡先

Step 4: 所属・職種（1画面）
  └→ 協力会社社員 / 一人親方 を最初に選択 → 分岐

Step 5: 資格選択（チェックリスト方式）
  └→ 資格マスターから該当するものをタップ選択

Step 6: 書類アップロード
  └→ カメラ直接起動 / ライブラリ選択

Step 7: 確認・送信
  └→ 送信完了 → 受付番号 + QRコード（スクショ促す）

---

【2回目以降の入場フロー（約30秒）】

Step 0: QRランディング
Step 1: 電話番号入力
  └→ [既存発見] →

  ┌─────────────────────────────┐
  │  👤 田中 ○郎さん ですか？    │  ← 名前は一部マスキング
  │  ○○建設 / 鉄筋工            │
  │                              │
  │  ┌──────────────┐           │
  │  │  はい、本人です  │  ←大ボタン│
  │  └──────────────┘           │
  │  別の方 / 情報を修正          │  ← テキストリンク
  └─────────────────────────────┘

  └→ [本人確認] →

  ┌─────────────────────────────┐
  │  ○○工事現場 の入場申請        │
  │                              │
  │  入場予定日: [今日 ▼]        │
  │  健康診断: [済み ▼]          │
  │                              │
  │  ┌──────────────────────┐   │
  │  │   申請する →         │   │
  │  └──────────────────────┘   │
  └─────────────────────────────┘
```

### 6.3 一時保存・オフライン対応

```
【一時保存戦略】

localStorage / IndexedDB に保存するもの:
  - 入力途中のフォームデータ（フィールド単位で随時保存）
  - 撮影した書類画像（Base64、最大5MB）
  - QRセッショントークン（30分TTL）

Service Worker キャッシュ:
  - フォームページHTML/CSS/JS（オフライン表示可能）
  - 資格マスターリスト（日次更新）

オフライン時の動作:
  1. フォーム入力はローカル保存のみ
  2. 電波回復を検知したら自動送信を試みる
  3. 「送信待ち」バナーを表示
  4. 手動送信ボタンも提供

PWA manifest.json:
  "display": "standalone",
  "start_url": "/entry",
  "background_sync": true  ← バックグラウンド送信
```

### 6.4 画面設計（スマホ最適化）

```
【入力フォームの共通ルール】

1. 1画面に最大3項目
2. キーボードに合わせたinputtype
   - 電話番号 → type="tel"
   - 生年月日 → type="date" または ドラム式ピッカー
   - 郵便番号 → type="tel" + 住所自動入力
3. 次へボタンは常に画面下部固定
4. 戻るボタンは左上（ブラウザ標準に従う）
5. 「必須」は赤い「*」ではなく「（必須）」テキスト
6. エラーはフィールド直下に赤テキストで表示

【資格選択UI】
  チェックリスト方式:
  ┌───────────────────────────────┐
  │ ✅ 職長・安全衛生責任者         │
  │ ☐  足場の組立て等作業主任者    │
  │ ☐  小型移動式クレーン         │
  │ ✅ 健康診断（受診済）          │
  └───────────────────────────────┘
  → 選択した資格だけ書類アップロードが表示される

【書類アップロードUI】
  ┌───────────────────────────────┐
  │  📄 職長・安全衛生責任者 修了証 │
  │                               │
  │  ┌──────────┐  ┌──────────┐  │
  │  │  📷 撮影  │  │ 📁 選択  │  │  ← 大きなボタン
  │  └──────────┘  └──────────┘  │
  │                               │
  │  [サムネイル表示エリア]         │
  │  ✅ アップロード完了            │
  └───────────────────────────────┘
```

---

## 7. セキュリティ方針

### 7.1 QRコードセキュリティ（強化版）

```
【多層防御の考え方】

Layer 1: トークン（推測不可能性）
  - 32バイトのCSPRNG生成 → Base64URL = 43文字
  - 毎回新規発行・使い捨て可能

Layer 2: PIN（流出時の第二防壁）
  - 4〜6桁数字（現場に別途掲示 or 口頭連絡）
  - bcrypt(cost=10)でハッシュ化保存
  - 3回失敗で10分IP+tokenブロック（Redis）

Layer 3: 有効期限
  - デフォルト: 現場工期終了日の翌日
  - 即時無効化: 管理者操作1クリックで即時（Redisに無効化フラグ）

Layer 4: 使用回数制限（オプション）
  - max_uses 設定時: use_count >= max_uses → 403
  - カウントはDBとRedisの両方で管理

Layer 5: 受付時間帯制限（オプション）
  - allowed_hours_start / end 設定時
  - 例: 06:00〜09:00のみ受付（朝礼時間限定）
  - 時間外アクセスは「現在受付時間外です」表示

【QR流出時のリカバリ手順】
  1. 管理者が /admin/qrcodes/{id}/deactivate → 即時無効化
  2. 新規QRを再発行（token + PIN変更）
  3. 新QRを現場に掲示・配布
  所要時間: 約2分
```

### 7.2 個人情報保護

| 情報 | 保存方法 | 理由 |
|------|---------|------|
| 電話番号 | 平文（検索キー） | 照合に必要・アクセス制御で保護 |
| 住所 | 平文（DBアクセス制御） | 管理者のみアクセス可 |
| 顔写真 | MinIO非公開バケット・署名URL | 直接URLアクセス不可 |
| 送信元IP | SHA256ハッシュのみ保存 | 個人特定に使えない形で痕跡のみ残す |
| 同意IP | SHA256ハッシュのみ保存 | 同上 |
| アクセスログ | 名前・電話番号をマスキング | ログ流出時のリスク低減 |

### 7.3 ファイルアップロードセキュリティ

```
【アップロードパイプライン】

1. クライアント → multipart/form-data で送信
2. FastAPI:
   a. ファイルサイズ確認（上限: 20MB/ファイル、HEIC考慮）
   b. マジックバイト検証（Content-Typeを信用しない）
   c. 許可MIMEタイプ確認:
      image/jpeg, image/png, image/webp, image/heic,
      image/heif, application/pdf
   d. Pillowで実際に開けるか確認（Zipbomb対策）
3. 画像処理:
   a. HEIC → JPEG 変換（pillow-heif）
   b. 長辺2048pxにリサイズ（元の縦横比維持）
   c. JPEG品質80で再圧縮
   d. サムネイル生成（300×400px、品質60）
   e. Exif情報を全削除（位置情報保護）
4. UUID ファイル名でMinIOに保存
5. 元ファイル名はDBに記録のみ（パスには使わない）
```

### 7.4 通信・認証セキュリティ

| 対策 | 設定値 |
|------|--------|
| HTTPS | TLS 1.2以上、TLS 1.0/1.1無効 |
| HSTS | max-age=31536000; includeSubDomains |
| CSP | default-src 'self'; img-src 'self' blob: data: |
| X-Frame-Options | DENY |
| JWT署名 | RS256（非対称鍵） |
| アクセストークン有効期限 | 60分 |
| リフレッシュトークン有効期限 | 7日（Redis管理・失効可能） |
| パスワードハッシュ | bcrypt cost=12 |
| ログイン失敗ロック | 5回失敗→15分ロック（IPとアカウント両方） |
| 管理画面IP制限 | Nginx allow/deny（社内CIDR） |

---

## 8. PDF帳票方針

### 8.1 帳票一覧と取得元テーブル

#### ① 個人別申請書（A4縦・1人1枚）

```
目的: 個人の入場申請内容を1枚で確認

取得テーブル:
  - worker_site_entries（ステータス・入場日・承認日時）
  - workers（氏名・生年月日・住所・電話・所属・職種）
  - worker_qualifications + qualifications_master（資格一覧・期限）
  - worker_documents（書類添付有無チェックリスト）
  - approval_logs（承認者・承認日時）
  - sites（現場名・住所）
  - companies（会社名・ロゴ）

レイアウト:
  ┌────────────────────────────────────────┐
  │ [会社ロゴ]    新規入場申請書            │
  │ 現場名: ○○工事現場          受付No: xxxx│
  ├────────────────────────────────────────┤
  │ 氏名: 田中 太郎  フリガナ: タナカ タロウ  │
  │ 生年月日: 1980/01/01  血液型: A型        │
  │ 住所: 東京都...                          │
  │ 電話: 090-xxxx-xxxx                      │
  │ 緊急連絡先: 090-xxxx-xxxx (配偶者)       │
  ├────────────────────────────────────────┤
  │ 所属: ○○建設株式会社  職種: 鉄筋工      │
  │ 経験年数: 10年  保険: 建設国保 xxx-xxx   │
  ├────────────────────────────────────────┤
  │ 保有資格:                                │
  │ ✅ 職長・安全衛生責任者（2024/03/15）    │
  │ ✅ 健康診断（2025/11/01）               │
  ├────────────────────────────────────────┤
  │ 承認: 山田 監督  2026/05/19 08:32        │
  │ [QRコード: 申請確認URL]                  │
  └────────────────────────────────────────┘
```

#### ② 新規入場者一覧（A4横・複数人一覧）

```
目的: 現場の入場者を一覧で把握（朝礼資料）

取得テーブル:
  - worker_site_entries（承認済のレコード・入場日でフィルタ）
  - workers（氏名・所属・職種）
  - worker_qualifications（資格期限警告フラグ）

カラム構成:
  No | 氏名 | フリガナ | 所属会社 | 職種 | 入場日 | 資格警告 | 備考
```

#### ③ 現場別台帳（A4縦・折りたたみ可能な詳細版）

```
目的: 現場の全入場者を期間指定で一覧管理

取得テーブル:
  - sites（現場情報・工期）
  - worker_site_entries（全ステータス・入場日）
  - workers（個人情報）
  - worker_qualifications（資格）

カバーページ + 一覧ページの構成
期間フィルタ: 承認日・入場日で絞り込み
```

#### ④ 協力会社別一覧（A4縦）

```
目的: 協力会社ごとに入場者を整理（請負管理）

取得テーブル:
  - workers（affiliation_company でグループ化）
  - worker_site_entries（現場・ステータス）

構成: 会社名をヘッダーに、その下に作業員一覧
```

#### ⑤ 添付資料一覧（A4縦・チェックリスト形式）

```
目的: 書類の提出状況を一覧確認

取得テーブル:
  - worker_qualifications（添付状況・期限）
  - worker_documents（書類種別・アップロード日）
  - workers（氏名）

構成: 作業員 × 書類種別のマトリクス表
      未提出・期限切れを赤でハイライト
```

### 8.2 PDF生成実装方針

```python
# WeasyPrint + Jinja2テンプレート方式

# 帳票ごとにHTMLテンプレートを作成
templates/
  pdf/
    individual_application.html   # 個人別申請書
    entry_list.html               # 新規入場者一覧
    site_ledger.html              # 現場別台帳
    company_list.html             # 協力会社別一覧
    document_checklist.html       # 添付資料一覧
    _base.html                    # 共通ヘッダー・フッター

# A4設定（CSSで制御）
@page {
  size: A4;
  margin: 15mm 12mm;
}
@page:first { ... }  # 表紙ページ

# 印刷ブレーク制御
.page-break { page-break-before: always; }
```

---

## 9. MVP定義（現場投入最小機能）

### MVP必須機能（フェーズ0 = 最初の3週間）

現場で「使える」状態を最短で実現する。書類・PDF・メール通知は後回し。

| # | 機能 | 理由 |
|---|------|------|
| 1 | 現場作成 + QR発行（PIN設定可） | これがないと何も始まらない |
| 2 | QR読込 → 電話番号照合 → 作業員登録 | コアフロー |
| 3 | 基本情報フォーム（氏名・生年月日・電話・所属・職種） | 最小入力項目 |
| 4 | 申請送信 → 受付番号発行 | 完了確認 |
| 5 | 2回目以降の短縮フロー（電話番号→確認→申請） | 再利用性の核心 |
| 6 | 管理者ログイン（IP制限あり） | セキュリティ必須 |
| 7 | 承認待ち一覧（スマホ対応シンプルUI） | 監督の主業務 |
| 8 | ワンタップ承認 / 差戻し | 監督の主業務 |
| 9 | HTTPS + Nginx IP制限 | セキュリティ必須 |
| 10 | PWAマニフェスト（ホーム画面追加可） | スマホUX |

**MVP除外機能（後回し）:**

| 機能 | 後回しにする理由 |
|------|----------------|
| 書類アップロード | 口頭・紙で代替可能。複雑性が高い |
| PDF出力 | Excelで代替可能。開発コストが高い |
| 資格期限警告 | マスターデータ構築が先決 |
| メール通知 | 運用ルールが先決 |
| HEIC変換 | 書類アップロードが前提 |
| CSVエクスポート | 少人数なら画面確認で対応可 |
| ダッシュボードグラフ | 集計のみで十分 |

### フェーズ別ロードマップ

```
Phase 0: MVP（3週間）
  ├─ Week 1: 環境構築 + DB + 認証 + QR発行
  ├─ Week 2: 公開フォーム（初回・2回目フロー）
  └─ Week 3: 管理画面（承認UI）+ 本番投入

Phase 1: 書類対応（+3週間）
  ├─ 書類アップロード + HEIC変換 + 圧縮
  ├─ サムネイル表示（監督UI）
  └─ 個人別申請書PDF出力

Phase 2: 資格管理（+3週間）
  ├─ 資格マスター + worker_qualifications
  ├─ 資格選択フォーム + 資格証アップロード
  ├─ 期限警告バッジ（承認画面・作業員詳細）
  └─ 期限切れ一覧レポート

Phase 3: 帳票・エクスポート（+2週間）
  ├─ 新規入場者一覧PDF
  ├─ 現場別台帳PDF
  ├─ 協力会社別一覧PDF
  └─ CSVエクスポート

Phase 4: 高度化（+2週間）
  ├─ メール通知（申請受付・承認完了）
  ├─ QR使用統計・ログ
  ├─ データ自動削除スケジューラ
  └─ 管理者向けダッシュボード強化
```

---

## 10. 今後の拡張計画

### 短期（リリース後3ヶ月以内）

| 機能 | 概要 |
|------|------|
| 資格期限一括警告メール | 期限30日前に自動でメール送信（作業員・監督へ） |
| 入場QRバッジ印刷 | 承認後に作業員IDカード（顔写真+QR）をPDF出力 |
| 差戻し連絡 | 差戻し時にSMS or URLリンクで作業員に通知 |
| 検索強化 | 氏名・電話・所属会社の横断検索 |

### 中期（6ヶ月以内）

| 機能 | 概要 |
|------|------|
| 入退場ログ | 承認済み作業員がQRをタッチして入退場記録 |
| 日次入場者リスト | 毎朝6時に当日入場予定者リストをメール配信 |
| 協力会社セルフ管理 | 協力会社が自社作業員を事前登録するポータル |
| 多言語対応 | 外国籍作業員向けに日本語/英語/中国語/ベトナム語切替 |
| 統計ダッシュボード | 現場別・協力会社別の入場者推移グラフ |

### 長期（1年以内）

| 機能 | 概要 |
|------|------|
| グリーンサイト連携 | 建設業のグリーンサイトAPIと作業員データ連携 |
| 顔認証入場 | 承認済み作業員の顔写真と照合して自動入場 |
| 外部認証機能 | Google Workspace / Microsoft Entra SSO対応 |
| マルチテナント | SaaS化（複数建設会社が同一システムを利用） |

### DB拡張時の考慮点

```
現在のスキーマで将来対応可能な設計:

✅ 作業員マスター（workers）は現場に依存しないため、
   協力会社ポータルや他システム連携の起点になれる

✅ qualifications_master はコードで管理しているため、
   グリーンサイトの資格コードとのマッピングが容易

✅ worker_site_entries は入退場ログの親テーブルになれる
   （entry_logs テーブルを追加するだけ）

✅ site_qr_codes の allowed_hours は
   入退場時間帯制限へ自然に拡張可能

⚠ 将来注意点:
   - workers テーブルが肥大化した場合はパーティショニングを検討
   - 書類ファイルの増加に対してMinioのバケットライフサイクル設定必須
   - 個人情報保持期間（3年）経過後の自動削除バッチ必須
```

---

## 付録A: 環境変数一覧

```env
# DB
DATABASE_URL=postgresql://app:password@postgres:5432/entry_db

# Redis
REDIS_URL=redis://:password@redis:6379

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=entry-documents
MINIO_USE_SSL=false

# JWT
JWT_PRIVATE_KEY_PATH=/run/secrets/jwt_private.pem
JWT_PUBLIC_KEY_PATH=/run/secrets/jwt_public.pem
JWT_ALGORITHM=RS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# セキュリティ
ALLOWED_ADMIN_CIDRS=192.168.0.0/16,10.0.0.0/8
QR_TOKEN_BYTES=32               # 生成するランダムバイト数
ENCRYPTION_KEY=...              # AES-256キー（送信元IPハッシュ用）

# ファイル処理
MAX_UPLOAD_SIZE_MB=20
IMAGE_MAX_LONG_SIDE=2048
IMAGE_JPEG_QUALITY=80
THUMBNAIL_WIDTH=300
THUMBNAIL_HEIGHT=400
THUMBNAIL_QUALITY=60

# 運用
DATA_RETENTION_YEARS=3          # 個人情報保持年数
EXPIRY_WARNING_DAYS=90          # 資格期限警告日数
```

## 付録B: Docker Compose（最終版）

```yaml
version: '3.9'

services:
  nginx:
    build: ./nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./certs:/etc/ssl/certs:ro
    depends_on: [frontend, backend]
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      target: production
    environment:
      NEXT_PUBLIC_API_URL: /api
    depends_on: [backend]
    restart: unless-stopped

  backend:
    build: ./backend
    env_file: .env
    secrets: [jwt_private, jwt_public]
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_started }
      minio: { condition: service_started }
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    env_file: .env
    environment:
      POSTGRES_DB: entry_db
      POSTGRES_USER: app
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d entry_db"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD} --save 60 1
    volumes:
      - redis_data:/data
    restart: unless-stopped

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ACCESS_KEY}
      MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY}
    volumes:
      - minio_data:/data
    restart: unless-stopped

  # バックグラウンドタスク（資格期限警告・自動削除）
  worker:
    build: ./backend
    command: python -m app.tasks.scheduler
    env_file: .env
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_started }
    restart: unless-stopped

secrets:
  jwt_private:
    file: ./secrets/jwt_private.pem
  jwt_public:
    file: ./secrets/jwt_public.pem

volumes:
  postgres_data:
  redis_data:
  minio_data:
```

## 付録C: 資格マスター初期データ（抜粋）

```sql
INSERT INTO qualifications_master
  (code, name, name_short, category, has_expiry, expiry_years, warn_days_before, display_order)
VALUES
  ('FOREMAN',              '職長・安全衛生責任者教育',   '職長',     '安全管理',  true,  5,    90, 10),
  ('HEALTH_CHECK',         '健康診断',                   '健診',     '健康',      true,  1,    60, 20),
  ('SCAFFOLD_CHIEF',       '足場の組立て等作業主任者',   '足場主任', '足場',      false, NULL, 90, 30),
  ('CRANE_UNDER_5T',       '小型移動式クレーン技能講習', '小クレ',   'クレーン',  false, NULL, 90, 40),
  ('SLING',                '玉掛け技能講習',             '玉掛け',   '吊り作業',  false, NULL, 90, 50),
  ('FORK_LIFT',            'フォークリフト技能講習',     'フォーク', '車両系',    false, NULL, 90, 60),
  ('FIRE_PREVENTION',      '防火管理者',                 '防火管理', '防災',      true,  5,    90, 70),
  ('CONFINED_SPACE',       '酸素欠乏危険作業主任者',     '酸欠',     '特殊作業',  false, NULL, 90, 80),
  ('ELECTRICITY_LOW',      '低圧電気取扱業務特別教育',   '低圧電気', '電気',      false, NULL, 90, 90),
  ('CONSTRUCTION_MACHINE', '車両系建設機械技能講習',     '建機',     '車両系',    false, NULL, 90, 100);
```
