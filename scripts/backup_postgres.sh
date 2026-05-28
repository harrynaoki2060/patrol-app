#!/bin/sh
# =============================================================================
# PostgreSQL バックアップスクリプト
#
# 機能:
#   - pg_dump で entry_db をプレーン SQL 形式でダンプ → gzip 圧縮
#   - BACKUP_RETENTION_DAYS 日以上古いバックアップを自動削除
#   - バックアップサイズと所要時間をログに出力
#
# 環境変数:
#   DB_PASSWORD           — PostgreSQL パスワード (必須)
#   BACKUP_DIR            — バックアップ保存先ディレクトリ (default: /backups/postgres)
#   BACKUP_RETENTION_DAYS — 保存期間（日数） (default: 30)
#
# 使い方:
#   docker compose exec backup sh /scripts/backup_postgres.sh
# =============================================================================
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}/postgres"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="entry_db_${TIMESTAMP}.sql.gz"
FILEPATH="${BACKUP_DIR}/${FILENAME}"

log() {
    echo "[$(date -Iseconds)] $*"
}

mkdir -p "${BACKUP_DIR}"

log "Starting PostgreSQL backup: ${FILENAME}"
START_TIME=$(date +%s)

# pg_dump を実行して gzip で圧縮
PGPASSWORD="${DB_PASSWORD}" pg_dump \
    -h postgres \
    -U app \
    -d entry_db \
    --no-password \
    --format=plain \
    --no-owner \
    --no-acl \
    | gzip > "${FILEPATH}"

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
SIZE=$(du -sh "${FILEPATH}" | cut -f1)

log "Backup complete: ${FILENAME} (${SIZE}, ${ELAPSED}s)"

# ---------------------------------------------------------------------------
# 古いバックアップを削除
# ---------------------------------------------------------------------------
DELETED=0
for OLD_FILE in $(find "${BACKUP_DIR}" -name "entry_db_*.sql.gz" -mtime "+${RETENTION_DAYS}" 2>/dev/null); do
    rm -f "${OLD_FILE}"
    DELETED=$((DELETED + 1))
    log "Deleted old backup: $(basename "${OLD_FILE}")"
done

if [ "${DELETED}" -gt 0 ]; then
    log "Pruned ${DELETED} old backup(s) (retention: ${RETENTION_DAYS} days)"
fi

# ---------------------------------------------------------------------------
# バックアップ一覧を出力
# ---------------------------------------------------------------------------
BACKUP_COUNT=$(find "${BACKUP_DIR}" -name "entry_db_*.sql.gz" | wc -l | tr -d ' ')
log "Current backup count: ${BACKUP_COUNT} file(s) in ${BACKUP_DIR}"
