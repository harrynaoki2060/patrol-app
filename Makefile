# =============================================================================
# 建設工事 新規入場管理システム — 開発用 Makefile
# 使い方: make <target>
# =============================================================================

.PHONY: help up down restart logs ps \
        migrate migrate-down migrate-reset db-shell db-tables db-indexes \
        test test-v test-cov lint format \
        test-approval test-worker test-qr test-site-admin \
        test-fe test-fe-watch \
        build clean \
        prod-up prod-down prod-build prod-logs prod-ps \
        backup backup-restore ssl-renew audit-logs

# デフォルトターゲット
help:
	@echo ""
	@echo "  建設工事 新規入場管理システム — 開発コマンド"
	@echo ""
	@echo "  【Docker】"
	@echo "  make up            全サービス起動"
	@echo "  make down          全サービス停止"
	@echo "  make restart       全サービス再起動"
	@echo "  make logs          全サービスのログを表示（Ctrl+C で終了）"
	@echo "  make logs-backend  Backend のログのみ"
	@echo "  make ps            サービス一覧と状態"
	@echo "  make build         Docker イメージをリビルド"
	@echo "  make clean         停止 + volumes 削除（DB データも消える）"
	@echo ""
	@echo "  【DB / Alembic】"
	@echo "  make migrate       alembic upgrade head（最新へ）"
	@echo "  make migrate-down  alembic downgrade base（全テーブル削除）"
	@echo "  make migrate-reset downgrade base → upgrade head（再作成）"
	@echo "  make db-shell      psql を起動"
	@echo "  make db-tables     テーブル一覧を表示"
	@echo "  make db-indexes    インデックス一覧を表示"
	@echo "  make db-constraints 制約一覧を表示"
	@echo ""
	@echo "  【テスト】"
	@echo "  make test          pytest を実行"
	@echo "  make test-v        pytest -v（詳細出力）"
	@echo "  make test-cov      カバレッジ付きテスト"
	@echo ""
	@echo "  【本番環境】"
	@echo "  make prod-up       本番構成で起動"
	@echo "  make prod-down     本番サービス停止"
	@echo "  make prod-build    本番イメージをビルド"
	@echo "  make prod-logs     本番ログをリアルタイム表示"
	@echo "  make ssl-renew     SSL 証明書を更新"
	@echo "  make backup        バックアップを今すぐ実行"
	@echo "  make backup-list   バックアップ一覧を表示"
	@echo "  make audit-logs    監査ログを表示（最新 50 件）"
	@echo ""

# =============================================================================
# Docker 操作
# =============================================================================

up:
	docker compose up -d
	@echo ""
	@echo "サービスが起動しました。"
	@echo "  API: http://localhost/api/health"
	@echo "  Docs: http://localhost/api/docs"
	@echo "  MinIO: http://localhost:9001"
	@echo ""
	docker compose ps

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

logs-backend:
	docker compose logs -f backend

logs-db:
	docker compose logs -f postgres

ps:
	docker compose ps

build:
	docker compose build

clean:
	@echo "⚠️  全サービスを停止し、volumes（DBデータ含む）を削除します。よろしいですか？ [y/N]"
	@read ans; if [ "$$ans" = "y" ]; then \
		docker compose down -v; \
		echo "クリーンアップ完了"; \
	else \
		echo "キャンセルしました"; \
	fi

# =============================================================================
# Alembic マイグレーション
# =============================================================================

migrate:
	docker compose exec backend alembic upgrade head

migrate-status:
	docker compose exec backend alembic current
	docker compose exec backend alembic history

migrate-down:
	docker compose exec backend alembic downgrade base

migrate-reset: migrate-down migrate
	@echo "マイグレーションをリセットしました"

# 新しいマイグレーションファイルを autogenerate で作成
# 使い方: make migrate-new MSG="add_column_xxx"
migrate-new:
	docker compose exec backend alembic revision --autogenerate -m "$(MSG)"

# =============================================================================
# DB 確認
# =============================================================================

db-shell:
	docker compose exec postgres psql -U app -d entry_db

db-tables:
	docker compose exec postgres psql -U app -d entry_db -c \
		"SELECT tablename, tableowner FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"

