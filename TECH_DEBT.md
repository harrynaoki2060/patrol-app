# 技術負債メモ

このファイルは「今は意図的に対応しない」選択をした事項をまとめる。
実装フェーズが進んだ時点で再評価すること。

---

## 1. PostgreSQL 依存箇所

### 1-1. 部分ユニークインデックス（Partial Unique Index）

```sql
-- worker_site_entries: 同一 worker × site の有効申請重複防止
CREATE UNIQUE INDEX uq_entries_worker_site_active
  ON worker_site_entries (worker_id, site_id)
  WHERE status IN ('draft', 'pending', 'approved');
```

**PostgreSQL 固有。SQLite / MySQL では動作しない。**

- Alembic の `alembic/versions/0001_initial_tables.py` の `create_index()` に `postgresql_where=` を使用している
- SQLite で実行すると `WHERE` 句が無視されて全行ユニークになる
- **影響範囲**: テスト環境で SQLite を使う場合に重複 INSERT が通ってしまう
- **対策**: テストは必ず PostgreSQL で実行する（`docker compose exec backend pytest`）

### 1-2. `TIMESTAMPTZ` 型

SQLAlchemy の `DateTime(timezone=True)` は PostgreSQL では `TIMESTAMPTZ` にマップされる。
SQLite では `DATETIME` になりタイムゾーン情報が失われる。

---

## 2. SQLite 非対応理由

| 理由 | 詳細 |
|---|---|
| 部分インデックス | WHERE 句付き UNIQUE INDEX が非対応 |
| TIMESTAMPTZ | タイムゾーン付き日時が非対応 |
| asyncpg | asyncio ドライバが PostgreSQL 専用 |
| connection pool | `pool_size` / `max_overflow` は PostgreSQL 向け設定 |

**結論**: このプロジェクトは PostgreSQL 専用。`aiosqlite` での代替テストは推奨しない。

---

## 3. 今後の改善候補

### 3-1. Alembic autogenerate の活用

現在は `0001_initial_tables.py` を手書きしている。
モデルを変更した場合は `alembic revision --autogenerate` で差分生成できるが、
PostgreSQL 固有の型・インデックスは手動確認が必要。

```bash
make migrate-new MSG="describe_the_change"
# → alembic/versions/xxxx_describe_the_change.py を確認してから
make migrate
```

### 3-2. DB マイグレーションの自動実行

現在は `make migrate` を手動実行が必要。
本番では起動時に `alembic upgrade head` を自動実行する仕組みが必要。

選択肢:
- `lifespan` の起動フックで実行（小規模向け）
- Kubernetes Job / Docker init container で実行（スケール向け）

### 3-3. Connection Pool チューニング

```python
# 現在の設定（app/db/session.py）
pool_size=5
max_overflow=10
pool_recycle=3600
```

本番の同時接続数・リクエスト数に応じて調整が必要。
PostgreSQL 側の `max_connections` (デフォルト 100) と合わせてチューニングすること。

### 3-4. Worker の updated_at（last_updated_at）の自動更新

```python
# worker.py
last_updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now(),  # ORM UPDATE 時にのみ発火
)
```

`onupdate=func.now()` は SQLAlchemy ORM 経由の UPDATE 時のみ動作する。
`session.execute(update(...))` などの「コア API」での UPDATE では更新されない。

**対策**: ORM の `session.merge()` や `setattr()` + `session.flush()` を使う。

### 3-5. receipt_number の生成ロジック

現在 `WorkerSiteEntry.receipt_number` は 8 桁英数字（大文字）と設計しているが、
実際の生成ロジックは未実装。衝突回避のための実装が必要（Day5 以降）。

---

## 4. セキュリティ未実装項目

| 項目 | 状態 | 予定 |
|---|---|---|
| JWT 認証 | ✅ 実装済み（Day3） | — |
| パスワード bcrypt ハッシュ化 | ✅ 実装済み（Day3） | — |
| PIN bcrypt ハッシュ化 | ✅ 実装済み（Day3 追加） | — |
| QR ブルートフォース保護 | ✅ 実装済み（Day3 追加） | — |
| entry_session トークン分離 | ✅ 実装済み（Day3 追加） | — |
| IP アドレスの SHA256 ハッシュ | ❌ 未実装 | Day6 |
| Nginx IP 制限（管理画面） | ❌ コメントアウト | Day8 |
| HTTPS / TLS 終端 | ❌ 未実装 | Day12 |
| Rate Limiting | ✅ Nginx 設定済み（qr_verify 専用ゾーン含む） | — |
| Input Validation | ✅ Pydantic + field_validator | — |
| JWT ブラックリスト（jti 管理） | ❌ 未実装（MVP 外） | Day10 以降 |
| Refresh Token の DB 保存 | ❌ 未実装（MVP 外） | Day10 以降 |
| ステータス遷移厳格化 | ✅ 実装済み（Day5: state_machine） | — |
| 承認ログ必須 | ✅ 実装済み（Day5: ApprovalService） | — |
| ロールスコープ強制 | ✅ 実装済み（Day5: SiteRepository.get_site_ids_for_user） | — |
| 承認者通知（メール/Slack） | ❌ 未実装 | Day8 以降 |

### 4-1. JWT ブラックリストについて

現状はリフレッシュトークン・entry_session トークンに `jti` (JWT ID) を付与しているが、
無効化リストの DB/Redis 保存は未実装。

