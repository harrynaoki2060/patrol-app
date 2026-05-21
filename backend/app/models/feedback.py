"""
ux_feedback テーブル

現場スタッフからの UX フィードバック。
「朝の現場で止まらない」ための改善データ収集用。

設計ポイント:
  - reporter_id は NULL 可（匿名フィードバックも受け付ける）
  - site_id は NULL 可（現場を特定しないフィードバックも可）
  - category は固定値: input_hard / poor_connection / unclear / other
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UxFeedback(Base):
    __tablename__ = "ux_feedback"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="UUID v4",
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="カテゴリ（input_hard / poor_connection / unclear / other）",
    )
    detail: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="詳細コメント（任意・最大 500 文字）",
    )
    reporter_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="報告した管理ユーザー ID（NULL = 匿名）",
    )
    site_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="関連する現場 ID（任意）",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="フィードバック送信日時",
    )

    __table_args__ = (
        Index("idx_ux_feedback_category", "category"),
        Index("idx_ux_feedback_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<UxFeedback id={self.id!r} "
            f"category={self.category!r}>"
        )