db-indexes:
	docker compose exec postgres psql -U app -d entry_db -c \
		"SELECT indexname, tablename, indexdef FROM pg_indexes WHERE schemaname = 'public' ORDER BY tablename, indexname;"

db-constraints:
	docker compose exec postgres psql -U app -d entry_db -c \
		"SELECT tc.constraint_name, tc.constraint_type, tc.table_name, kcu.column_name \
		 FROM information_schema.table_constraints tc \
		 JOIN information_schema.key_column_usage kcu \
		   ON tc.constraint_name = kcu.constraint_name \
		 WHERE tc.table_schema = 'public' \
		 ORDER BY tc.table_name, tc.constraint_type;"

db-check-entries:
	docker compose exec postgres psql -U app -d entry_db -c \
		"SELECT schemaname, tablename, indexname, indexdef \
		 FROM pg_indexes \
		 WHERE tablename = 'worker_site_entries' \
		 ORDER BY indexname;"

# =============================================================================
# テスト
# =============================================================================

test:
	docker compose exec backend pytest

test-v:
	docker compose exec backend pytest -v

test-cov:
	docker compose exec backend pytest --cov=app --cov-report=term-missing

test-session:
	docker compose exec backend pytest tests/test_db_session.py -v

test-repo:
	docker compose exec backend pytest tests/test_repositories.py -v

test-health:
	docker compose exec backend pytest tests/test_health_api.py -v

test-auth:
	docker compose exec backend pytest tests/test_auth.py -v

test-qr:
	docker compose exec backend pytest tests/test_qr_verify.py -v

test-worker:
	docker compose exec backend pytest tests/test_worker_entry.py -v

test-approval:
	docker compose exec backend pytest tests/test_approval.py -v

test-site-admin:
	docker compose exec backend pytest tests/test_site_admin.py -v

test-ops:
	docker compose exec backend pytest tests/test_ops.py -v

# =============================================================================
# 管理者セットアップ
# =============================================================================

# 使い方: make create-admin EMAIL=admin@example.com PASSWORD=Secret1234! NAME="管理者" ROLE=super_admin
create-admin:
	docker compose exec backend python scripts/create_admin.py \
		--email "$(EMAIL)" \
		--password "$(PASSWORD)" \
		--name "$(NAME)" \
		--role "$(ROLE)"

# =============================================================================
# フロントエンドテスト
# =============================================================================

## フロントエンドテストを実行（Docker コンテナ内）
test-fe:
	docker compose exec frontend npm test

## フロントエンドテストをウォッチモードで実行
test-fe-watch:
	docker compose exec frontend npm run test:watch

# =============================================================================
# コード品質（TODO: Day4 以降で lint/format を追加）
# =============================================================================

lint:
	docker compose exec backend python -m flake8 app tests --max-line-length=100 || true

format:
	docker compose exec backend python -m black app tests || true

# =============================================================================
# 本番環境操作 (Phase 8)
# =============================================================================

PROD_COMPOSE = docker compose -f docker-compose.yml -f docker-compose.prod.yml

prod-up:
	$(PROD_COMPOSE) up -d
	@echo ""
	@echo "本番環境が起動しました。"
	@echo "  API  : https://$${DOMAIN}/api/health"
	@echo "  Nginx: https://$${DOMAIN}"
	@echo ""
	$(PROD_COMPOSE) ps

prod-down:
	$(PROD_COMPOSE) down

prod-build:
	$(PROD_COMPOSE) build

prod-logs:
	$(PROD_COMPOSE) logs -f

prod-ps:
	$(PROD_COMPOSE) ps

# SSL 証明書の手動更新
ssl-renew:
	$(PROD_COMPOSE) run --rm certbot renew
	$(PROD_COMPOSE) exec nginx nginx -s reload
	@echo "SSL 証明書を更新しました"

# バックアップを今すぐ実行
backup:
	$(PROD_COMPOSE) exec backup sh /scripts/backup_postgres.sh
	$(PROD_COMPOSE) exec backup sh /scripts/backup_minio.sh
	@echo "バックアップ完了"

# バックアップ一覧表示
backup-list:
	$(PROD_COMPOSE) exec backup ls -lh /backups/postgres/

# 監査ログの確認（最新 50 件）
audit-logs:
	docker compose logs --tail=200 backend | grep '"event":' | tail -50
