"""
トークンストア — Redis ベースのリフレッシュトークン失効管理

リフレッシュトークンの jti (JWT ID) を Redis に登録することで
以下のセキュリティ機能を実現する:

  - トークンローテーション: リフレッシュ成功後に旧 jti を失効させる
  - ログアウト: 任意のタイミングで refresh token を即時無効化
  - トークン再利用検出: 失効済み jti での再認証試行を検知

Redis キー設計:
  revoked:rt:{jti}   — 失効した refresh token jti
                       TTL = トークンの残り有効期限（秒）

可用性方針:
  Redis が利用不可の場合はトークンを「有効」として扱う（可用性優先）。
  ただし WARN ログを出力してアラートを発生させる。
  セキュリティと可用性のトレードオフとして、この設計を選択。
  Redis が完全に応答不能な状況は滅多になく、その間のトークン再利用リスクは低い。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "revoked:rt:"
_REDIS: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    """
    Redis クライアントシングルトンを返す（遅延初期化）。

    接続エラーは各操作内で捕捉する。
    タイムアウトを 2 秒に設定してレスポンスタイムを保護。
    """
    global _REDIS
    if _REDIS is None:
        _REDIS = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            health_check_interval=30,
        )
    return _REDIS


async def revoke_token(jti: str, exp: int) -> None:
    """
    リフレッシュトークンの jti を失効リストに追加する。

    Args:
        jti: JWT ID（トークンの jti クレーム）
        exp: 有効期限（Unix timestamp）

    TTL は exp から現在時刻までの残り秒数。
    すでに期限切れの jti は Redis に保存しない（無意味なため）。
    """
    now = int(datetime.now(timezone.utc).timestamp())
    ttl = exp - now
    if ttl <= 0:
        return  # 既に期限切れ: Redis に保存しても即時 evict されるだけ

    key = f"{_KEY_PREFIX}{jti}"
    try:
        r = _get_redis()
        await r.setex(key, ttl, "1")
        logger.debug("Refresh token revoked: jti=%s ttl=%ds", jti, ttl)
    except Exception as e:  # noqa: BLE001
        logger.warning("Redis revoke_token failed (jti=%.8s): %s", jti, e)


async def is_revoked(jti: str) -> bool:
    """
    jti が失効リストに存在するか確認する。

    Returns:
        True: 失効済み（このトークンは拒否すべき）
        False: 有効 or Redis エラー（可用性優先のため有効として扱う）
    """
    if not jti:
        return False

    key = f"{_KEY_PREFIX}{jti}"
    try:
        r = _get_redis()
        result = await r.get(key)
        return result is not None
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Redis is_revoked check failed (jti=%.8s): %s — treating as valid",
            jti, e,
        )
        return False  # 可用性優先: Redis 障害時はトークンを有効として扱う


async def close() -> None:
    """アプリケーション終了時に Redis 接続を閉じる"""
    global _REDIS
    if _REDIS is not None:
        try:
            await _REDIS.aclose()
        except Exception as e:  # noqa: BLE001
            logger.warning("Redis close error: %s", e)
        finally:
            _REDIS = None
