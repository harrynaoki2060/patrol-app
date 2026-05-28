"""
ヘルスチェック API

GET /api/health       → シンプルな生死確認（nginx / 監視から呼ぶ）
GET /api/health/full  → DB・Redis・MinIO の実接続確認（タイムアウト付き）
"""
import asyncio
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter
from minio import Minio

from app.core.config import settings
from app.db.session import check_db_connection

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# タイムアウト秒数（外部サービス確認の上限）
_HEALTH_TIMEOUT = 5.0


@router.get("/health")
async def health_check() -> dict:
    """
    サービスの生死確認。
    nginx のヘルスチェック・監視ツールから呼ばれる最軽量エンドポイント。
    DB・外部サービスへの問い合わせは行わない。
    """
    return {
        "status": "ok",
        "service": "entry-management-api",
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/full")
async def full_health_check() -> dict:
    """
    全依存サービスへの接続確認。
    各チェックに _HEALTH_TIMEOUT 秒のタイムアウトを設定する。
    """
    checks: dict[str, dict] = {}
    overall_ok = True

    # --- Database ---
    try:
        db_result = await asyncio.wait_for(check_db_connection(), timeout=_HEALTH_TIMEOUT)
    except asyncio.TimeoutError:
        db_result = {"status": "error", "error": f"timeout after {_HEALTH_TIMEOUT}s"}
    checks["database"] = db_result
    if db_result["status"] != "ok":
        overall_ok = False

    # --- Redis ---
    try:
        redis_result = await asyncio.wait_for(_check_redis(), timeout=_HEALTH_TIMEOUT)
    except asyncio.TimeoutError:
        redis_result = {"status": "error", "error": f"timeout after {_HEALTH_TIMEOUT}s"}
    checks["redis"] = redis_result
    if redis_result["status"] != "ok":
        overall_ok = False

    # --- MinIO (sync SDK → asyncio.to_thread でスレッドプール実行) ---
    try:
        minio_result = await asyncio.wait_for(
            asyncio.to_thread(_check_minio), timeout=_HEALTH_TIMEOUT
        )
    except asyncio.TimeoutError:
        minio_result = {"status": "error", "error": f"timeout after {_HEALTH_TIMEOUT}s"}
    checks["minio"] = minio_result
    if minio_result["status"] != "ok":
        overall_ok = False

    return {
        "status": "ok" if overall_ok else "degraded",
        "service": "entry-management-api",
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


async def _check_redis() -> dict:
    """Redis への PING 確認"""
    try:
        client = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
        await client.ping()
        await client.aclose()
        return {"status": "ok"}
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        return {"status": "error", "error": str(exc)}


def _check_minio() -> dict:
    """MinIO へのバケット存在確認（同期 SDK のためスレッドプールで実行）"""
    try:
        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_USE_SSL,
        )
        exists = client.bucket_exists(settings.MINIO_BUCKET)
        return {"status": "ok", "bucket_exists": exists}
    except Exception as exc:
        logger.warning("MinIO health check failed: %s", exc)
        return {"status": "error", "error": str(exc)}
