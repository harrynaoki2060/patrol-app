# 本番デプロイガイド

建設工事 新規入場管理システムの VPS/社内 LAN サーバーへのデプロイ手順。

---

## 目次

1. [事前準備](#1-事前準備)
2. [サーバー初期設定](#2-サーバー初期設定)
3. [アプリケーションのデプロイ](#3-アプリケーションのデプロイ)
4. [SSL 証明書の取得（Let's Encrypt）](#4-ssl-証明書の取得)
5. [初回起動と動作確認](#5-初回起動と動作確認)
6. [管理者アカウントの作成](#6-管理者アカウントの作成)
7. [バックアップの運用](#7-バックアップの運用)
8. [証明書の定期更新](#8-証明書の定期更新)
9. [ゼロダウンタイム更新](#9-ゼロダウンタイム更新)
10. [障害対応・ログ確認](#10-障害対応ログ確認)
11. [社内 LAN 運用時の追加設定](#11-社内-lan-運用時の追加設定)

---

## 1. 事前準備

### 必要なもの

| 項目 | 要件 |
|------|------|
| OS | Ubuntu 22.04 LTS / Debian 12（推奨） |
| CPU | 2 コア以上 |
| RAM | 2 GB 以上（4 GB 推奨） |
| ストレージ | 20 GB 以上（バックアップ除く） |
| ドメイン | 固定 IP にバインドされたドメイン名（Let's Encrypt 用） |
| Docker | 24.x 以上 |
| Docker Compose | v2 系（`docker compose` コマンドが使えること） |

### ポート開放

| ポート | 用途 |
|--------|------|
| 80/tcp | HTTP（ACME challenge + HTTPS リダイレクト） |
| 443/tcp | HTTPS（本番トラフィック） |
| 22/tcp | SSH（管理用、IP 制限推奨） |

---

## 2. サーバー初期設定

```bash
# システム更新
sudo apt update && sudo apt upgrade -y

# Docker インストール
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# git インストール
sudo apt install -y git

# ファイアウォール設定 (ufw)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp  # SSH
sudo ufw enable
```

---

## 3. アプリケーションのデプロイ

### 3-1. リポジトリをクローン

```bash
cd /opt
sudo git clone https://your-repo-url/patrol-app.git
sudo chown -R $USER:$USER patrol-app
cd patrol-app
```

### 3-2. 環境変数を設定

```bash
cp .env.production .env
nano .env   # 各値を本番用に書き換える
```

**必ず変更する項目:**

| 変数 | 説明 | 生成方法 |
|------|------|----------|
| `DOMAIN` | ドメイン名 | 手動入力 |
| `DB_PASSWORD` | PostgreSQL パスワード | `openssl rand -base64 18 \| tr -dc 'a-zA-Z0-9' \| head -c 24` |
| `REDIS_PASSWORD` | Redis パスワード | 同上 |
| `MINIO_ACCESS_KEY` | MinIO アクセスキー | 手動（英数字 20 文字以上） |
| `MINIO_SECRET_KEY` | MinIO シークレット | `openssl rand -base64 24 \| tr -dc 'a-zA-Z0-9' \| head -c 32` |
| `SECRET_KEY` | JWT 署名鍵 | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `CERTBOT_EMAIL` | Let's Encrypt 通知先 | 手動入力 |

> ⚠️ **`SECRET_KEY` が漏洩するとすべての JWT トークンが偽造可能になります。**  
> 64 文字以上のランダム文字列を必ず設定し、Git にコミットしないこと。

### 3-3. Docker イメージをビルド

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml build
```

---

## 4. SSL 証明書の取得

### 4-1. 一時的に HTTP のみで起動（ACME challenge 用）

証明書取得前は nginx が 443 の証明書を読もうとして起動失敗します。  
まず証明書なしで nginx を起動できるよう一時設定が必要です。

```bash
# nginx だけ開発用設定で起動
docker compose up -d nginx

# 確認
curl http://YOUR_DOMAIN/nginx-health
```

### 4-2. Let's Encrypt 証明書を取得

```bash
source .env  # DOMAIN と CERTBOT_EMAIL を読み込む

docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm certbot \
  certonly \
  --webroot \
  -w /var/www/certbot \
  -d ${DOMAIN} \
  --email ${CERTBOT_EMAIL} \
  --agree-tos \
  --no-eff-email
```

取得成功のメッセージ例:
```
Successfully received certificate.
Certificate is saved at: /etc/letsencrypt/live/entry.example.com/fullchain.pem
```

---

## 5. 初回起動と動作確認

```bash
# 全サービスを本番設定で起動
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 状態確認
docker compose ps

# DB マイグレーション実行（初回のみ）
docker compose exec backend alembic upgrade head

# ヘルスチェック
curl https://YOUR_DOMAIN/api/health
```

期待するレスポンス:
```json
{"status": "ok", "version": "0.1.0"}
```

---

## 6. 管理者アカウントの作成

```bash
# スーパー管理者アカウント作成
docker compose exec backend python scripts/create_admin.py \
  --email admin@your-company.com \
  --password "Strong_Password_Here!" \
  --name "システム管理者" \
  --role super_admin

# 確認
curl -s -X POST https://YOUR_DOMAIN/api/admin/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@your-company.com","password":"Strong_Password_Here!"}' \
  | python3 -m json.tool
```

---

## 7. バックアップの運用

### 自動バックアップ

`backup` コンテナが起動中、毎日 **UTC 02:00**（日本時間 11:00）に自動実行:
- `pg_dump` → `/var/lib/docker/volumes/patrol-app_backup_data/_data/postgres/`
- MinIO mirror → 同ディレクトリの `minio/` 以下

### 手動バックアップ

```bash
# PostgreSQL バックアップ（今すぐ実行）
docker compose exec backup sh /scripts/backup_postgres.sh

# MinIO バックアップ（今すぐ実行）
docker compose exec backup sh /scripts/backup_minio.sh

# バックアップ一覧確認
docker compose exec backup ls -lh /backups/postgres/
```

### バックアップからのリストア

```bash
# バックアップファイルを確認
docker compose exec backup ls -lh /backups/postgres/

# リストア（対話式・確認あり）
docker compose exec backup sh /scripts/restore_postgres.sh \
  /backups/postgres/entry_db_20260521_020000.sql.gz

# マイグレーション状態を確認
docker compose exec backend alembic current
```

### バックアップファイルを外部にコピー

```bash
# Docker Volume からホストにコピー
docker cp $(docker compose ps -q backup):/backups/postgres/entry_db_YYYYMMDD_HHMMSS.sql.gz ./

# または rsync でバックアップサーバーに転送
rsync -avz \
  "$(docker volume inspect patrol-app_backup_data --format '{{.Mountpoint}}')/postgres/" \
  backup-server:/backups/patrol-app/
```

---

## 8. 証明書の定期更新

Let's Encrypt 証明書は **90 日で期限切れ**になります。  
以下のコマンドを cron に登録して自動更新します。

### ホストの cron に登録

```bash
crontab -e
```

以下を追加（毎月 1 日 03:00 に実行）:

```cron
0 3 1 * * cd /opt/patrol-app && \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm certbot renew && \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml exec nginx nginx -s reload \
  >> /var/log/certbot-renew.log 2>&1
```

### 手動更新

```bash
cd /opt/patrol-app

# 証明書を更新
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm certbot renew

# nginx を再読込（ダウンタイムなし）
docker compose exec nginx nginx -s reload
```

---

## 9. ゼロダウンタイム更新

アプリケーションコードを更新する手順:

```bash
cd /opt/patrol-app

# 1. 最新コードを取得
git pull

# 2. 新イメージをビルド（既存コンテナは継続稼働）
docker compose -f docker-compose.yml -f docker-compose.prod.yml build backend frontend

# 3. DB マイグレーション（必要な場合）
docker compose exec backend alembic upgrade head

# 4. バックエンドのみ再起動（フロントエンドは最後）
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps backend

# 5. フロントエンドを再起動
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps frontend

# 6. ヘルスチェック
curl https://YOUR_DOMAIN/api/health
```

> **注**: `--no-deps` オプションで依存サービス（DB/Redis）を再起動せずにアプリのみ更新できます。

---

## 10. 障害対応・ログ確認

### ログの確認

```bash
# 全サービスのログ（リアルタイム）
docker compose logs -f

# バックエンドのみ（最新 100 行）
docker compose logs --tail=100 backend

# nginx アクセスログ
docker compose logs nginx | grep '"GET\|POST\|PATCH\|DELETE'

# 監査ログのみ抽出（JSON フィルタリング）
docker compose logs backend | grep '"event":' | python3 -m json.tool
```

### よくある問題

#### nginx が起動しない（証明書エラー）

```bash
# 証明書の確認
docker compose exec nginx ls -la /etc/letsencrypt/live/

# nginx 設定テスト
docker compose exec nginx nginx -t
```

#### DB 接続エラー

```bash
# PostgreSQL の状態確認
docker compose exec postgres pg_isready -U app -d entry_db

# 接続テスト
docker compose exec backend python -c \
  "import asyncio; from app.db.session import check_db_connection; print(asyncio.run(check_db_connection()))"
```

#### Redis 接続エラー

```bash
# Redis の状態確認
docker compose exec redis redis-cli -a "${REDIS_PASSWORD}" ping
```

#### バックアップコンテナが動いていない

```bash
docker compose ps backup
docker compose logs backup
```

---

## 11. 社内 LAN 運用時の追加設定

社内 LAN のみで運用し、外部からアクセス不可にする場合:

### nginx で管理 API を社内 IP に制限

`nginx/conf.d/default.prod.conf.template` の管理 API セクションを編集:

```nginx
location /api/admin/ {
    # 社内 LAN の IP アドレス範囲を指定
    allow 192.168.0.0/16;   # 例: 社内 LAN
    allow 10.0.0.0/8;       # 例: VPN
    deny all;               # それ以外は拒否

    limit_req zone=admin_api burst=20 nodelay;
    proxy_pass http://backend;
    ...
}
```

編集後:
```bash
# 設定を再読込
docker compose exec nginx nginx -s reload
```

### Let's Encrypt なし（自己署名証明書）の場合

社内 LAN で公開ドメインなしの場合、自己署名証明書を使用:

```bash
# 自己署名証明書生成
openssl req -x509 -newkey rsa:4096 -sha256 -days 3650 \
  -keyout /etc/ssl/private/patrol-app.key \
  -out /etc/ssl/certs/patrol-app.crt \
  -subj "/CN=patrol-app.local"
```

nginx.conf の証明書パスを変更:
```nginx
ssl_certificate     /etc/ssl/certs/patrol-app.crt;
ssl_certificate_key /etc/ssl/private/patrol-app.key;
```

> ⚠️ 自己署名証明書の場合、ブラウザで警告が出ます。  
> 組織の CA 証明書を使用するか、mkcert を使って社内 CA を構築することを検討してください。

---

## セキュリティチェックリスト

デプロイ後に以下を確認してください:

- [ ] `.env` ファイルのパーミッション: `chmod 600 .env`
- [ ] `SECRET_KEY` が 64 文字以上のランダム文字列
- [ ] 全パスワードがデフォルト値 (`changeme_*`) から変更済み
- [ ] SSH が鍵認証のみ（パスワード認証無効）
- [ ] ufw / iptables で不要ポートを閉鎖
- [ ] MinIO 管理コンソール（:9001）が外部に公開されていない
- [ ] バックアップが正常に取得されていることを確認
- [ ] `curl https://YOUR_DOMAIN/api/health` が 200 を返す
- [ ] HTTPS 評価: [SSL Labs](https://www.ssllabs.com/ssltest/) で A 以上を確認
