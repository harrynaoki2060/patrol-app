"""
SQLAlchemy 2.x 宣言的ベースクラス

設計方針:
  - UUID は Python 側 (uuid.uuid4) で生成 → DB 関数に依存しない
  - TIMESTAMPTZ: DateTime(timezone=True) で PostgreSQL の TIMESTAMPTZ にマップ
  - server_default=func.now() → INSERT 時に DB が NOW() を設定
  - onupdate=func.now()       → ORM UPDATE 時に Python 側で NOW() を設定
  - __abstract__ = True       → このクラス自体はテーブルを作らない
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """全 SQLAlchemy モデルの共通ベース"""
    pass


class BaseModel(Base):
    """
    全テーブル共通カラムを持つ抽象ベースモデル

    カラム:
        id          : UUID（Primary Key）アプリ側で生成
        created_at  : レコード作成日時（INSERT 時に DB が自動設定）
        updated_at  : レコード更新日時（UPDATE 時に ORM が自動設定）
    """
    __abstract__ = True

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="UUID v4（アプリ側で生成）",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="レコード作成日時",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="レコード最終更新日時",
    )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id!r}>"
