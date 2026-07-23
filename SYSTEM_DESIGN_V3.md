# 安全パトロールアプリ — システム設計書 V3
**作成日**: 2026-07-23  
**対象**: 同期システムの Vercel KV → Google 完全移行

---

## 0. 現状と移行方針

### 現状（V2）
| レイヤー | 現状 |
|---|---|
| UI / PWA | `index.html` 単一ファイル（2,759行・83関数） |
| ローカル保存 | IndexedDB（`patrol-db`）|
| サーバー同期 | Vercel KV（`/api/records`） |
| 写真 | base64 で IndexedDB に保存 |

### 移行方針
- **UI・PWA・PDF・写真撮影・IndexedDB は一切変更しない**
- **同期レイヤーのみ置き換える**（Vercel KV → Google）
- index.html の既存関数はそのまま保持し、外部 JS ファイルに同期処理を追加
- 段階的実装（Phase 1→5）、各 Phase で動作確認してから次へ

---

## 1. アーキテクチャ全体図

```
[端末] ─── IndexedDB（オフライン時はここだけ）
    │
    │  オンライン時
    ▼
[Google Apps Script Web App]
    ├── doGet()  → Spreadsheet 読み取り
    └── doPost() → Spreadsheet 書き込み / Drive 写真アップロード

[Google Spreadsheet] ─── レコードデータ（1行1レコード）
[Google Drive]        ─── 写真ファイル（フォルダ構造）
```

### 認証方式
Google OAuth は不要。GAS Web App を下記設定でデプロイ：
- **実行者**: スクリプトオーナー（会社アカウント）
- **アクセス**: 「全員」
- **セキュリティ**: リクエストに `X-API-Key` ヘッダーを必須化（設定画面で入力）

---

## 2. ファイル構成（移行後）

```
patrol-app/
├── index.html              ← 既存のまま（UI・PDF・写真・PWA）
├── js/                     ← 新規ディレクトリ（同期モジュール群）
│   ├── storage.js          ← IndexedDB ヘルパー（index.html から移植）
│   ├── google-api.js       ← GAS への HTTP 通信
│   ├── sync.js             ← 同期オーケストレーション
│   ├── photo-sync.js       ← Drive への写真アップロード
│   └── pdf.js              ← PDF生成（将来分離用・Phase5）
├── sw.js                   ← 既存のまま
├── manifest.json           ← 既存のまま
├── api/                    ← 既存のまま（Vercel KV は残すが使用停止）
│   ├── health.js
│   └── records.js
└── gas/
    └── Code.gs             ← GAS ソースコード（手動デプロイ）
```

### index.html への追加（最小変更）
```html
<!-- 既存の </body> 直前に追加するだけ -->
<script src="/js/storage.js"></script>
<script src="/js/google-api.js"></script>
<script src="/js/photo-sync.js"></script>
<script src="/js/sync.js"></script>
```

---

## 3. Google Apps Script 設計（`gas/Code.gs`）

### エンドポイント設計
GAS は GET / POST のみサポートするため、`action` パラメーターで振り分け。

```
GET  ?action=records&updatedSince=ISO_DATE    → 更新されたレコード一覧
GET  ?action=record&id=xxx                    → 1件取得
POST action=upsert  body:{record}             → 新規・更新
POST action=delete  body:{id, deletedAt}      → 論理削除
POST action=photo   body:{recordId, base64, name, mimeType, yearMonth} → Drive 保存
GET  ?action=photo&fileId=xxx                 → Drive URL 取得
GET  ?action=health                           → 接続確認
```

### GAS 関数構成
```javascript
// gas/Code.gs

function doGet(e)  { /* action に応じてルーティング */ }
function doPost(e) { /* action に応じてルーティング */ }

// Records (Spreadsheet)
function getRecords(updatedSince)
function upsertRecord(record)
function deleteRecord(id, deletedAt)

// Photos (Drive)
function savePhoto(recordId, base64, name, mimeType, yearMonth)
function getOrCreateFolder(yearMonth)   // 安全パトロール/YYYY/MM を取得・作成

// Auth
function checkApiKey(headers)
```

---

## 4. Google Spreadsheet スキーマ

### シート名: `Records`

