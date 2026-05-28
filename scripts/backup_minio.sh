#!/bin/sh
# =============================================================================
# MinIO バックアップスクリプト
#
# 機能:
#   - mc mirror で MinIO バケットをローカルディレクトリにミラーリング
#   - BACKUP_RETENTION_DAYS 日以上古いバックアップディレクトリを自動削除
#
# 環境変数:
#   MINIO_ACCESS_KEY      — MinIO アクセスキー (必須)
#   MINIO_SECRET_KEY      — MinIO シークレットキー (必須)
#   MINIO_BUCKET          — バケット名 (default: entry-documents)
#   BACKUP_DIR            — バックアップ保存先 (default: /backups/minio)
#   BACKUP_RETENTION_DAYS — 保存期間（日数） (default: 30)
#
# 使い方:
#   docker compose exec backup sh /scripts/backup_minio.sh
# =============================================================================
set -eu

BACKUP_BASE="${BACKUP_DIR:-/backups}/minio"
MINIO_BUCKET="${MINIO_BUCKET:-entry-documents}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TARGET="${BACKUP_BASE}/${TIMESTAMP}"

log() {
    echo "[$(date -Iseconds)] $*"
}

mkdir -p "${TARGET}"

# ---------------------------------------------------------------------------
# MinIO alias を設定
# ---------------------------------------------------------------------------
mc alias set local http://minio:9000 "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}" --quiet

# ---------------------------------------------------------------------------
# バケットの存在確認
# ---------------------------------------------------------------------------
if ! mc ls "local/${MINIO_BUCKET}" >/dev/null 2>&1; then
    log "WARNING: MinIO bucket '${MINIO_BUCKET}' does not exist or is empty. Skipping."
    rmdir "${TARGET}" 2>/dev/null || true
    exit 0
fi

log "Starting MinIO backup: ${MINIO_BUCKET} → ${TARGET}"
START_TIME=$(date +%s)

# ミラーリング実行
mc mirror --quiet "local/${MINIO_BUCKET}" "${TARGET}"

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
FILE_COUNT=$(find "${TARGET}" -type f | wc -l | tr -d ' ')
SIZE=$(du -sh "${TARGET}" 2>/dev/null | cut -f1)

log "MinIO backup complete: ${FILE_COUNT} file(s), ${SIZE:-0B}, ${ELAPSED}s"

# ---------------------------------------------------------------------------
# 古いバックアップディレクトリを削除
# ---------------------------------------------------------------------------
DELETED=0
for OLD_DIR in $(find "${BACKUP_BASE}" -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" 2>/dev/null); do
    if [ "${OLD_DIR}" = "${BACKUP_BASE}" ]; then
        continue
    fi
    rm -rf "${OLD_DIR}"
    DELETED=$((DELETED + 1))
    log "Deleted old MinIO backup: $(basename "${OLD_DIR}")"
done

if [ "${DELETED}" -gt 0 ]; then
    log "Pruned ${DELETED} old MinIO backup(s) (retention: ${RETENTION_DAYS} days)"
fi
