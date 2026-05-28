"""
SQLAlchemy 非同期セッション設定

構成:
  - create_async_engine  : asyncpg ドライバで PostgreSQL 接続
  - async_sessionmaker   : AsyncSession ファクトリ
  - get_db               : FastAPI Depends で使う非同期ジェネレータ
  - check_db_connection  : ヘルスチェック用接続確認
"""
import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

# =============================================================================
# 非同期エンジン
# =============================================================================
engine = create_async_engine(
    settings.DATABASE_URL,
    # SQL ログ（DEBUG 時のみ出力）
    echo=settings.LOG_LEVEL.upper() == "DEBUG",
    # コネクションプール設定
    pool_size=5,          # 常時保持する接続数
    max_overflow=10,      # pool_size を超えて一時的に増やせる数
    pool_pre_ping=True,   # 使用前に接続が生きているか確認（切断後の自動復旧）
    pool_recycle=3600,    # 1時間ごとに接続を再生成（長時間接続切断対策）
    # asyncpg 接続タイムアウト
    connect_args={"timeout": 10},
)

# =============================================================================
# セッションファクトリ
# =============================================================================
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # commit 後もオブジェクト属性にアクセス可能にする
    autoflush=False,          # 明示的に flush するまで DB に送らない
    autocommit=False,
)


# =============================================================================
# FastAPI 依存性注入 (Depends で使用)
# =============================================================================
async def get_db() -> AsyncSession:  # type: ignore[return]
    """
    リクエストごとに AsyncSession を払い出す。
    例外発生時はロールバックして確実にクローズする。

    使い方:
        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except SQLAlchemyError:
            await session.rollback()
            raise
        finally:
            await session.close()


# =============================================================================
# ヘルスチェック用 DB 接続確認
# =============================================================================
async def check_db_connection() -> dict:
    """
    DB への接続と簡単なクエリを確認する。
    /api/health/full エンドポイントから呼ばれる。
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1 AS ping, version() AS ver"))
            row = result.mappings().one()
            if row["ping"] != 1:
                return {"status": "error", "error": "Unexpected result from SELECT 1"}
            return {"status": "ok", "version": row["ver"]}
    except Exception as e:
        logger.error("DB health check failed: %s", e)
        return {"status": "error", "error": str(e)}