| 列 | フィールド名 | 型 | 説明 |
|---|---|---|---|
| A | id | number | `Date.now()` で生成したタイムスタンプID |
| B | date | string | 点検日 `YYYY-MM-DD` （JST） |
| C | projectName | string | 工事名称 |
| D | termStart | string | 工期開始 `YYYY-MM-DD` |
| E | termEnd | string | 工期終了 `YYYY-MM-DD` |
| F | contractor | string | 受注者名 |
| G | subcontractor | string | 協力業者 |
| H | inspector | string | 点検者 |
| I | progressRate | number | 進捗率 0〜100 |
| J | notes1 | string | 施工進捗 |
| K | notes2 | string | 竣工書類進捗 |
| L | notes3 | string | その他問題点 |
| M | checks | string | チェック結果 JSON `{"1-1":"OK","1-2":"NG",...}` |
| N | photoCount | number | 写真枚数 |
| O | photoMeta | string | 写真メタ JSON `[{fileId,url,name,takenAt},...]` |
| P | updatedAt | string | 最終更新日時 `YYYY-MM-DD HH:mm:ss` （JST） |
| Q | deleted | boolean | 論理削除フラグ（TRUE / FALSE） |

### シート名: `SyncLog`（任意・診断用）
| 列 | 内容 |
|---|---|
| A | 同期日時 |
| B | 端末UA |
| C | 送信件数 |
| D | 取得件数 |
| E | 写真枚数 |
| F | エラー内容 |

---

## 5. Google Drive フォルダ構成

```
マイドライブ/
└── 安全パトロール/          ← FOLDER_ROOT_NAME（GAS定数）
    ├── 2026/
    │   ├── 07/
    │   │   ├── {recordId}_{photoName}.jpg
    │   │   └── ...
    │   └── 08/
    └── 2027/
```

写真ファイル名規則: `{recordId}_{index}_{photoName}.jpg`  
Drive 共有設定: 「リンクを知っている全員が閲覧可」（縮小画像として index.html に表示）

---

## 6. 同期アルゴリズム詳細

### 6-1. アップロード（ローカル → サーバー）
```
対象: records.synced === false
処理:
  1. テキストデータを Spreadsheet へ upsert
     → サーバー側で updatedAt を上書きして保存
  2. 写真を Drive へ 1枚ずつアップロード
     → 成功したら photoMeta に fileId / url を記録
  3. ローカルの record.synced = true へ更新
     ※ アップロード失敗しても IndexedDB のデータは消さない
```

### 6-2. ダウンロード（サーバー → ローカル）
```
処理:
  1. GET /records?updatedSince={lastSyncAt}
     → 前回同期以降に更新されたレコードを取得
  2. 各レコードについてマージ判断:
       if (サーバーの updatedAt > ローカルの updatedAt)
           → サーバーデータで上書き（テキスト部分のみ）
             写真は ローカルの photos[] を優先保持
       else
           → ローカルを維持
  3. サーバーにあってローカルにない → 追加（photos: []）
  4. deleted=true のレコード → ローカルも論理削除
     （IndexedDB から消さず deleted フラグを立てる）
```

### 6-3. マージ優先ルール
```
テキストデータ: updatedAt が新しい方が勝ち
写真データ:     ローカル優先（Drive URL があればそれを使用）
削除:           deleted=true は最強（復活させない）
```

### 6-4. 競合シナリオ
| シナリオ | 対処 |
|---|---|
| 2端末が同じレコードを編集 | updatedAt が新しい方で上書き |
| オフライン中に編集 → オンライン時に他端末更新あり | 双方の updatedAt を比較して最新優先 |
| 削除と編集が競合 | deleted=true が優先 |

---

## 7. 写真移行方針

### 現状（V2）
- base64 データURL を IndexedDB の `photos[]` 配列に保存
- PDF出力時はそのまま `<img src="data:...">` として埋め込み

### 移行後（V3）
- IndexedDB は**変更なし**（base64 のまま保持）
- 同期時のみ Drive へアップロード → URL を取得
- `record.photoMeta` に Drive URL を追加保存
- PDF 出力は引き続き IndexedDB の base64 を使用（Drive URL への切り替えは Phase5 以降で検討）

```javascript
// IndexedDB record 構造（追加フィールド）
{
  ...既存フィールド,
  photos: [{ dataUrl, name, takenAt }],    // 既存（base64）
  photoMeta: [{ fileId, url, name, takenAt }]  // 新規追加（Drive URL）
}
```

---

## 8. 設定画面（追加項目）

既存の設定モーダルに以下を追加：

```
┌─────────────────────────────────┐
│ 🔧 Google 同期設定              │
│                                 │
│ GAS Web App URL                 │
│ [https://script.google.com/...] │
│                                 │
│ API キー                        │
│ [************************]      │
│                                 │
│ 同期グループID（任意）           │
│ [nishino-company]               │
│                                 │
│ 最終同期: 2026/07/23 14:30      │
│ ステータス: 🟢 接続中           │
│                                 │
│ [🔄 今すぐ同期]                 │
└─────────────────────────────────┘
```

