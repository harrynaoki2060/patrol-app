"""
approval_logs テーブル

承認・差戻し・取下げ操作の監査ログ。
「誰が・いつ・どの申請を・どう処理したか」を記録する。

設計方針:
  - UPDATE せず INSERT のみ（不変の監査証跡）
  - entry_id / actor_id / created_at にインデックス
  - FK 制約は ORM レイヤーのみ（TECH_DEBT.md §6 参照）
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.admin_user import AdminUser
    from app.models.entry import WorkerSiteEntry


# =============================================================================
# Enum 定義
# =============================================================================

class ApprovalAction(str, Enum):
    APPROVED  = "approved"   # 承認
    REJECTED  = "rejected"   # 差戻し
    WITHDRAWN = "withdrawn"  # 取下げ（作業員または管理者）


# =============================================================================
# モデル
# =============================================================================

class ApprovalLog(Base):
    __tablename__ = "approval_logs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="UUID v4",
    )

    # -------------------------------------------------------------------------
    # 外部キー（制約なし — TECH_DEBT.md §6）
    # -------------------------------------------------------------------------
    entry_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        comment="対象申請 FK (worker_site_entries.id)",
    )
    actor_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        comment="操作した管理者 FK (admin_users.id)",
    )

    # -------------------------------------------------------------------------
    # 操作情報
    # -------------------------------------------------------------------------
    action: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="操作種別: approved / rejected / withdrawn",
    )
    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="理由（差戻し時に必須。承認時はNULL可）",
    )
    request_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="X-Request-ID トレーシング用",
    )

    # -------------------------------------------------------------------------
    # タイムスタンプ（INSERT 時のみ設定、以後不変）
    # -------------------------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="操作日時",
    )

    # -------------------------------------------------------------------------
    # テーブル制約・インデックス
    # -------------------------------------------------------------------------
    __table_args__ = (
        CheckConstraint(
            "action IN ('approved', 'rejected', 'withdrawn')",
            name="ck_approval_logs_action",
        ),
        Index("idx_approval_logs_entry",         "entry_id"),
        Index("idx_approval_logs_actor",         "actor_id"),
        Index("idx_approval_logs_created",       "created_at"),
        Index("idx_approval_logs_entry_created", "entry_id", "created_at"),
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    entry: Mapped["WorkerSiteEntry"] = relationship(
        "WorkerSiteEntry",
        back_populates="approval_logs",
        lazy="select",
        foreign_keys=[entry_id],
    )
    actor: Mapped["AdminUser"] = relationship(
        "AdminUser",
        back_populates="approval_logs",
        lazy="select",
        foreign_keys=[actor_id],
    )

    def __repr__(self) -> str:
        return (
            f"<ApprovalLog id={self.id!r} "
            f"entry={self.entry_id!r} action={self.action!r}>"
        )
