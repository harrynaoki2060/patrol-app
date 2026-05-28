"""
Alembic 非同期マイグレーション環境。

asyncpg / SQLAlchemy 2.x async エンジンを使用するため、
run_migrations_online を async で実装する。

実行方法（コンテナ内）:
    alembic upgrade head       # 最新へ
    alembic downgrade base     # 全テーブル削除
    alembic current            # 現在のリビジョン確認
    alembic history            # 履歴確認
    alembic revision --autogenerate -m "msg"  # 差分生成
"""
import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

# alembic コマンドはプロジェクトの /app ディレクトリから実行されることを想定
# sys.path に追加することで `from app.xxx import ...` が解決できる
_here = Path(__file__).resolve().parent.parent  # backend/ ディレクトリ
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

# alembic.ini のログ設定を適用
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 全モデルを import して autogenerate に検出させる
from app.db.base import Base
import app.models  # noqa: F401 — side effect import (全モデル登録)

target_metadata = Base.metadata

# 環境変数から DATABASE_URL を取得（asyncpg ドライバーを明示）
_db_url = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://app:changeme_dev_password@postgres:5432/entry_db",
)
config.set_main_option("sqlalchemy.url", _db_url)


def run_migrations_offline() -> None:
    """オフラインモード: SQL スクリプトをファイル出力する"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """オンラインモード: 実 DB に接続してマイグレーション実行"""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