localStorage キー:
- `patrol_gas_url`
- `patrol_gas_key`
- `patrol_group_id`
- `patrol_last_sync`

---

## 9. 診断画面追加項目

既存の `runSyncDiag()` に以下セクションを追加：

```
🌐 Google 接続状態
  GAS URL          https://script.google.com/...（設定済み / 未設定）
  Spreadsheet      ✅ 接続OK / ❌ 未接続
  Drive            ✅ 接続OK / ❌ 未接続
  API応答時間      245ms
  最終同期日時     2026/07/23 14:30:22
  同期件数         12件（送信5 / 受信7）
  写真同期件数     8枚
  同期失敗理由     -
```

---

## 10. 実装フェーズ計画

### Phase 1: Google Apps Script 作成
**作業**: `gas/Code.gs` を作成 → Google アカウントで手動デプロイ  
**成果物**: GAS Web App URL（例: `https://script.google.com/macros/s/xxx/exec`）  
**確認**: ブラウザで `?action=health` を叩いて `{"ok":true}` が返ること  
**index.html 変更**: なし  

### Phase 2: Spreadsheet 同期（テキストのみ）
**作業**: `js/google-api.js` + `js/sync.js` を作成  
`index.html` の `</body>` 前に script タグを2行追加  
**成果物**: 同期ボタンでテキストデータが Spreadsheet に保存される  
**確認**: Spreadsheet に Records シートが作成されレコードが書き込まれること  
**index.html 変更**: `</body>` 前に `<script>` 2行追加のみ  

### Phase 3: Drive 写真同期
**作業**: `js/photo-sync.js` を作成  
同期時に base64 → Drive アップロード → URL 保存  
**成果物**: 写真が Drive の年月フォルダに保存される  
**確認**: Drive フォルダに写真ファイルが作成されること  
**index.html 変更**: `<script>` 1行追加のみ  

### Phase 4: 双方向同期（ダウンロード）
**作業**: `sync.js` にダウンロード処理を追加  
マージアルゴリズムを実装  
**成果物**: 複数端末で同一データになること  
**確認**: PC で入力 → iPad で同期 → 同じ一覧になること  
**index.html 変更**: なし  

### Phase 5: 診断画面強化 + モジュール整理
**作業**: `runSyncDiag()` に Google 接続状態セクション追加  
不要になった Vercel KV 同期コードを整理  
`pdf.js` 分離（任意）  
**成果物**: 診断画面で Google 状態が確認できる  
**index.html 変更**: `runSyncDiag()` 内に数行追加  

---

## 11. 既存機能への影響範囲

| 機能 | 変更 | 理由 |
|---|---|---|
| 入力フォーム | **なし** | 変更不要 |
| IndexedDB保存 | **なし** | 引き続き使用 |
| 通常PDF | **なし** | base64写真をそのまま使用 |
| 役所提出PDF | **なし** | base64写真をそのまま使用 |
| 写真撮影・圧縮 | **なし** | base64保存はそのまま |
| 写真並び替え | **なし** | 変更不要 |
| PWA・Service Worker | **なし** | 変更不要 |
| 履歴一覧 | **なし** | renderHistory()は変更不要 |
| 診断パネル | **追加のみ** | 既存行を消さず追記 |
| 設定モーダル | **追加のみ** | GAS設定欄を追記 |
| Vercel KV同期 | **停止** | GAS同期に置き換え（API削除はしない） |

---

## 12. リスクと対策

| リスク | 対策 |
|---|---|
| GAS デプロイURL変更 | 設定画面から URL を変更可能にする |
| GAS 実行時間制限（6分/実行） | 1回の同期を小分けにして実行 |
| Drive 容量不足 | 写真圧縮は既存の1000px/0.5品質を流用 |
| Spreadsheet 同時書き込み競合 | GAS 側で `LockService` を使用 |
| API キー漏洩 | localStorage 保存（WebView内のみ使用） |
| Phase移行中の二重同期 | `localStorage.patrol_sync_engine = 'gas'` フラグで切り替え |

---

## 13. 承認チェックリスト

以下を確認の上、実装承認をお願いします。

- [ ] Google アカウント（GAS・Spreadsheet・Drive のオーナー）が準備できている
- [ ] GAS Web App URL をアプリに設定する手順を理解した
- [ ] API キーを任意の文字列で決定できる（例: `patrol-2026-abc`）
- [ ] Phase 1 完了後に動作確認を行う時間がある
- [ ] 写真の Drive 保存に同意した（Drive 容量を使用する）
- [ ] 既存の Vercel KV データは移行しない（新規同期から開始）に同意した

---

*本設計書承認後、Phase 1（GAS作成）の実装を開始します。*
