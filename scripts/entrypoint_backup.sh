#!/bin/sh
# =============================================================================
# バックアップコンテナ エントリポイント
# 起動時に即時バックアップを実行し、以降は cron で毎日午前 2 時に実行する
# =============================================================================
set -eu

BACKUP_SCRIPT="/scripts/backup_postgres.sh"
MINIO_SCRIPT="/scripts/backup_minio.sh"

# スクリプトのフォールバック (Dockerfile COPY パスを使用)
if [ ! -f "${BACKUP_SCRIPT}" ]; then
    BACKUP_SCRIPT="/backup_postgres.sh"
fi
if [ ! -f "${MINIO_SCRIPT}" ]; then
    MINIO_SCRIPT="/backup_minio.sh"
fi

log() {
    echo "[$(date -Iseconds)] $*"
}

# ---------------------------------------------------------------------------
# 起動時チェック: postgres が応答するまで待機
# ---------------------------------------------------------------------------
log "Waiting for PostgreSQL to be ready..."
MAX_RETRIES=30
RETRY=0
until PGPASSWORD="${DB_PASSWORD}" pg_isready -h postgres -U app -d entry_db -q; do
    RETRY=$((RETRY + 1))
    if [ "${RETRY}" -ge "${MAX_RETRIES}" ]; then
        log "ERROR: PostgreSQL did not become ready after ${MAX_RETRIES} retries"
        exit 1
    fi
    log "PostgreSQL not ready yet (attempt ${RETRY}/${MAX_RETRIES})..."
    sleep 5
done
log "PostgreSQL is ready."

# ---------------------------------------------------------------------------
# 起動時に即時バックアップ実行
# ---------------------------------------------------------------------------
log "Running initial backup on startup..."
sh "${BACKUP_SCRIPT}" || log "WARNING: Initial PostgreSQL backup failed"
sh "${MINIO_SCRIPT}"  || log "WARNING: Initial MinIO backup failed"
log "Initial backup complete."

# ---------------------------------------------------------------------------
# cron 設定: 毎日午前 2 時 (UTC) に実行
# ---------------------------------------------------------------------------
CRON_JOB="0 2 * * * sh ${BACKUP_SCRIPT} && sh ${MINIO_SCRIPT}"
echo "${CRON_JOB}" | crontab -
log "Cron job registered: ${CRON_JOB}"

# ---------------------------------------------------------------------------
# crond をフォアグラウンドで起動 (コンテナが終了しないよう)
# -d 8 = debug level (エラーのみ出力)
# -f   = フォアグラウンド実行
# ---------------------------------------------------------------------------
log "Starting crond in foreground..."
exec crond -f -d 8