**影響**: ログアウト後もトークンが有効期限まで使い続けられる。

**将来の実装方針**:
- Redis に `jti` を保存（有効期限 = トークンの `exp` に合わせて自動削除）
- `decode_token()` の後に Redis で `jti` の存在チェックを追加

```python
# 将来実装例（security.py）
async def is_token_revoked(jti: str) -> bool:
    return await redis.exists(f"revoked:{jti}")
```

### 4-2. QR ブロック後の管理者通知

現状は `logger.warning` のみでブロックを通知している。
本番では管理者へのメール通知・Slack 通知が望ましい。

### 4-3. 入場申請の二重送信防止

entry_session_token は JWT なので同一トークンで複数回 submit を呼べる。
ただし `uq_entries_worker_site_active` 部分インデックスにより、同一 worker × site で
有効な申請が 1 件しか作れないため、二重の「draft 作成」は防止できる。

submit の重複呼び出しは 409 を返す（`status != draft` チェック）ため実害はないが、
将来的に Redis で `jti` を管理して一度限りの使い捨てにすることを推奨。

### 4-4. 古い Draft のクリーンアップ

30 分の entry_session が切れた後も draft レコードは DB に残り続ける。
長期間放置された draft がテーブルを圧迫する可能性がある。

**将来の実装方針**:
- Celery / APScheduler で 24 時間以上 `last_saved_at` が更新されていない draft を削除
- または管理 API に「古い draft を一覧・削除する」エンドポイントを追加

### 4-5. Worker データの不整合

`DraftEntryService.update_draft()` は Worker レコードを直接更新する。
これにより、過去の申請に紐づく Worker 情報も同時に変わる。

**影響**: 旧申請の「申請時の氏名・住所」が現在の Worker データと異なる場合がある。

**将来の実装方針**:
- 申請確定（submit）時に Worker データのスナップショットを Entry に保存する
- または `worker_site_entries` に `snapshot_json JSONB` カラムを追加する（Day7 以降）

---

## 5. TODO / FIXME 一覧

| ファイル | 内容 |
|---|---|
| `docker-compose.yml` | Nginx の管理画面 IP 制限がコメントアウト |
| `backend/app/main.py` | 本番環境での `docs_url` / `redoc_url` 無効化 |
| `nginx/conf.d/default.conf` | `/api/admin/` の社内 IP 制限を有効化（コメントアウト中） |
| `alembic/versions/0001_initial_tables.py` | FK 制約の追加（現在は外部キー制約なし） |
| `backend/app/services/qr_verify.py` | entry_session_token の `jti` を Redis に保存して一度限りの使い捨てにする |
| `backend/app/api/public/entries.py` | X-Forwarded-For の trusted proxy 設定を nginx と合わせて確認すること |
| `backend/app/services/draft_entry.py` | 古い draft（24 時間以上更新なし）の自動クリーンアップジョブが未実装 |

---

## 6. 外部キー制約について

**現在の状態**: テーブル間の参照整合性は ORM レイヤーのみで保証。
DB レベルの `FOREIGN KEY` 制約は意図的に省略している。

**理由**:
- マイグレーションの順序管理が複雑になる
- テストデータ投入時にキー順序を気にしなくて済む
- 将来的にマイクロサービス化する可能性がある

**リスク**:
- ORM を通さない直接 INSERT ではデータ整合性が壊れる可能性がある
- 孤立レコードが発生しても DB が検知しない

**将来対応**: 本番リリース前に FK 制約を追加する `0003_add_foreign_keys.py` を作成予定。

---

---

## 7. 承認フロー 未実装項目

| 項目 | 状態 | 予定 |
|---|---|---|
| 承認通知（メール/Slack） | ❌ 未実装 | Day8 以降 |
| 取下げ API（`withdrawn` 遷移） | ❌ 未実装 | Day6 以降 |
| 再申請フロー（rejected → 新規 draft） | ❌ 未実装 | Day6 以降 |
| 一括承認 API | ❌ 未実装 | Day10 以降 |
| 承認ログの管理者向け閲覧 API | ❌ 未実装 | Day8 以降 |

### 7-1. approval_logs の外部キー制約

`approval_logs.entry_id` / `approval_logs.actor_id` に FK 制約を追加していない
（TECH_DEBT.md §6 の方針に準拠）。

`0005_add_foreign_keys.py` で追加予定:
```sql
ALTER TABLE approval_logs
  ADD CONSTRAINT fk_approval_logs_entry
    FOREIGN KEY (entry_id) REFERENCES worker_site_entries(id);
ALTER TABLE approval_logs
  ADD CONSTRAINT fk_approval_logs_actor
    FOREIGN KEY (actor_id) REFERENCES admin_users(id);
```

### 7-2. approval_logs の actor 情報の非正規化

現在 `actor_name` は `actor.name` をクエリ時に JOIN して取得している。
管理者ユーザーが削除された場合、`actor` が None になるが、
`ApprovalLogItem.actor_name` を None として返すだけで実害はない。

将来的には `actor_name` カラムを `approval_logs` に追加してスナップショット保存することを推奨
（削除されたアクターの名前も履歴に残る）。

### 7-3. ステータス遷移の `withdrawn`

`pending → withdrawn` は state_machine で許可しているが、
API エンドポイントは未実装（Day6 以降）。

_最終更新: 2026-05-20（Day5: 管理側承認・審査フロー基盤）_
