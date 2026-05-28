"""
admin_users テーブル

管理者・現場監督アカウント。
ロールによって操作権限が異なる。
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel

if TYPE_CHECKING:
    from app.models.approval_log import ApprovalLog
    from app.models.company import Company
    from app.models.site import Site
    from app.models.entry import WorkerSiteEntry


# =============================================================================
# Enum 定義
# =============================================================================
class AdminRole(str, Enum):
    SUPER_ADMIN = "super_admin"  # 全権限
    ADMIN = "admin"              # 現場管理・QR発行
    SUPERVISOR = "supervisor"    # 申請確認・承認


# =============================================================================
# モデル
# =============================================================================
class AdminUser(BaseModel):
    __tablename__ = "admin_users"

    company_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        comment="所属会社 FK",
    )
    email: Mapped[str] = mapped_column(
        String(254),
        nullable=False,
        comment="メールアドレス（ログイン ID）",
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="bcrypt ハッシュ化済みパスワード",
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="表示名"
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=AdminRole.SUPERVISOR.value,
        comment="権限ロール",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="有効フラグ"
    )
    # ログイン失敗ロック
    login_failure_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="ログイン失敗連続回数",
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="アカウントロック解除日時",
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最終ログイン日時",
    )

    # -------------------------------------------------------------------------
    # テーブル制約・インデックス
    # -------------------------------------------------------------------------
    __table_args__ = (
        UniqueConstraint("email", name="uq_admin_users_email"),
        Index("idx_admin_users_company", "company_id"),
        CheckConstraint(
            "role IN ('super_admin', 'admin', 'supervisor')",
            name="ck_admin_users_role",
        ),
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    company: Mapped["Company"] = relationship(
        "Company",
        back_populates="admin_users",
        lazy="select",
        foreign_keys=[company_id],
    )
    supervised_sites: Mapped[list["Site"]] = relationship(
        "Site",
        back_populates="supervisor",
        lazy="select",
        foreign_keys="Site.supervisor_id",
    )
    approved_entries: Mapped[list["WorkerSiteEntry"]] = relationship(
        "WorkerSiteEntry",
        back_populates="approver",
        lazy="select",
        foreign_keys="WorkerSiteEntry.approved_by",
    )
    approval_logs: Mapped[list["ApprovalLog"]] = relationship(
        "ApprovalLog",
        back_populates="actor",
        lazy="select",
        foreign_keys="ApprovalLog.actor_id",
    )
