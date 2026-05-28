"""
pytest フィクスチャ定義

テスト戦略:
  - 各テストはネストされたトランザクション（SAVEPOINT）で分離する
  - テスト終了時に外側のトランザクションを ROLLBACK → DB は常にクリーンな状態
  - Alembic は実行しない。テスト前に Base.metadata.create_all() で全テーブルを作成する
  - PostgreSQL に実際に接続するため `docker compose exec backend pytest` で実行する

実行方法:
    docker compose exec backend pytest
    docker compose exec backend pytest -v tests/test_repositories.py
    make test / make test-v / make test-repo
"""
import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    create_async_engine,
)

from app.db.base import Base

# =============================================================================
# テスト用 DB URL
# =============================================================================
TEST_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://app:changeme_dev_password@postgres:5432/entry_db",
)


# =============================================================================
# セッションスコープエンジン（テスト全体で 1 つ）
# =============================================================================
@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """
    テストセッション全体で使うエンジン。
    セッション開始時に全テーブルを DROP → CREATE し、
    終了時に DROP する。
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_size=2,
        max_overflow=0,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


# =============================================================================
# テスト関数スコープ: 接続ごとにトランザクションを開始し ROLLBACK で戻す
# =============================================================================
@pytest_asyncio.fixture
async def db_connection(test_engine) -> AsyncGenerator[AsyncConnection, None]:
    """
    テストごとに接続を取得してトランザクション開始。
    テスト終了後に無条件 ROLLBACK。
    """
    async with test_engine.connect() as conn:
        await conn.begin()
        yield conn
        await conn.rollback()


@pytest_asyncio.fixture
async def db_session(db_connection: AsyncConnection) -> AsyncGenerator[AsyncSession, None]:
    """
    テスト用 AsyncSession。
    db_connection のトランザクション上に SAVEPOINT を発行して分離する。

    テスト内で session.rollback() を呼んでも外側のトランザクションには影響しない。
    """
    session = AsyncSession(
        bind=db_connection,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    # SAVEPOINT を発行（テスト内 rollback をこの点まで巻き戻す）
    nested = await db_connection.begin_nested()
    try:
        yield session
    finally:
        # SAVEPOINT までロールバック（テストが commit していても戻る）
        await nested.rollback()
        await session.close()
