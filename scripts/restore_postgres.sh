#!/bin/sh
# =============================================================================
# PostgreSQL リストアスクリプト
#
# 機能:
#   - 指定した .sql.gz バックアップファイルを entry_db にリストア
#   - 実行前に確認プロンプトを表示（--force オプションでスキップ可能）
#
# 環境変数:
#   DB_PASSWORD — PostgreSQL パスワード (必須)
#
# 使い方:
#   # Docker コンテナ内から実行
#   docker compose exec backup sh /scripts/restore_postgres.sh /backups/postgres/entry_db_20260521_020000.sql.gz
#
#   # ホストから直接実行（バックアップ volume をマウントした場合）
#   docker compose run --rm backup sh /scripts/restore_postgres.sh /backups/postgres/FILENAME.sql.gz
#
#   # 確認スキップ（CI 等）
#   docker compose run --rm backup sh /scripts/restore_postgres.sh FILENAME.sql.gz --force
# =============================================================================
set -eu

# ---------------------------------------------------------------------------
# 引数チェック
# ---------------------------------------------------------------------------
if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup_file.sql.gz> [--force]"
    echo ""
    echo "  <backup_file.sql.gz>  リストアするバックアップファイルのパス"
    echo "  --force               確認プロンプトをスキップ"
    echo ""
    echo "利用可能なバックアップ:"
    ls -lh "${BACKUP_DIR:-/backups}/postgres/"*.sql.gz 2>/dev/null || echo "  (バックアップなし)"
    exit 1
fi

BACKUP_FILE="$1"
FORCE="${2:-}"

log() {
    echo "[$(date -Iseconds)] $*"
}

# ---------------------------------------------------------------------------
# ファイル存在チェック
# ---------------------------------------------------------------------------
if [ ! -f "${BACKUP_FILE}" ]; then
    echo "ERROR: バックアップファイルが見つかりません: ${BACKUP_FILE}"
    exit 1
fi

FILE_SIZE=$(du -sh "${BACKUP_FILE}" | cut -f1)
log "Restore target: ${BACKUP_FILE} (${FILE_SIZE})"

# ---------------------------------------------------------------------------
# 確認プロンプト
# ---------------------------------------------------------------------------
if [ "${FORCE}" != "--force" ]; then
    echo ""
    echo "=========================================================="
    echo "  警告: この操作は既存のデータを上書きします！"
    echo "  対象DB: entry_db on postgres:5432"
    echo "  バックアップ: ${BACKUP_FILE}"
    echo "=========================================================="
    printf "本当に実行しますか？ [y/N] "
    read -r CONFIRM
    if [ "${CONFIRM}" != "y" ] && [ "${CONFIRM}" != "Y" ]; then
        echo "リストアをキャンセルしました。"
        exit 0
    fi
fi

# ---------------------------------------------------------------------------
# リストア実行
# ---------------------------------------------------------------------------
log "Starting restore from: $(basename "${BACKUP_FILE}")"
START_TIME=$(date +%s)

# 既存の接続を切断してからリストア
PGPASSWORD="${DB_PASSWORD}" psql \
    -h postgres \
    -U app \
    -d postgres \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'entry_db' AND pid <> pg_backend_pid();" \
    -q 2>/dev/null || true

# バックアップをリストア（gzip 解凍 + psql）
gunzip -c "${BACKUP_FILE}" | PGPASSWORD="${DB_PASSWORD}" psql \
    -h postgres \
    -U app \
    -d entry_db \
    -v ON_ERROR_STOP=1

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

log "Restore complete: ${ELAPSED}s"
log "Please run 'alembic current' to verify migration state."
