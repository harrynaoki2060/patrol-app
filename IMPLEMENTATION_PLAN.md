# 新規入場管理システム 実装計画書（仕様固定版）

> 作成日: 2026-05-19  
> ベース設計: SYSTEM_DESIGN_V2.md  
> 目的: MVP実装前の仕様凍結・後戻りリスクの排除

---

## 目次

1. [MVP範囲の完全固定](#1-mvp範囲の完全固定)
2. [画面一覧固定](#2-画面一覧固定)
3. [API仕様固定](#3-api仕様固定)
4. [DBスキーマ固定](#4-dbスキーマ固定)
5. [Docker構成](#5-docker構成)
6. [ディレクトリ構成](#6-ディレクトリ構成)
7. [開発工程表 Day1〜Day14](#7-開発工程表-day1day14)
8. [Claude Code実装戦略](#8-claude-code実装戦略)

---

## 1. MVP範囲の完全固定

### 判断基準

```
「明日から現場で使えるか」= YES → MVP IN
「なくても紙・口頭で代替できる」= YES → MVP OUT
```

### 機能分類表

| 機能 | MVP | 判定理由 |
|------|:---:|---------|
| **現場作成** | ✅ IN | QR発行の前提。これがないと何も始まらない |
| **QR発行（トークン＋PIN）** | ✅ IN | 入力フローの入口。PIN は流出対策として初日から必須 |
| **QR有効期限設定** | ✅ IN | 工期終了後に無効化される必要がある |
| **QR即時無効化** | ✅ IN | 紛失リスク対応。管理操作の最重要機能 |
| **スマホ入力フォーム（基本項目）** | ✅ IN | コアバリュー |
| **電話番号による作業員照合** | ✅ IN | 2回目以降の短縮フローがないと現場で使われない |
| **作業員再利用（2回目フロー）** | ✅ IN | 朝礼時間中に処理するため必須 |
| **申請送信・受付番号発行** | ✅ IN | 送信完了の確認手段 |
| **管理者ログイン（IP制限）** | ✅ IN | セキュリティ必須。開発初日から入れる |
| **承認待ち一覧（モバイル対応）** | ✅ IN | 監督の主業務 |
| **ワンタップ承認** | ✅ IN | 監督の主業務 |
| **差戻し（理由入力）** | ✅ IN | 承認の裏面として必須 |
| **現場別の申請一覧** | ✅ IN | 監督が状況把握するために必須 |
| **申請詳細閲覧** | ✅ IN | 承認判断に必要 |
| **HTTPS + Nginx IP制限** | ✅ IN | セキュリティ必須、妥協不可 |
| **PWAマニフェスト（ホーム画面追加のみ）** | ✅ IN | UX向上、実装コスト低 |
| **添付ファイルアップロード** | ❌ OUT | 紙で代替可。HEIC変換等の複雑性が高い |
| **HEIC変換・画像圧縮** | ❌ OUT | 添付ファイル機能が前提 |
| **サムネイル生成** | ❌ OUT | 添付ファイル機能が前提 |
| **PDF出力** | ❌ OUT | Excelで代替可 |
| **メール通知** | ❌ OUT | 口頭・チャットで代替可 |
| **オフライン一時保存（Service Worker）** | ❌ OUT | localStorage一時保存で十分 |
| **PWAバックグラウンド同期** | ❌ OUT | オフライン機能が前提 |
| **資格期限管理** | ❌ OUT | データが溜まってから意味が出る |
| **資格マスター管理** | ❌ OUT | 資格期限管理が前提 |
| **CSVエクスポート** | ❌ OUT | 少人数なら画面で対応可 |
| **ダッシュボードグラフ** | ❌ OUT | 件数サマリーのみで十分 |
| **差戻し理由テンプレート** | ❌ OUT | 自由入力で代替可 |
| **QR使用回数制限** | ❌ OUT | 時間帯制限と有効期限で十分 |
| **QR受付時間帯制限** | ❌ OUT | 運用ルールで代替可 |
| **顔写真** | ❌ OUT | 添付ファイル機能が前提 |

### MVP境界線の定義

```
MVP IN:
  companies / admin_users / sites / site_qr_codes
  workers / worker_site_entries / approval_logs
  公開フォーム7画面 + 管理画面8画面
  公開API5本 + 管理API17本

MVP OUT（テーブル不要）:
  qualifications_master / worker_qualifications
  worker_documents / rejection_templates

MVP OUT（後から追加しても DB 変更不要なもの）:
  → 上記テーブルはMVPのスキーマに含めない
  → worker_site_entries に has_health_check カラムは残す（フォームで使う）
```

---

## 2. 画面一覧固定

### 2.1 外部ユーザー画面（公開・スマートフォン向け）

#### P01 QRランディング画面

| 項目 | 内容 |
|------|------|
| URL | `/entry/[token]` |
| 利用権限 | 誰でもアクセス可（QRトークン保有者） |
| モバイル対応 | ◎ 必須（スマホ専用デザイン） |
| 目的 | 現場情報の表示・申請開始の起点 |

**表示内容:**
```
- 現場名（大きく表示）
- 現場住所
- 現場カスタム注意事項（sites.custom_notice）
- [申請を開始する] ボタン（フルワイド、60px高さ）
- 「このページはブックマーク保存をおすすめします」案内
```

**バリデーション:**
```
- トークンが存在しない → 404ページ
- トークンが無効化済み → 「このQRコードは無効です」エラー画面
- トークンの期限切れ → 「QRコードの有効期限が切れています」エラー画面
```

---

#### P02 PIN入力画面

| 項目 | 内容 |
|------|------|
| URL | `/entry/[token]/pin` |
| 利用権限 | P01通過後 |
| モバイル対応 | ◎ 必須 |
| 表示条件 | `site_qr_codes.pin_required = true` の場合のみ表示 |

**入力項目:**

| フィールド | type | バリデーション |
|-----------|------|--------------|
| PIN | `tel` 数字4〜6桁 | 必須・数字のみ・3回失敗でブロック |

**バリデーション:**
```
- PIN不一致（1〜2回目）→ 「PINが違います。あと{N}回入力できます」
- PIN不一致（3回目）→ 「しばらく経ってから再試行してください」（10分ブロック）
- 正解 → セッショントークン発行（Redis保存・30分TTL）→ P03へ
```

---

#### P03 電話番号入力画面

| 項目 | 内容 |
|------|------|
| URL | `/entry/[token]/lookup` |
| 利用権限 | セッショントークン必須（Redisで検証） |
| モバイル対応 | ◎ 必須 |
| 目的 | 既存作業員の照合 |

**入力項目:**

| フィールド | type | バリデーション |
|-----------|------|--------------|
| 電話番号 | `tel` | 必須・10〜11桁・ハイフン有無どちらも可 |

**バリデーション:**
```
- 空欄 → 「電話番号を入力してください」
- 桁数不正 → 「正しい電話番号を入力してください」
- API照合成功（既存作業員あり）→ P04へ
- API照合成功（新規）→ P05へ（同意ページ経由）
```

---

#### P04 作業員再利用確認画面

| 項目 | 内容 |
|------|------|
| URL | `/entry/[token]/confirm` |
| 利用権限 | セッショントークン必須 |
| モバイル対応 | ◎ 必須 |
| 目的 | 本人確認・2回目以降の超短縮フロー |

**表示内容:**
```
- 「○○さん ですか？」（姓のみ表示）
- 所属会社名
- 職種
- 最終入場現場名

[はい、本人です] ボタン（フルワイド・大）
[別の方 / 情報を修正する] リンク（小・テキスト）
```

**「はい、本人です」選択後の追加入力（最小限）:**

| フィールド | type | バリデーション |
|-----------|------|--------------|
| 入場予定日 | `date` | 必須・今日以降 |
| 健康診断済み | チェックボックス | 任意 |

**バリデーション:**
```
- 同一作業員が同一現場に承認済みエントリーを持つ場合
  → 「この現場への申請は既に承認されています」と表示してブロック
- 同一作業員が同一現場にpending状態のエントリーを持つ場合
  → 「申請中です。承認をお待ちください」と表示してブロック
```

---

#### P05 新規作業員入力フォーム

| 項目 | 内容 |
|------|------|
| URL | `/entry/[token]/form` |
| 利用権限 | セッショントークン必須 |
| モバイル対応 | ◎ 必須（多段階・1画面3項目以内） |
| 目的 | 初回入場時の情報登録 |

**フォームステップ構成:**

```
Step 1 of 4: 基本情報
Step 2 of 4: 連絡先・住所
Step 3 of 4: 所属・職種
Step 4 of 4: 入場情報
→ 確認画面 → 送信
```

**Step 1: 基本情報**

| フィールド | type | 必須 | バリデーション |
|-----------|------|:----:|--------------|
| 姓 | `text` | ✅ | 50文字以内 |
| 名 | `text` | ✅ | 50文字以内 |
| 姓（フリガナ） | `text` | - | カタカナのみ・50文字以内 |
| 名（フリガナ） | `text` | - | カタカナのみ・50文字以内 |
| 生年月日 | `date` | ✅ | 1920-01-01〜今日-15年（15歳未満NG） |
| 性別 | select | - | 男性／女性／回答しない |
| 血液型 | select | - | A/B/O/AB/不明 |

**Step 2: 連絡先・住所**

| フィールド | type | 必須 | バリデーション |
|-----------|------|:----:|--------------|
| 電話番号 | `tel` | ✅ | 照合済みなので表示のみ（変更不可） |
| 緊急連絡先 | `tel` | - | 10〜11桁 |
| 緊急連絡先のお名前 | `text` | - | 50文字以内 |
| 緊急連絡先の続柄 | `text` | - | 30文字以内 |
| 郵便番号 | `tel` | - | 7桁→住所自動入力 |
| 住所 | `text` | - | 200文字以内 |

**Step 3: 所属・職種**

| フィールド | type | 必須 | バリデーション |
|-----------|------|:----:|--------------|
| 区分 | radio | ✅ | 協力会社社員 / 一人親方 |
| 所属会社名 | `text` | △協力社員のみ必須 | 200文字以内 |
| 職種・工種 | `text` | ✅ | 100文字以内（例: 鉄筋工） |
| 経験年数 | `tel` | - | 0〜60の整数 |
| 保険の種類 | `text` | - | 100文字以内（例: 建設国保） |
| 保険番号 | `text` | - | 100文字以内 |

**Step 4: 入場情報**

| フィールド | type | 必須 | バリデーション |
|-----------|------|:----:|--------------|
| 入場予定日 | `date` | ✅ | 今日以降 |
| 健康診断済み | チェックボックス | △現場設定による | - |
| 健康診断日 | `date` | △健診済みチェック時 | 過去日付のみ |

**個人情報同意（Step 1の前に1画面）:**
```
- 個人情報取り扱い同意文（全文表示）
- [同意して次へ] ボタン
- 同意なしは先に進めない
```

**一時保存仕様:**
```
- 各Stepの「次へ」押下時に localStorage に保存
  キー: entry_draft_{token}
  値: { step, formData, timestamp }
- 30分以内の再アクセス時は「続きから」の選択肢を表示
- 送信完了後に localStorage から削除
```

---

#### P06 確認・送信画面

| 項目 | 内容 |
|------|------|
| URL | `/entry/[token]/review` |
| モバイル対応 | ◎ 必須 |

**表示内容:**
```
- 入力内容の全項目表示（読み取り専用）
- [修正する] ボタン（各セクションごと）
- [申請する] ボタン（フルワイド・大・送信中はdisabled）
```

---

#### P07 送信完了画面

| 項目 | 内容 |
|------|------|
| URL | `/entry/[token]/complete` |
| モバイル対応 | ◎ 必須 |

**表示内容:**
```
- ✅ 申請が完了しました
- 受付番号: XXXXXXXX（8桁英数字）
- 現場名
- 「この画面をスクリーンショットして保存してください」
- 「承認完了後に入場できます」
- [申請状況を確認する] リンク（→ /entry/status/{entry_id}）
```

---

#### P08 申請状況確認画面

| 項目 | 内容 |
|------|------|
| URL | `/entry/status/[entry_id]` |
| モバイル対応 | ◎ 必須 |

**表示内容:**
```
- 受付番号
- 現場名
- 申請日時
- 現在のステータス（承認待ち / 承認済み / 差戻し）
- 差戻し時: 差戻し理由の表示
```

---

### 2.2 管理画面（社内限定・PC/スマホ両対応）

#### A01 ログイン画面

| 項目 | 内容 |
|------|------|
| URL | `/admin/login` |
| 利用権限 | 社内IPのみアクセス可（Nginx制限） |
| モバイル対応 | ○ 対応 |

**入力項目:**

| フィールド | type | バリデーション |
|-----------|------|--------------|
| メールアドレス | `email` | 必須・形式チェック |
| パスワード | `password` | 必須・1文字以上 |

**バリデーション:**
```
- 未入力 → フィールド下にエラー表示
- 認証失敗（1〜4回目）→ 「メールアドレスまたはパスワードが違います」
- 認証失敗（5回目）→ 「アカウントがロックされました。15分後に再試行してください」
- ロック中はパスワードを正しく入力しても拒否
- 認証成功 → JWT発行 → /admin へリダイレクト
```

---

#### A02 ダッシュボード画面

| 項目 | 内容 |
|------|------|
| URL | `/admin` |
| 利用権限 | supervisor以上 |
| モバイル対応 | ○ 対応 |

**表示内容:**
```
- 承認待ち件数バッジ（大きく・目立つ色）
- 今日の入場予定者数
- 担当現場一覧（supervisor: 自分の現場のみ、admin+: 全現場）
  各現場カード:
    - 現場名
    - 承認待ち件数
    - 承認済み件数
    - [詳細へ] ボタン
```

---

#### A03 現場一覧画面

| 項目 | 内容 |
|------|------|
| URL | `/admin/sites` |
| 利用権限 | admin以上（supervisorはA02から自分の現場のみアクセス） |
| モバイル対応 | ○ 対応 |

**表示内容:**
```
- 現場カード一覧（工期順ソート）
- 各カード: 現場名・住所・工期・入場者数・承認待ち件数
- [新規現場作成] ボタン（admin+のみ表示）
- 検索ボックス（現場名で絞り込み）
```

---

#### A04 現場作成・編集画面

| 項目 | 内容 |
|------|------|
| URL | `/admin/sites/new` / `/admin/sites/[id]/edit` |
| 利用権限 | admin以上 |
| モバイル対応 | △ 最低限 |

**入力項目:**

| フィールド | type | 必須 | バリデーション |
|-----------|------|:----:|--------------|
| 現場名 | `text` | ✅ | 200文字以内 |
| 現場住所 | `text` | - | - |
| 工期開始日 | `date` | - | - |
| 工期終了日 | `date` | - | 開始日以降 |
| 担当監督 | select | - | admin_usersから選択 |
| 健康診断を必須とする | チェックボックス | - | デフォルトON |
| 保険情報を必須とする | チェックボックス | - | デフォルトON |
| 現場への注意事項 | `textarea` | - | QRランディングに表示される |

---

#### A05 QRコード管理画面

| 項目 | 内容 |
|------|------|
| URL | `/admin/sites/[id]/qrcodes` |
| 利用権限 | supervisor以上（閲覧）/ admin以上（発行・無効化） |
| モバイル対応 | ○ 対応 |

**表示内容:**
```
- QR発行済みリスト
  各行: ラベル・有効期限・使用状況（有効/無効/期限切れ）・[QR画像] ボタン・[無効化] ボタン
- [新規QR発行] ボタン（admin+のみ）
```

**QR発行モーダル入力項目:**

| フィールド | type | 必須 | バリデーション |
|-----------|------|:----:|--------------|
| ラベル | `text` | - | 100文字以内（例: 北ゲート用） |
| PIN設定 | チェックボックス | - | ONにするとPIN入力欄が出現 |
| PINコード | `tel` | △PIN設定ON時 | 4〜6桁数字 |
| 有効期限 | `date` | - | 今日以降（空欄=工期終了日） |

---

#### A06 承認待ち一覧画面（監督メイン画面）

| 項目 | 内容 |
|------|------|
| URL | `/admin/entries` |
| 利用権限 | supervisor以上 |
| モバイル対応 | ◎ 必須（監督はスマホで使う） |

**表示内容:**
```
- タブ: [承認待ち (N)] [承認済み] [差戻し]
- 各申請カード:
  - 氏名・所属会社・職種
  - 申請日時（〇分前 形式）
  - 入場予定日
  - [詳細・承認へ] ボタン（フルワイド）
- 現場フィルター（admin+は全現場、supervisorは担当現場のみ）
- プルダウンで更新
```

---

#### A07 申請詳細画面

| 項目 | 内容 |
|------|------|
| URL | `/admin/entries/[id]` |
| 利用権限 | supervisor以上 |
| モバイル対応 | ◎ 必須 |

**表示内容:**
```
上部: ステータスバッジ + 申請日時
─────────────────────
作業員情報:
  氏名・フリガナ・生年月日・性別・血液型
  電話番号・緊急連絡先
  住所
─────────────────────
所属情報:
  区分（協力社員/一人親方）
  所属会社・職種・経験年数
  保険種別・保険番号
─────────────────────
入場情報:
  入場予定日・健康診断状況
─────────────────────
承認操作エリア（pending時のみ表示）:
  [✅ 承認する] ボタン（緑・フルワイド・大）
  [❌ 差戻す]   ボタン（赤・フルワイド）
  ↓ 差戻しボタン押下時:
  差戻し理由テキストエリア（必須）
  [差戻しを確定する] ボタン
─────────────────────
承認ログ（過去の操作履歴）
```

---

#### A08 申請者一覧画面（現場詳細）

| 項目 | 内容 |
|------|------|
| URL | `/admin/sites/[id]` |
| 利用権限 | supervisor以上 |
| モバイル対応 | ○ 対応 |

**表示内容:**
```
- 現場基本情報（名称・住所・工期・担当監督）
- QRコード管理へのリンク
- 入場者一覧（ステータス別タブ）
- 各行: 氏名・所属・職種・申請日・ステータス・[詳細] リンク
```

---

## 3. API仕様固定

### 共通仕様

```
Base URL: https://{host}/api
Content-Type: application/json
文字コード: UTF-8

エラーレスポンス共通フォーマット:
{
  "error": {
    "code": "VALIDATION_ERROR",   // エラー種別
    "message": "入力内容を確認してください",
    "details": [                   // バリデーションエラー時のみ
      { "field": "phone", "message": "電話番号の形式が正しくありません" }
    ]
  }
}

エラーコード一覧:
  VALIDATION_ERROR     → 400
  UNAUTHORIZED         → 401
  FORBIDDEN            → 403
  NOT_FOUND            → 404
  CONFLICT             → 409（重複申請等）
  RATE_LIMITED         → 429
  INTERNAL_ERROR       → 500
```

---

### 公開API（認証不要）

#### API-P01: QRトークン検証

```
POST /api/public/qr/verify

レート制限: 30回/時/IP

Request:
{
  "token": "string",        // URLパスから取得（必須）
  "pin": "string"           // PINが必要な場合のみ（4〜6桁数字）
}

Response 200:
{
  "session_token": "tmp_xxxxxxxx",   // Redis保存・30分TTL
  "site": {
    "id": "uuid",
    "name": "○○工事現場",
    "address": "東京都渋谷区...",
    "custom_notice": "作業前に検温を実施してください",
    "require_health_check": true,
    "require_insurance": false
  },
  "pin_required": false,    // PINが必要かどうか（true=PIN入力画面へ）
  "pin_verified": true      // PIN検証済みかどうか
}

Errors:
  400 VALIDATION_ERROR  → tokenが空
  404 NOT_FOUND         → トークンが存在しない
  403 FORBIDDEN         → QRが無効化済み / 期限切れ
  400 PIN_REQUIRED      → PINが必要だが未送信（pin_required: true を含む）
  401 PIN_INVALID       → PIN不一致
                           { attempts_remaining: 2 } を含む
  429 PIN_BLOCKED       → PIN試行回数超過（10分ブロック）
                           { retry_after_seconds: 600 } を含む
```

---

#### API-P02: 作業員照合

```
POST /api/public/workers/lookup

レート制限: 10回/時/IP

Request:
{
  "phone": "09012345678",         // ハイフンあり/なし両可（必須）
  "session_token": "tmp_xxxxxxxx" // 必須（QR検証済み証明）
}

Response 200（既存作業員あり）:
{
  "found": true,
  "worker_id": "uuid",
  "preview": {
    "last_name": "田中",           // 姓のみ（名はマスク）
    "affiliation_company": "○○建設",
    "job_title": "鉄筋工"
  },
  "already_applied": false,        // この現場に既に申請済みか
  "apply_status": null             // 申請済みの場合: "pending" / "approved"
}

Response 200（新規作業員）:
{
  "found": false
}

Errors:
  400 VALIDATION_ERROR  → 電話番号の形式不正
  401 UNAUTHORIZED      → session_token が無効/期限切れ
```

---

#### API-P03: 作業員新規登録

```
POST /api/public/workers

レート制限: 5回/時/IP

Request:
{
  "session_token": "tmp_xxxxxxxx",
  "consent_agreed": true,        // 個人情報同意（必須・falseは拒否）

  // 基本情報
  "last_name": "田中",           // 必須・50文字以内
  "first_name": "太郎",          // 必須・50文字以内
  "last_name_kana": "タナカ",    // 任意
  "first_name_kana": "タロウ",   // 任意
  "birth_date": "1980-01-15",    // 必須・YYYY-MM-DD
  "gender": "male",              // 任意: male/female/other/prefer_not_to_say
  "blood_type": "A",             // 任意: A/B/O/AB/unknown

  // 連絡先（phoneはsession経由で取得済み・不要）
  "emergency_contact": "09098765432",          // 任意
  "emergency_contact_name": "田中 花子",       // 任意
  "emergency_contact_relation": "配偶者",      // 任意
  "postal_code": "1500001",      // 任意
  "address": "東京都渋谷区神宮前...",           // 任意

  // 所属
  "worker_type": "company_employee",           // 必須: company_employee/sole_proprietor
  "affiliation_company": "○○建設株式会社",    // worker_type=company_employee時必須
  "job_title": "鉄筋工",                       // 必須
  "experience_years": 10,                      // 任意・0以上の整数
  "insurance_type": "建設国保",               // 任意
  "insurance_number": "12345",                 // 任意

  // 入場情報
  "planned_entry_date": "2026-05-20",          // 必須
  "has_health_check": true,                    // 任意（現場設定で必須になる場合あり）
  "health_check_date": "2026-03-01"            // has_health_check=trueの場合
}

Response 201:
{
  "worker_id": "uuid",
  "entry_id": "uuid",
  "receipt_number": "A1B2C3D4",   // 8桁英数字
  "status": "pending"
}

Errors:
  400 VALIDATION_ERROR  → 各フィールドバリデーション失敗
  400 CONSENT_REQUIRED  → consent_agreed が false
  401 UNAUTHORIZED      → session_token 無効
  409 CONFLICT          → この現場に既にpending/approved申請がある
```

---

#### API-P04: 既存作業員で入場申請

```
POST /api/public/entries

レート制限: 5回/時/IP

Request:
{
  "session_token": "tmp_xxxxxxxx",
  "worker_id": "uuid",
  "planned_entry_date": "2026-05-20",  // 必須
  "has_health_check": true,            // 任意
  "health_check_date": "2026-03-01",   // 任意

  // 変更があれば更新（任意項目）
  "update_worker": {
    "job_title": "型枠大工",           // 職種変更時
    "affiliation_company": "△△工業"   // 所属変更時
  }
}

Response 201:
{
  "entry_id": "uuid",
  "receipt_number": "X9Y8Z7W6",
  "status": "pending"
}

Errors:
  400 VALIDATION_ERROR  → バリデーション失敗
  401 UNAUTHORIZED      → session_token 無効/worker_idとの不一致
  409 CONFLICT          → この現場に既にpending/approved申請がある
```

---

#### API-P05: 申請状況確認

```
GET /api/public/entries/{entry_id}/status

レート制限: 30回/時/IP

Response 200:
{
  "receipt_number": "A1B2C3D4",
  "site_name": "○○工事現場",
  "status": "pending",             // pending/approved/rejected/withdrawn
  "submitted_at": "2026-05-19T07:30:00+09:00",
  "approved_at": null,
  "rejection_reason": null
}

Errors:
  404 NOT_FOUND  → entry_id が存在しない
```

---

### 管理者API（JWT認証必須 + 社内IP必須）

#### 認証ヘッダー
```
Authorization: Bearer {access_token}
```

---

#### API-A01: ログイン

```
POST /api/admin/auth/login

Request:
{
  "email": "admin@example.com",
  "password": "password"
}

Response 200:
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "uuid",
    "name": "山田 太郎",
    "email": "admin@example.com",
    "role": "supervisor"
  }
}

Errors:
  401 UNAUTHORIZED  → 認証失敗（残り試行回数は返さない）
  423 LOCKED        → アカウントロック中 { retry_after_seconds: N }
```

---

#### API-A02: ログアウト

```
POST /api/admin/auth/logout
認証: 必須

Response 204: (body なし)
→ Redisのrefresh_tokenを失効させる
```

---

#### API-A03: トークンリフレッシュ

```
POST /api/admin/auth/refresh

Request:
{
  "refresh_token": "eyJ..."
}

Response 200:
{
  "access_token": "eyJ...",
  "expires_in": 3600
}

Errors:
  401 UNAUTHORIZED  → refresh_tokenが無効/期限切れ
```

---

#### API-A04: 自分の情報取得

```
GET /api/admin/auth/me
認証: 必須

Response 200:
{
  "id": "uuid",
  "name": "山田 太郎",
  "email": "admin@example.com",
  "role": "supervisor",
  "company": {
    "id": "uuid",
    "name": "○○建設株式会社"
  }
}
```

---

#### API-A05: 現場一覧

```
GET /api/admin/sites?page=1&per_page=20&search=
認証: 必須 / admin以上

Response 200:
{
  "total": 15,
  "page": 1,
  "per_page": 20,
  "items": [
    {
      "id": "uuid",
      "name": "○○工事現場",
      "address": "東京都...",
      "start_date": "2026-01-01",
      "end_date": "2026-12-31",
      "supervisor": { "id": "uuid", "name": "山田 太郎" },
      "stats": {
        "pending": 3,
        "approved": 12,
        "rejected": 1
      },
      "is_active": true
    }
  ]
}
```

---

#### API-A06: 現場作成

```
POST /api/admin/sites
認証: 必須 / admin以上

Request:
{
  "name": "○○工事現場",
  "address": "東京都渋谷区...",
  "start_date": "2026-01-01",
  "end_date": "2026-12-31",
  "supervisor_id": "uuid",
  "require_health_check": true,
  "require_insurance": true,
  "custom_notice": "作業前に検温を実施してください"
}

Response 201:
{
  "id": "uuid",
  "name": "○○工事現場",
  ...（全フィールド）
}

Errors:
  400 VALIDATION_ERROR → name が空等
  404 NOT_FOUND        → supervisor_id が存在しない
```

---

#### API-A07: 現場詳細

```
GET /api/admin/sites/{site_id}
認証: 必須 / supervisor以上（自分の担当現場のみ）

Response 200:
{
  "id": "uuid",
  "name": "○○工事現場",
  "address": "東京都...",
  "start_date": "2026-01-01",
  "end_date": "2026-12-31",
  "supervisor": { "id": "uuid", "name": "山田 太郎" },
  "require_health_check": true,
  "require_insurance": true,
  "custom_notice": "...",
  "stats": { "pending": 3, "approved": 12, "rejected": 1 },
  "recent_entries": [...]   // 直近5件
}

Errors:
  403 FORBIDDEN  → supervisorが担当外現場にアクセス
  404 NOT_FOUND  → 存在しないsite_id
```

---

#### API-A08: 現場更新

```
PUT /api/admin/sites/{site_id}
認証: 必須 / admin以上

Request: API-A06と同じ形式（部分更新可）

Response 200: 更新後の現場オブジェクト
```

---

#### API-A09: QRコード一覧

```
GET /api/admin/sites/{site_id}/qrcodes
認証: 必須 / supervisor以上

Response 200:
{
  "items": [
    {
      "id": "uuid",
      "label": "北ゲート用",
      "token": "xxxx...",           // 管理画面表示用（短縮）
      "pin_required": true,
      "is_active": true,
      "expires_at": "2026-12-31T23:59:59+09:00",
      "use_count": 15,
      "created_at": "2026-05-19T09:00:00+09:00",
      "created_by": { "name": "山田 管理者" },
      "qr_url": "https://entry.example.com/entry/xxxx..."
    }
  ]
}
```

---

#### API-A10: QRコード発行

```
POST /api/admin/sites/{site_id}/qrcodes
認証: 必須 / admin以上

Request:
{
  "label": "北ゲート用",
  "pin_required": true,
  "pin_code": "1234",        // pin_required=trueの場合必須・4〜6桁数字
  "expires_at": "2026-12-31" // 任意（省略時=sites.end_date。end_dateもなければNULL）
}

Response 201:
{
  "id": "uuid",
  "token": "xxxx...",
  "qr_image_url": "/api/admin/qrcodes/{id}/image",
  "entry_url": "https://entry.example.com/entry/xxxx..."
}
```

---

#### API-A11: QR無効化

```
PUT /api/admin/qrcodes/{qr_id}/deactivate
認証: 必須 / admin以上

Response 200:
{
  "id": "uuid",
  "is_active": false,
  "deactivated_at": "2026-05-19T10:00:00+09:00"
}
```

---

#### API-A12: QR画像取得

```
GET /api/admin/qrcodes/{qr_id}/image?format=png
認証: 必須 / supervisor以上

format: png（デフォルト）/ svg

Response: image/png バイナリ または image/svg+xml
```

---

#### API-A13: 承認待ち一覧（モバイル監督向け）

```
GET /api/admin/entries?status=pending&site_id={uuid}&page=1&per_page=20
認証: 必須 / supervisor以上

Query Parameters:
  status: pending / approved / rejected（デフォルト: pending）
  site_id: 絞り込み用（省略時=担当全現場）
  page, per_page: ページネーション

Response 200:
{
  "total": 5,
  "page": 1,
  "per_page": 20,
  "items": [
    {
      "id": "uuid",
      "receipt_number": "A1B2C3D4",
      "worker": {
        "last_name": "田中",
        "first_name": "太郎",
        "affiliation_company": "○○建設",
        "job_title": "鉄筋工"
      },
      "site": { "id": "uuid", "name": "○○工事現場" },
      "status": "pending",
      "planned_entry_date": "2026-05-20",
      "submitted_at": "2026-05-19T07:30:00+09:00",
      "submitted_at_relative": "2時間前"    // 表示用
    }
  ]
}
```

---

#### API-A14: 申請詳細

```
GET /api/admin/entries/{entry_id}
認証: 必須 / supervisor以上

Response 200:
{
  "id": "uuid",
  "receipt_number": "A1B2C3D4",
  "status": "pending",
  "site": { "id": "uuid", "name": "○○工事現場" },
  "worker": {
    "id": "uuid",
    "last_name": "田中",
    "first_name": "太郎",
    "last_name_kana": "タナカ",
    "first_name_kana": "タロウ",
    "birth_date": "1980-01-15",
    "gender": "male",
    "blood_type": "A",
    "phone": "090-1234-5678",
    "emergency_contact": "090-9876-5432",
    "emergency_contact_name": "田中 花子",
    "emergency_contact_relation": "配偶者",
    "postal_code": "1500001",
    "address": "東京都渋谷区...",
    "worker_type": "company_employee",
    "affiliation_company": "○○建設株式会社",
    "job_title": "鉄筋工",
    "experience_years": 10,
    "insurance_type": "建設国保",
    "insurance_number": "12345"
  },
  "planned_entry_date": "2026-05-20",
  "has_health_check": true,
  "health_check_date": "2026-03-01",
  "submitted_at": "2026-05-19T07:30:00+09:00",
  "approval_logs": [
    {
      "action": "approved",
      "admin_name": "山田 太郎",
      "comment": "",
      "created_at": "2026-05-19T08:00:00+09:00"
    }
  ]
}

Errors:
  403 FORBIDDEN  → supervisorが担当外現場の申請にアクセス
  404 NOT_FOUND  → entry_id が存在しない
```

---

#### API-A15: 承認

```
PUT /api/admin/entries/{entry_id}/approve
認証: 必須 / supervisor以上

Request:
{
  "comment": "確認しました"    // 任意
}

Response 200:
{
  "id": "uuid",
  "status": "approved",
  "approved_by": { "id": "uuid", "name": "山田 太郎" },
  "approved_at": "2026-05-19T08:00:00+09:00"
}

Errors:
  409 CONFLICT   → すでに承認済み/差戻し済みの申請
  404 NOT_FOUND  → entry_id が存在しない
```

---

#### API-A16: 差戻し

```
PUT /api/admin/entries/{entry_id}/reject
認証: 必須 / supervisor以上

Request:
{
  "rejection_reason": "添付書類が不鮮明です。再申請をお願いします。"  // 必須・1文字以上
}

Response 200:
{
  "id": "uuid",
  "status": "rejected",
  "rejection_reason": "添付書類が不鮮明です。再申請をお願いします。"
}

Errors:
  400 VALIDATION_ERROR → rejection_reason が空
  409 CONFLICT         → すでに承認済みの申請
```

---

#### API-A17: ダッシュボードデータ

```
GET /api/admin/reports/dashboard
認証: 必須 / supervisor以上

Response 200:
{
  "today_entries": 5,           // 今日入場予定の承認済み件数
  "pending_count": 3,           // 承認待ち総数（担当現場）
  "approved_this_week": 20,     // 今週承認済み件数
  "sites": [
    {
      "id": "uuid",
      "name": "○○工事現場",
      "pending": 2,
      "approved": 15
    }
  ]
}
```

---

## 4. DBスキーマ固定

### SQLite vs PostgreSQL 判定

| 機能 | PostgreSQL | SQLite | MVP判定 |
|------|:---------:|:------:|--------|
| `gen_random_uuid()` | ✅ | ❌ | PG必須（アプリ側でUUID生成で回避可） |
| `TIMESTAMPTZ` | ✅ | △TEXT | PG必須（タイムゾーン管理が必要） |
| `ENUM型` | ✅ | ❌ | VARCHAR+CHECK制約で代替可 |
| `INET型` | ✅ | ❌ | MVPでは送信元IPを保存しないので不要 |
| `UNIQUE INDEX` | ✅ | ✅ | OK |
| 部分INDEX (`WHERE`) | ✅ | ✅ | OK |
| `CHECK制約` | ✅ | ✅ | OK |

**結論: PostgreSQL必須。ただし以下の対策でSQLAlchemy経由の抽象化を維持する**

```python
# UUIDはアプリ側で生成（DB依存しない）
import uuid
id = str(uuid.uuid4())

# ENUMはPython Enumクラス + VARCHAR(50) で管理
# TIMESTAMPTZはSQLAlchemy DateTime(timezone=True) で管理
# INETは使わない（IPはハッシュ化してVARCHAR保存）
```

---

### テーブル定義（MVP用・8テーブル）

#### TABLE: companies

```sql
CREATE TABLE companies (
    id              VARCHAR(36)  PRIMARY KEY,  -- UUID文字列
    name            VARCHAR(200) NOT NULL,
    name_kana       VARCHAR(200),
    postal_code     VARCHAR(8),
    address         TEXT,
    phone           VARCHAR(20),
    representative  VARCHAR(100),
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

| カラム | 型 | NULL | DEFAULT | INDEX | 制約 |
|-------|---|:----:|---------|-------|------|
| id | VARCHAR(36) | ❌ | - | PK | UUID |
| name | VARCHAR(200) | ❌ | - | - | - |
| name_kana | VARCHAR(200) | ✅ | - | - | - |
| postal_code | VARCHAR(8) | ✅ | - | - | - |
| address | TEXT | ✅ | - | - | - |
| phone | VARCHAR(20) | ✅ | - | - | - |
| representative | VARCHAR(100) | ✅ | - | - | - |
| is_active | BOOLEAN | ❌ | TRUE | - | - |
| created_at | TIMESTAMPTZ | ❌ | NOW() | - | - |
| updated_at | TIMESTAMPTZ | ❌ | NOW() | - | - |

---

#### TABLE: admin_users

```sql
CREATE TABLE admin_users (
    id                  VARCHAR(36)  PRIMARY KEY,
    company_id          VARCHAR(36)  NOT NULL REFERENCES companies(id),
    email               VARCHAR(254) NOT NULL,
    password_hash       VARCHAR(255) NOT NULL,
    name                VARCHAR(100) NOT NULL,
    role                VARCHAR(20)  NOT NULL DEFAULT 'supervisor'
                        CHECK (role IN ('super_admin', 'admin', 'supervisor')),
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    login_failure_count INTEGER      NOT NULL DEFAULT 0,
    locked_until        TIMESTAMPTZ,
    last_login_at       TIMESTAMPTZ,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_admin_users_email ON admin_users(email);
CREATE INDEX idx_admin_users_company ON admin_users(company_id);
```

| カラム | 型 | NULL | DEFAULT | INDEX |
|-------|---|:----:|---------|-------|
| id | VARCHAR(36) | ❌ | - | PK |
| company_id | VARCHAR(36) | ❌ | - | IDX, FK→companies |
| email | VARCHAR(254) | ❌ | - | UNIQUE |
| password_hash | VARCHAR(255) | ❌ | - | - |
| name | VARCHAR(100) | ❌ | - | - |
| role | VARCHAR(20) | ❌ | 'supervisor' | - |
| is_active | BOOLEAN | ❌ | TRUE | - |
| login_failure_count | INTEGER | ❌ | 0 | - |
| locked_until | TIMESTAMPTZ | ✅ | NULL | - |
| last_login_at | TIMESTAMPTZ | ✅ | NULL | - |
| created_at | TIMESTAMPTZ | ❌ | NOW() | - |
| updated_at | TIMESTAMPTZ | ❌ | NOW() | - |

---

#### TABLE: sites

```sql
CREATE TABLE sites (
    id                  VARCHAR(36)  PRIMARY KEY,
    company_id          VARCHAR(36)  NOT NULL REFERENCES companies(id),
    name                VARCHAR(200) NOT NULL,
    address             TEXT,
    start_date          DATE,
    end_date            DATE,
    supervisor_id       VARCHAR(36)  REFERENCES admin_users(id) ON DELETE SET NULL,
    require_health_check BOOLEAN     NOT NULL DEFAULT TRUE,
    require_insurance   BOOLEAN      NOT NULL DEFAULT TRUE,
    custom_notice       TEXT,
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
);

CREATE INDEX idx_sites_company    ON sites(company_id);
CREATE INDEX idx_sites_supervisor ON sites(supervisor_id);
CREATE INDEX idx_sites_active     ON sites(is_active, end_date);
```

---

#### TABLE: site_qr_codes

```sql
CREATE TABLE site_qr_codes (
    id              VARCHAR(36)  PRIMARY KEY,
    site_id         VARCHAR(36)  NOT NULL REFERENCES sites(id),
    token           VARCHAR(64)  NOT NULL,   -- secrets.token_urlsafe(32)
    pin_hash        VARCHAR(255),            -- bcrypt(pin) / NULL=PINなし
    pin_required    BOOLEAN      NOT NULL DEFAULT FALSE,
    label           VARCHAR(100),
    qr_image_path   VARCHAR(500),
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    expires_at      TIMESTAMPTZ,
    created_by      VARCHAR(36)  REFERENCES admin_users(id) ON DELETE SET NULL,
    deactivated_by  VARCHAR(36)  REFERENCES admin_users(id) ON DELETE SET NULL,
    deactivated_at  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_qr_codes_token ON site_qr_codes(token);
CREATE INDEX idx_qr_codes_site   ON site_qr_codes(site_id);
CREATE INDEX idx_qr_codes_active ON site_qr_codes(is_active, expires_at);
```

---

#### TABLE: workers

```sql
CREATE TABLE workers (
    id                          VARCHAR(36)  PRIMARY KEY,
    phone                       VARCHAR(20)  NOT NULL,
    phone_normalized            VARCHAR(20)  NOT NULL,   -- ハイフン除去・先頭0固定
    last_name                   VARCHAR(50)  NOT NULL,
    first_name                  VARCHAR(50)  NOT NULL,
    last_name_kana              VARCHAR(50),
    first_name_kana             VARCHAR(50),
    birth_date                  DATE         NOT NULL,
    gender                      VARCHAR(20)
                                CHECK (gender IN ('male','female','other','prefer_not_to_say')),
    blood_type                  VARCHAR(10)
                                CHECK (blood_type IN ('A','B','O','AB','unknown')),
    emergency_contact           VARCHAR(20),
    emergency_contact_name      VARCHAR(50),
    emergency_contact_relation  VARCHAR(30),
    postal_code                 VARCHAR(8),
    address                     TEXT,
    worker_type                 VARCHAR(20)  NOT NULL
                                CHECK (worker_type IN ('company_employee','sole_proprietor')),
    affiliation_company         VARCHAR(200),
    job_title                   VARCHAR(100) NOT NULL,
    experience_years            INTEGER      CHECK (experience_years >= 0),
    insurance_type              VARCHAR(100),
    insurance_number            VARCHAR(100),
    consent_agreed_at           TIMESTAMPTZ,
    is_active                   BOOLEAN      NOT NULL DEFAULT TRUE,
    first_registered_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_updated_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_workers_phone ON workers(phone_normalized);
CREATE INDEX idx_workers_name    ON workers(last_name, first_name);
CREATE INDEX idx_workers_company ON workers(affiliation_company);
```

---

#### TABLE: worker_site_entries

```sql
CREATE TABLE worker_site_entries (
    id                  VARCHAR(36)  PRIMARY KEY,
    worker_id           VARCHAR(36)  NOT NULL REFERENCES workers(id),
    site_id             VARCHAR(36)  NOT NULL REFERENCES sites(id),
    qr_code_id          VARCHAR(36)  NOT NULL REFERENCES site_qr_codes(id),
    receipt_number      VARCHAR(8)   NOT NULL,  -- 8桁英数字 UPPER
    status              VARCHAR(20)  NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('draft','pending','approved','rejected','withdrawn')),
    rejection_reason    TEXT,
    planned_entry_date  DATE,
    has_health_check    BOOLEAN      DEFAULT FALSE,
    health_check_date   DATE,
    approved_by         VARCHAR(36)  REFERENCES admin_users(id) ON DELETE SET NULL,
    approved_at         TIMESTAMPTZ,
    submit_ip_hash      VARCHAR(64),    -- SHA256(IP)
    submitted_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 同一作業員が同一現場に有効申請を重複作成できない
CREATE UNIQUE INDEX uq_entries_worker_site_active
    ON worker_site_entries(worker_id, site_id)
    WHERE status IN ('draft', 'pending', 'approved');

CREATE UNIQUE INDEX uq_entries_receipt ON worker_site_entries(receipt_number);
CREATE INDEX idx_entries_site      ON worker_site_entries(site_id);
CREATE INDEX idx_entries_worker    ON worker_site_entries(worker_id);
CREATE INDEX idx_entries_status    ON worker_site_entries(status);
CREATE INDEX idx_entries_submitted ON worker_site_entries(submitted_at DESC);
```

---

#### TABLE: approval_logs

```sql
CREATE TABLE approval_logs (
    id              VARCHAR(36)  PRIMARY KEY,
    entry_id        VARCHAR(36)  NOT NULL REFERENCES worker_site_entries(id),
    admin_user_id   VARCHAR(36)  NOT NULL REFERENCES admin_users(id),
    action          VARCHAR(20)  NOT NULL
                    CHECK (action IN ('approved','rejected','pending_reset')),
    comment         TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_approval_logs_entry   ON approval_logs(entry_id);
CREATE INDEX idx_approval_logs_created ON approval_logs(created_at DESC);
```

---

#### シードデータ（初期投入必須）

```sql
-- 初期会社
INSERT INTO companies (id, name, is_active)
VALUES ('00000000-0000-0000-0000-000000000001', '○○建設株式会社', TRUE);

-- 初期super_adminユーザー（パスワード: 起動時に環境変数 INITIAL_ADMIN_PASSWORD から設定）
INSERT INTO admin_users (id, company_id, email, password_hash, name, role)
VALUES (
    '00000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000001',
    'admin@example.com',
    '{BCRYPT_HASH}',   -- デプロイスクリプトで差し替え
    'システム管理者',
    'super_admin'
);
```

---

## 5. Docker構成

### ファイル構成

```
patrol-entry/
├── docker-compose.yml          ← 開発・本番共用ベース
├── docker-compose.override.yml ← 開発時の上書き設定
├── docker-compose.prod.yml     ← 本番専用設定
├── .env.example
├── .env                        ← .gitignore に追加必須
├── secrets/
│   ├── jwt_private.pem         ← .gitignore に追加必須
│   └── jwt_public.pem
├── nginx/
│   ├── Dockerfile
│   ├── nginx.conf
│   └── conf.d/
│       ├── entry.conf          ← 公開フォーム
│       └── admin.conf          ← 管理画面（IP制限）
├── frontend/
│   └── Dockerfile
├── backend/
│   └── Dockerfile
└── postgres/
    └── init.sql                ← テーブル作成SQL
```

### docker-compose.yml（本番ベース）

```yaml
version: '3.9'

networks:
  frontend_net:   # nginx ↔ frontend
  backend_net:    # frontend ↔ backend
  data_net:       # backend ↔ postgres/redis/minio

services:
  nginx:
    build:
      context: ./nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./certs:/etc/nginx/certs:ro
    networks:
      - frontend_net
      - backend_net
    depends_on:
      - frontend
      - backend
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    environment:
      NODE_ENV: production
      NEXT_PUBLIC_API_BASE_URL: ""   # 同一オリジン /api でアクセス
    networks:
      - frontend_net
      - backend_net
    depends_on:
      - backend
    restart: unless-stopped

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    environment:
      DATABASE_URL: postgresql+asyncpg://app:${DB_PASSWORD}@postgres:5432/entry_db
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
      MINIO_ENDPOINT: minio:9000
      MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY}
      MINIO_SECRET_KEY: ${MINIO_SECRET_KEY}
      MINIO_BUCKET: entry-documents
      MINIO_USE_SSL: "false"
      JWT_ALGORITHM: RS256
      ACCESS_TOKEN_EXPIRE_MINUTES: "60"
      REFRESH_TOKEN_EXPIRE_DAYS: "7"
      QR_SESSION_EXPIRE_MINUTES: "30"
      ALLOWED_ADMIN_CIDRS: ${ALLOWED_ADMIN_CIDRS}
      INITIAL_ADMIN_EMAIL: ${INITIAL_ADMIN_EMAIL}
      INITIAL_ADMIN_PASSWORD: ${INITIAL_ADMIN_PASSWORD}
    secrets:
      - jwt_private
      - jwt_public
    networks:
      - backend_net
      - data_net
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
      POSTGRES_DB: entry_db
      POSTGRES_USER: app
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./postgres/init.sql:/docker-entrypoint-initdb.d/01_init.sql:ro
    networks:
      - data_net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d entry_db"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD}
      --save 60 1
      --loglevel warning
    volumes:
      - redis_data:/data
    networks:
      - data_net
    restart: unless-stopped

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ACCESS_KEY}
      MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY}
    volumes:
      - minio_data:/data
    networks:
      - data_net
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  minio_data:

secrets:
  jwt_private:
    file: ./secrets/jwt_private.pem
  jwt_public:
    file: ./secrets/jwt_public.pem
```

### docker-compose.override.yml（開発専用・自動適用）

```yaml
version: '3.9'

services:
  backend:
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      - ./backend:/app   # ホットリロード
    ports:
      - "8000:8000"      # デバッグ用直接アクセス

  frontend:
    command: npm run dev
    volumes:
      - ./frontend:/app
      - /app/node_modules
      - /app/.next
    ports:
      - "3000:3000"

  postgres:
    ports:
      - "5432:5432"      # DB直接接続（開発時）

  minio:
    ports:
      - "9001:9001"      # MinIOコンソール（開発時）
```

### .env.example

```env
# PostgreSQL
DB_PASSWORD=changeme_in_production

# Redis
REDIS_PASSWORD=changeme_in_production

# MinIO
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=changeme_in_production

# 管理画面IP制限（カンマ区切りCIDR）
ALLOWED_ADMIN_CIDRS=192.168.0.0/16,10.0.0.0/8

# 初期管理者
INITIAL_ADMIN_EMAIL=admin@example.com
INITIAL_ADMIN_PASSWORD=changeme_in_production

# フロントエンドURL（QR URLに使用）
PUBLIC_ENTRY_BASE_URL=https://entry.example.com
ADMIN_BASE_URL=https://admin.example.com
```

### Nginx設定（conf.d/admin.conf）

```nginx
limit_req_zone $binary_remote_addr zone=public_limit:10m rate=30r/m;
limit_req_zone $binary_remote_addr zone=submit_limit:10m rate=5r/m;

# 公開フォームサーバー
server {
    listen 443 ssl http2;
    server_name entry.example.com;

    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;

    location /api/public/qr/ {
        limit_req zone=public_limit burst=10 nodelay;
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /api/public/entries {
        limit_req zone=submit_limit burst=3 nodelay;
        proxy_pass http://backend:8000;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /api/public/ {
        limit_req zone=public_limit burst=10 nodelay;
        proxy_pass http://backend:8000;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location / {
        proxy_pass http://frontend:3000;
        proxy_set_header Host $host;
    }
}

# 管理画面サーバー（IP制限）
server {
    listen 443 ssl http2;
    server_name admin.example.com;

    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;

    # 社内IPホワイトリスト
    allow 192.168.0.0/16;
    allow 10.0.0.0/8;
    deny all;

    location /api/admin/ {
        proxy_pass http://backend:8000;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        proxy_pass http://frontend:3000;
        proxy_set_header Host $host;
    }
}

# HTTP → HTTPS リダイレクト
server {
    listen 80;
    server_name entry.example.com admin.example.com;
    return 301 https://$host$request_uri;
}
```

---

## 6. ディレクトリ構成

### バックエンド（FastAPI）

```
backend/
├── Dockerfile
├── requirements.txt
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 0001_initial_tables.py
└── app/
    ├── main.py              ← FastAPIアプリ本体・ルーター登録
    ├── config.py            ← Pydantic Settings（環境変数読み込み）
    ├── database.py          ← AsyncSession設定・get_db
    ├── deps.py              ← 依存性注入（get_current_user, verify_session_token等）
    │
    ├── models/              ← SQLAlchemy ORMモデル（テーブル定義）
    │   ├── __init__.py      ← 全モデルをインポート（Alembic用）
    │   ├── base.py          ← Base・UUID生成ヘルパー
    │   ├── company.py
    │   ├── admin_user.py
    │   ├── site.py
    │   ├── qr_code.py
    │   ├── worker.py
    │   ├── entry.py
    │   └── approval_log.py
    │
    ├── schemas/             ← Pydanticスキーマ（Request/Response型）
    │   ├── __init__.py
    │   ├── auth.py
    │   ├── site.py
    │   ├── qr_code.py
    │   ├── worker.py
    │   ├── entry.py
    │   └── common.py        ← PaginatedResponse等の共通型
    │
    ├── routers/
    │   ├── __init__.py
    │   ├── public/
    │   │   ├── __init__.py
    │   │   ├── qr.py        ← POST /api/public/qr/verify
    │   │   ├── workers.py   ← POST /api/public/workers/lookup, /workers
    │   │   └── entries.py   ← POST /api/public/entries, GET /status
    │   └── admin/
    │       ├── __init__.py
    │       ├── auth.py      ← login/logout/refresh/me
    │       ├── sites.py     ← CRUD
    │       ├── qrcodes.py   ← 発行・無効化・画像
    │       ├── entries.py   ← 一覧・詳細・承認・差戻し
    │       └── reports.py   ← dashboard
    │
    ├── services/            ← ビジネスロジック（routerから呼ぶ）
    │   ├── auth.py          ← JWT発行・検証・ロック管理
    │   ├── qr.py            ← トークン生成・PIN検証・セッション管理
    │   ├── worker.py        ← 電話番号正規化・照合・登録
    │   ├── entry.py         ← 申請作成・承認ステート管理
    │   └── rate_limit.py    ← Redis ベースのレート制限
    │
    └── utils/
        ├── security.py      ← bcrypt・JWT（RS256）ユーティリティ
        ├── qr_generator.py  ← qrcode ライブラリラッパー
        └── receipt.py       ← 受付番号生成（8桁英数字・重複チェック）
```

**requirements.txt（MVP最小構成）:**

```
fastapi==0.111.0
uvicorn[standard]==0.30.0
sqlalchemy[asyncio]==2.0.30
asyncpg==0.29.0
alembic==1.13.1
pydantic==2.7.1
pydantic-settings==2.2.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
redis[asyncio]==5.0.4
minio==7.2.7
qrcode[pil]==7.4.2
Pillow==10.3.0
python-multipart==0.0.9
httpx==0.27.0       # テスト用
pytest==8.2.0
pytest-asyncio==0.23.6
```

---

### フロントエンド（Next.js 14）

```
frontend/
├── Dockerfile
├── package.json
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── src/
    ├── app/
    │   ├── layout.tsx           ← ルートレイアウト（フォント・メタ）
    │   ├── not-found.tsx
    │   │
    │   ├── entry/               ← 公開フォーム（外部ユーザー向け）
    │   │   ├── layout.tsx       ← スマホ専用レイアウト（最大幅480px）
    │   │   └── [token]/
    │   │       ├── page.tsx     ← P01 QRランディング
    │   │       ├── pin/
    │   │       │   └── page.tsx ← P02 PIN入力
    │   │       ├── lookup/
    │   │       │   └── page.tsx ← P03 電話番号入力
    │   │       ├── confirm/
    │   │       │   └── page.tsx ← P04 作業員再利用確認
    │   │       ├── form/
    │   │       │   └── page.tsx ← P05 新規入力フォーム（多段階）
    │   │       ├── review/
    │   │       │   └── page.tsx ← P06 確認・送信
    │   │       └── complete/
    │   │           └── page.tsx ← P07 送信完了
    │   │
    │   ├── entry/status/
    │   │   └── [entry_id]/
    │   │       └── page.tsx     ← P08 申請状況確認
    │   │
    │   └── admin/               ← 管理画面（社内向け）
    │       ├── layout.tsx       ← 認証チェック・サイドバーレイアウト
    │       ├── login/
    │       │   └── page.tsx     ← A01 ログイン
    │       ├── page.tsx         ← A02 ダッシュボード
    │       ├── sites/
    │       │   ├── page.tsx     ← A03 現場一覧
    │       │   ├── new/
    │       │   │   └── page.tsx ← A04 現場作成
    │       │   └── [id]/
    │       │       ├── page.tsx         ← A08 現場詳細
    │       │       ├── edit/
    │       │       │   └── page.tsx     ← A04 現場編集
    │       │       └── qrcodes/
    │       │           └── page.tsx     ← A05 QR管理
    │       └── entries/
    │           ├── page.tsx     ← A06 申請一覧（承認待ち）
    │           └── [id]/
    │               └── page.tsx ← A07 申請詳細・承認
    │
    ├── components/
    │   ├── ui/                  ← 基本UIパーツ（Button, Input, Badge等）
    │   │   ├── button.tsx
    │   │   ├── input.tsx
    │   │   ├── badge.tsx
    │   │   ├── card.tsx
    │   │   └── dialog.tsx
    │   ├── entry/               ← 公開フォーム専用コンポーネント
    │   │   ├── StepIndicator.tsx    ← Step 1/4 表示
    │   │   ├── FormStep1.tsx        ← 基本情報
    │   │   ├── FormStep2.tsx        ← 連絡先
    │   │   ├── FormStep3.tsx        ← 所属
    │   │   ├── FormStep4.tsx        ← 入場情報
    │   │   └── WorkerConfirmCard.tsx ← 再利用確認カード
    │   └── admin/               ← 管理画面専用コンポーネント
    │       ├── Sidebar.tsx
    │       ├── EntryCard.tsx        ← 承認待ちカード（モバイル）
    │       ├── ApproveButton.tsx    ← ワンタップ承認ボタン
    │       └── QrCodeModal.tsx      ← QR発行モーダル
    │
    ├── lib/
    │   ├── api.ts               ← fetch ラッパー（エラーハンドリング共通化）
    │   ├── api-types.ts         ← API Request/Response の TypeScript型（手書き）
    │   ├── storage.ts           ← localStorage 一時保存ヘルパー
    │   ├── phone.ts             ← 電話番号正規化ユーティリティ
    │   └── validators.ts        ← Zod スキーマ（フォームバリデーション）
    │
    ├── hooks/
    │   ├── useSession.ts        ← QRセッショントークン管理
    │   ├── useAuth.ts           ← 管理者JWT管理（自動リフレッシュ）
    │   └── useDraft.ts          ← フォーム一時保存
    │
    └── types/
        └── index.ts             ← 共通型定義
```

**package.json（主要依存）:**

```json
{
  "dependencies": {
    "next": "14.2.3",
    "react": "^18",
    "react-dom": "^18",
    "react-hook-form": "^7.51.0",
    "zod": "^3.23.0",
    "@hookform/resolvers": "^3.3.4",
    "tailwindcss": "^3.4.0",
    "clsx": "^2.1.0"
  },
  "devDependencies": {
    "typescript": "^5",
    "@types/react": "^18",
    "@types/node": "^20",
    "eslint": "^8",
    "eslint-config-next": "14.2.3"
  }
}
```

---

## 7. 開発工程表 Day1〜Day14

### 前提

```
担当: 1名（Claude Code支援あり）
環境: Docker Compose ローカル開発
1日 = 実稼働6〜7時間想定
各Dayの末尾に「動作確認ポイント」を記載
```

---

### Day 1: インフラ・プロジェクト骨格

```
【午前】
□ リポジトリ作成（patrol-entry/）
□ .gitignore 設定（.env, secrets/, *.pem）
□ docker-compose.yml 作成（backend/postgres/redis/minio のみ）
□ docker-compose.override.yml 作成（開発用ポート公開）
□ .env ファイル作成（.env.exampleから）

【午後】
□ backend/ FastAPI 骨格作成
  - app/main.py（ルーターなし・healthcheckのみ）
  - app/config.py（Pydantic Settings）
  - app/database.py（AsyncSession）
  - requirements.txt
  - Dockerfile
□ frontend/ Next.js 骨格作成
  - npx create-next-app でスキャフォールド
  - tailwind, typescript 設定確認
  - Dockerfile（development用）

【動作確認】
  $ docker compose up
  → GET http://localhost:8000/health → {"status": "ok"}
  → http://localhost:3000 → Next.jsデフォルト画面
  → http://localhost:9001 → MinIOコンソール
```

---

### Day 2: DBモデル・マイグレーション

```
【午前】
□ alembic 初期化（alembic init alembic）
□ alembic/env.py を async対応に修正
□ app/models/base.py（Base クラス・UUID ヘルパー）
□ app/models/company.py
□ app/models/admin_user.py
□ app/models/site.py
□ app/models/__init__.py（全モデルインポート）

【午後】
□ app/models/qr_code.py
□ app/models/worker.py
□ app/models/entry.py
□ app/models/approval_log.py
□ alembic リビジョン作成・適用
□ postgres/init.sql にシードデータ追加

【動作確認】
  $ docker compose exec backend alembic upgrade head
  → エラーなく全テーブル作成
  $ docker compose exec postgres psql -U app entry_db -c "\dt"
  → 8テーブル一覧が表示される
```

---

### Day 3: 認証基盤（バックエンド）

```
【午前】
□ secrets/jwt_private.pem・jwt_public.pem 生成
  $ openssl genrsa -out secrets/jwt_private.pem 2048
  $ openssl rsa -in secrets/jwt_private.pem -pubout -out secrets/jwt_public.pem
□ app/utils/security.py
  - bcrypt ハッシュ化・検証
  - JWT（RS256）発行・検証
□ app/schemas/auth.py（LoginRequest, TokenResponse 等）
□ app/services/auth.py
  - ログイン処理・失敗回数管理（Redis）
  - トークン発行・リフレッシュ・失効

【午後】
□ app/deps.py
  - get_db（AsyncSession）
  - get_current_admin（JWT検証）
  - require_role（ロールチェック）
□ app/routers/admin/auth.py
  - POST /api/admin/auth/login
  - POST /api/admin/auth/logout
  - POST /api/admin/auth/refresh
  - GET  /api/admin/auth/me
□ app/main.py にルーター登録

【動作確認】
  $ curl -X POST localhost:8000/api/admin/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@example.com","password":"changeme"}'
  → access_token, refresh_token が返る
  $ curl localhost:8000/api/admin/auth/me \
    -H "Authorization: Bearer {token}"
  → ユーザー情報が返る
```

---

### Day 4: 現場管理 API + 管理画面ログイン

```
【午前】
□ app/schemas/site.py（SiteCreate, SiteResponse 等）
□ app/routers/admin/sites.py
  - GET  /api/admin/sites（ページネーション）
  - POST /api/admin/sites
  - GET  /api/admin/sites/{id}
  - PUT  /api/admin/sites/{id}

【午後】
□ frontend: src/lib/api.ts（fetchラッパー基本実装）
□ frontend: src/hooks/useAuth.ts（JWT管理）
□ frontend: A01 ログイン画面（/admin/login）
  - react-hook-form + Zod バリデーション
  - ログイン成功→ /admin へリダイレクト
  - エラー表示
□ frontend: admin/layout.tsx（認証チェック・未認証はloginへリダイレクト）

【動作確認】
  ブラウザで http://localhost:3000/admin/login を開く
  → admin@example.com / changeme でログイン
  → /admin へリダイレクトされる（画面はまだ空でOK）
```

---

### Day 5: 現場管理 UI + QR発行 API

```
【午前】
□ frontend: A03 現場一覧（/admin/sites）
□ frontend: A04 現場作成（/admin/sites/new）
□ frontend: A02 ダッシュボード（/admin）← 現場一覧カードのみ

【午後】
□ app/utils/qr_generator.py（qrcode → PNG バイト列）
□ app/utils/receipt.py（8桁受付番号生成）
□ app/schemas/qr_code.py
□ app/services/qr.py
  - トークン生成（secrets.token_urlsafe）
  - PIN bcrypt ハッシュ化
□ app/routers/admin/qrcodes.py
  - GET  /api/admin/sites/{id}/qrcodes
  - POST /api/admin/sites/{id}/qrcodes（QR発行）
  - PUT  /api/admin/qrcodes/{id}/deactivate
  - GET  /api/admin/qrcodes/{id}/image（PNG返却）
□ frontend: A05 QR管理（/admin/sites/[id]/qrcodes）

【動作確認】
  管理画面で現場を作成 → QRを発行
  → QR画像が表示される
  QR画像をスマホで読み取って URL を確認
  → https://entry.example.com/entry/{token} 形式になっている
```

---

### Day 6: QR検証 API + 公開フォーム P01-P02

```
【午前】
□ app/services/rate_limit.py（Redis ベースのレート制限デコレータ）
□ app/services/qr.py に追加:
  - セッショントークン発行（Redis保存・30分TTL）
  - PIN 検証・失敗カウント管理
□ app/routers/public/qr.py
  - POST /api/public/qr/verify

【午後】
□ frontend: entry/layout.tsx（スマホ専用レイアウト）
□ frontend: P01 QRランディング（/entry/[token]）
  - API-P01 でサーバーコンポーネントとして現場情報取得
  - トークン無効時のエラー画面
□ frontend: P02 PIN入力（/entry/[token]/pin）
  - PIN送信 → session_token をローカルに保存
  - 失敗カウント表示

【動作確認】
  QRをスマホで読み取る
  → /entry/{token} にアクセス → 現場名が表示される
  PIN設定ありのQR: PIN入力画面が表示される
  PIN入力成功 → session_tokenがlocalStorageに保存される
```

---

### Day 7: 作業員照合 API + 公開フォーム P03-P04

```
【午前】
□ app/utils/phone.py（電話番号正規化: 090-1234-5678 → 09012345678）
□ app/schemas/worker.py（WorkerLookupRequest, WorkerPreview 等）
□ app/services/worker.py
  - 電話番号正規化・照合（workers テーブル検索）
  - 既存エントリー重複チェック
□ app/routers/public/workers.py
  - POST /api/public/workers/lookup

【午後】
□ frontend: src/hooks/useSession.ts（session_token 管理）
□ frontend: P03 電話番号入力（/entry/[token]/lookup）
  - 電話番号入力 → API-P02 で照合
  - 既存 → P04、新規 → 同意ページ → P05
□ frontend: P04 作業員再利用確認（/entry/[token]/confirm）
  - 本人確認カード表示
  - 「はい」→ 最小入力（入場日・健康診断）→ P06（確認）

【動作確認】
  スマホで新規の電話番号を入力 → 「新規の方」として P05 へ
  既存の電話番号を入力 → 「田中さんですか？」カードが表示される
```

---

### Day 8: 新規作業員フォーム（P05）

```
【午前】
□ frontend: src/lib/validators.ts（全フォームの Zod スキーマ）
□ frontend: src/hooks/useDraft.ts（localStorage 一時保存）
□ frontend: components/entry/StepIndicator.tsx
□ frontend: components/entry/FormStep1.tsx（基本情報）
□ frontend: components/entry/FormStep2.tsx（連絡先・住所）

【午後】
□ frontend: components/entry/FormStep3.tsx（所属・職種）
□ frontend: components/entry/FormStep4.tsx（入場情報）
□ frontend: P05 フォーム統合（/entry/[token]/form）
  - 4ステップの状態管理
  - localStorage 自動保存
  - バリデーション表示

【動作確認】
  P03 → P05 の全ステップを入力できる
  途中でブラウザを閉じて戻ると「続きから」が表示される
  各ステップのバリデーションが機能する
```

---

### Day 9: 申請送信 API + P06-P08

```
【午前】
□ app/schemas/worker.py に WorkerCreate 追加
□ app/services/worker.py に worker 登録処理追加
□ app/services/entry.py
  - worker 作成 + entry 作成のトランザクション
  - 受付番号生成（重複チェックリトライ）
□ app/routers/public/workers.py
  - POST /api/public/workers（新規登録 + 申請）
□ app/routers/public/entries.py
  - POST /api/public/entries（既存worker + 申請）
  - GET  /api/public/entries/{id}/status

【午後】
□ frontend: P06 確認・送信（/entry/[token]/review）
  - 入力内容一覧表示
  - 送信ボタン（disabled 中は二重送信防止）
□ frontend: P07 送信完了（/entry/[token]/complete）
  - 受付番号大きく表示
  - スクリーンショット案内
□ frontend: P08 申請状況確認（/entry/status/[entry_id]）

【動作確認】
  スマホで最初から最後まで申請フローを通す
  完了画面に受付番号が表示される
  /entry/status/{entry_id} で「承認待ち」が確認できる
```

---

### Day 10: 承認待ち一覧 API + A06

```
【午前】
□ app/schemas/entry.py（EntryListItem, EntryDetail 等）
□ app/routers/admin/entries.py
  - GET /api/admin/entries（フィルタ・ページネーション）
  - GET /api/admin/entries/{id}

【午後】
□ frontend: components/admin/EntryCard.tsx（モバイル向け申請カード）
□ frontend: A06 申請一覧（/admin/entries）
  - タブ（承認待ち / 承認済み / 差戻し）
  - 申請カード一覧
  - プルダウン更新

【動作確認】
  管理画面でスマホアクセス
  → 申請一覧が縦並びカードで表示される
  → タップで詳細へ遷移できる
```

---

### Day 11: 承認・差戻し API + A07

```
【午前】
□ app/services/entry.py に approve/reject 追加
  - ステータス遷移バリデーション
  - approval_logs への記録
□ app/routers/admin/entries.py
  - PUT /api/admin/entries/{id}/approve
  - PUT /api/admin/entries/{id}/reject

【午後】
□ frontend: components/admin/ApproveButton.tsx（ワンタップ承認）
□ frontend: A07 申請詳細（/admin/entries/[id]）
  - 全情報表示
  - 承認/差戻しボタン（pending時のみ）
  - 差戻し理由テキストエリア
  - 承認ログ表示

【動作確認】
  スマホで申請詳細を開く → [承認する] をタップ
  → ステータスが「承認済み」になる
  /entry/status/{id} で承認済みと表示される
  → 差戻しも同様にテスト
```

---

### Day 12: ダッシュボード・現場詳細・仕上げ

```
【午前】
□ app/routers/admin/reports.py
  - GET /api/admin/reports/dashboard
□ frontend: A02 ダッシュボード完成（件数サマリー）
□ frontend: A08 現場詳細（/admin/sites/[id]）

【午後】
□ frontend: A03 現場一覧（検索・ソート追加）
□ frontend: サイドバーナビゲーション完成（全ページリンク）
□ 全画面のローディング・エラーハンドリング確認
□ 404・エラー画面の実装

【動作確認】
  ダッシュボードで承認待ち件数が正しく表示される
  現場詳細から申請一覧・QR管理に遷移できる
```

---

### Day 13: セキュリティ強化

```
【午前】
□ Nginx 本番設定確認（IP制限・レート制限・セキュリティヘッダー）
□ CORS 設定（FastAPI: 公開フォームドメインのみ許可）
□ 全公開APIのレート制限動作確認
  - 申請を6回連続送信 → 429 になることを確認
□ PIN 3回失敗ブロック動作確認
□ ログイン失敗ロック動作確認

【午後】
□ 入力バリデーション最終確認（全フィールド）
□ 受付番号の重複確認テスト
□ 同一作業員の同一現場重複申請ブロック確認
□ supervisorが担当外現場にアクセスできないことを確認
□ セッショントークンの30分期限切れ確認

【動作確認】
  社外IP（VPNオフ）から /admin にアクセス → 403
  社内IP から /admin にアクセス → ログイン画面が表示される
  レート制限が正しく機能している
```

---

### Day 14: 本番デプロイ・最終確認

```
【午前】
□ 本番サーバーに Docker + Docker Compose インストール
□ SSL証明書配置（Let's Encrypt or 自社証明書）
□ .env 本番値を設定
□ secrets/ の鍵ファイルを配置
□ docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

【午後】
□ 本番環境での全フロー動作確認
  1. 管理者がログイン → 現場作成 → QR発行
  2. スマホでQR読込 → 申請フォーム → 送信
  3. 管理者スマホで承認待ち確認 → 承認
  4. 申請状況確認ページで「承認済み」確認
□ バックアップ設定（postgres_data volume の定期バックアップ）
□ 監視設定（Uptime ツール等）
□ 管理者向け操作説明（口頭 or 簡易マニュアル）

【完了条件】
  ✅ スマホで現場のQRを読んで申請できる
  ✅ 監督スマホで承認できる
  ✅ 2回目の申請が30秒以内で完了する
  ✅ 社外IPから管理画面にアクセスできない
  ✅ HTTPS で通信される
```

---

## 8. Claude Code実装戦略

### 8.1 生成単位の原則

```
「1プロンプト = 1ファイル」を徹底する

❌ 悪い例（1プロンプトで複数ファイル）:
  「ORMモデルを全部作って」

✅ 良い例（1ファイルずつ）:
  「app/models/worker.py を作成してください。
   以下のスキーマ定義に従って SQLAlchemy の async モデルを作成してください:
   [テーブル定義をそのまま貼り付ける]」

理由: 複数ファイルを一度に生成すると
  ・インポートパスのミスが発見しにくい
  ・1ファイルのエラーで全体が壊れる
  ・レビューが困難になる
```

### 8.2 先に固定すべきファイル（変更コストが高い）

```
優先度 S（最初に作成・後から変えると全体に波及）:
  1. app/models/base.py          ← 全モデルの基底
  2. app/models/*.py（全モデル） ← DB変更はマイグレーション必要
  3. app/config.py               ← 環境変数の型定義
  4. app/database.py             ← DB接続設定
  5. src/lib/api-types.ts        ← フロントの型定義（APIレスポンスと一致させる）

優先度 A（早めに固定・変更は局所的）:
  6. app/deps.py                 ← 認証ミドルウェア（全ルーターが依存）
  7. app/utils/security.py       ← JWT/bcryptの実装
  8. src/lib/api.ts              ← APIクライアント（全ページが使う）

優先度 B（後から変更しやすい）:
  9. app/routers/*.py            ← ルーティングは追加しやすい
  10. src/app/**/*.tsx            ← UIは変更しやすい
```

### 8.3 後から変更しにくい箇所（特に注意）

```
⚠ テーブル名・カラム名
  → Alembicマイグレーションが必要
  → FK参照で変更が連鎖する
  → 決める前に必ずこの仕様書と照合する

⚠ URLパス構造（特にQR埋め込みURL）
  → /entry/{token} の形式を変えると、
    印刷済みのQRが全滅する
  → 現場に貼り出した後は変更不可

⚠ JWTペイロード構造
  → { sub, role, company_id } の構造を変えると
    全認証ミドルウェアの修正が必要

⚠ APIレスポンスのフィールド名
  → フロントエンドの型定義と厳密に一致させること
  → 変えると全ページの型エラーが発生

⚠ セッショントークンのRedisキー形式
  → qr_session:{token} → 変えるとログイン中のユーザーが全員ログアウト
```

### 8.4 Claude Codeへの指示テンプレート

```markdown
【バックエンドのモデル作成時】

app/models/worker.py を作成してください。

## 条件
- SQLAlchemy 2.x の async スタイルで書く
- Mapped[] と mapped_column() を使う（旧スタイルの Column() は使わない）
- UUID は str 型、アプリ側で uuid.uuid4() を使って生成（DB関数に依存しない）
- タイムゾーン付き datetime は DateTime(timezone=True) を使う
- ENUM は Python の str + CHECK 制約（Column(String(20), CheckConstraint(...))）

## テーブル定義
[この仕様書の TABLE: workers の内容を貼り付ける]

## 参照する既存ファイル
- app/models/base.py（Base クラスの定義を確認）
```

```markdown
【フロントエンドのページ作成時】

src/app/entry/[token]/lookup/page.tsx を作成してください。

## 画面仕様
[この仕様書の P03 電話番号入力画面 の内容を貼り付ける]

## 使用するAPI
[この仕様書の API-P02 の Request/Response を貼り付ける]

## 制約
- Next.js 14 App Router（サーバーコンポーネントとクライアントコンポーネントを適切に分ける）
- react-hook-form + zod でバリデーション
- src/lib/api.ts の fetch ラッパーを使う
- tailwindcss でスタイリング（インラインスタイルは使わない）
- スマホ最優先デザイン（タップターゲット 48px 以上）
```

### 8.5 テスト優先箇所

```
優先度 S（必ずテストを書く）:
  □ QR検証のセキュリティロジック
    - 無効トークン → 403
    - PIN不一致カウント・ブロック
    - 期限切れトークン → 403

  □ 承認ステータス遷移
    - pending → approved（正常）
    - approved → approved（409 Conflict）
    - rejected → approved（再申請フローを経ないと不可）

  □ 重複申請ブロック
    - 同一worker+site で pending があれば 409

  □ レート制限
    - 申請API: 6回目で 429

  □ 権限チェック
    - supervisorが担当外現場にアクセス → 403

優先度 A（テストを書くと良い）:
  □ 電話番号正規化（ハイフンあり/なし/全角/半角）
  □ 受付番号の重複回避リトライ
  □ supervisorロールのフィルタリング（自分の現場のみ）

優先度 B（手動確認でOK）:
  □ UI表示・スタイリング
  □ ページネーション
  □ 検索・フィルタ
```

### 8.6 実装崩壊を防ぐチェックリスト

```
各 Day の作業前:
  □ この IMPLEMENTATION_PLAN.md を開いて仕様を確認する
  □ 変更するファイルの依存関係を確認する

各ファイル作成後:
  □ docker compose exec backend python -m pytest（バックエンド）
  □ tsc --noEmit（フロントエンド型チェック）
  □ eslint で lint エラーがないことを確認

API 変更時（絶対ルール）:
  □ IMPLEMENTATION_PLAN.md の API仕様と一致しているか確認
  □ src/lib/api-types.ts を同時に更新する
  □ フロントエンドの呼び出し箇所を全て確認する

DB変更時（絶対ルール）:
  □ alembic revision --autogenerate でマイグレーション生成
  □ マイグレーションの内容を目視確認（autogenerate を盲信しない）
  □ テスト DB でマイグレーション適用確認
```

---

## 付録: 仕様凍結宣言

```
以下の仕様は MVPリリースまで変更を禁止する:

✅ URL構造: /entry/{token}/... および /admin/...
✅ DBテーブル名・カラム名（8テーブル）
✅ APIエンドポイント（22本）
✅ JWT構造: { sub: user_id, role: string, company_id: string }
✅ QRトークン形式: secrets.token_urlsafe(32) = 43文字
✅ 受付番号形式: 8桁英数字大文字
✅ Redisキー形式:
    qr_session:{token}            → QRセッション
    pin_fail:{token}:{ip_hash}    → PIN失敗カウント
    login_fail:{email}            → ログイン失敗カウント
    refresh_token:{token_id}      → リフレッシュトークン

変更が必要な場合は、このファイルの更新と
影響箇所の洗い出しを先に行うこと。
```
