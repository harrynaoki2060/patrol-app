"""
worker_site_entries テーブル

作業員 × 現場の入場申請レコード。
1 作業員が複数現場に申請できる。同一現場への有効な重複申請はブロック。

ステータス遷移:
  draft → pending → approved
                 → rejected → (再申請で新規 draft)
  pending → withdrawn（取下げ）

draft フロー（migration 0003 で追加）:
  draft_started_at : draft 生成日時
  last_saved_at    : 最終自動保存日時（PATCH ごとに更新）
  submitted_at     : NULL → pending 遷移時に設定
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.admin_user import AdminUser
    from app.models.approval_log import ApprovalLog
    from app.models.qr_code import SiteQrCode
    from app.models.site import Site
    from app.models.worker import Worker


# =============================================================================
# Enum 定義
# =============================================================================
class EntryStatus(str, Enum):
    DRAFT = "draft"          # 一時保存（フォーム途中離脱）
    PENDING = "pending"      # 申請中（承認待ち）
    APPROVED = "approved"    # 承認済み
    REJECTED = "rejected"    # 差戻し
    WITHDRAWN = "withdrawn"  # 取下げ


# =============================================================================
# モデル
# =============================================================================
class WorkerSiteEntry(Base):
    __tablename__ = "worker_site_entries"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="UUID v4",
    )

    # -------------------------------------------------------------------------
    # 外部キー
    # -------------------------------------------------------------------------
    worker_id: Mapped[str] = mapped_column(
        String(36), nullable=False, comment="作業員 FK"
    )
    site_id: Mapped[str] = mapped_column(
        String(36), nullable=False, comment="現場 FK"
    )
    qr_code_id: Mapped[str] = mapped_column(
        String(36), nullable=False, comment="使用した QR コード FK"
    )

    # -------------------------------------------------------------------------
    # 申請情報
    # -------------------------------------------------------------------------
    receipt_number: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        comment="受付番号（8桁英数字大文字）",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=EntryStatus.DRAFT.value,
        comment="申請ステータス（draft から始まり pending → approved へ遷移）",
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="差戻し理由"
    )

    # -------------------------------------------------------------------------
    # 入場情報
    # -------------------------------------------------------------------------
    planned_entry_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="入場予定日"
    )
    has_health_check: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="健康診断受診済み"
    )
    health_check_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="健康診断実施日"
    )

    # -------------------------------------------------------------------------
    # 承認情報
    # -------------------------------------------------------------------------
    approved_by: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="承認した管理者 FK"
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="承認日時"
    )

    # -------------------------------------------------------------------------
    # 送信元情報（個人情報保護）
    # -------------------------------------------------------------------------
    submit_ip_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="送信元 IP の SHA256 ハッシュ（原文は保持しない）",
    )

    # -------------------------------------------------------------------------
    # タイムスタンプ（migration 0003 で submitted_at を nullable 化）
    # -------------------------------------------------------------------------
    draft_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="draft 生成日時（migration 0003 で追加）",
    )
    last_saved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最終自動保存日時（PATCH ごとに更新）",
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="申請日時（pending 遷移時に設定。draft 段階は NULL）",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="最終更新日時",
    )

    # -------------------------------------------------------------------------
    # テーブル制約・インデックス
    # -------------------------------------------------------------------------
    __table_args__ = (
        # 受付番号はシステム全体でユニーク
        UniqueConstraint("receipt_number", name="uq_entries_receipt"),
        # 同一作業員が同一現場に有効な申請を重複できない
        # draft/pending/approved の状態では同一 worker × site の重複を防ぐ
        # NOTE: PostgreSQL 部分インデックス。SQLite では非対応。
        Index(
            "uq_entries_worker_site_active",
            "worker_id",
            "site_id",
            unique=True,
            postgresql_where=text("status IN ('draft', 'pending', 'approved')"),
        ),
        # 検索用インデックス
        Index("idx_entries_site", "site_id"),
        Index("idx_entries_worker", "worker_id"),
        Index("idx_entries_status", "status"),
        Index("idx_entries_submitted", "submitted_at"),
        Index("idx_entries_site_status", "site_id", "status"),
        Index("idx_entries_draft_saved", "last_saved_at",
              postgresql_where=text("status = 'draft'")),
        CheckConstraint(
            "status IN ('draft','pending','approved','rejected','withdrawn')",
            name="ck_entries_status",
        ),
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    worker: Mapped["Worker"] = relationship(
        "Worker",
        back_populates="entries",
        lazy="select",
        foreign_keys=[worker_id],
    )
    site: Mapped["Site"] = relationship(
        "Site",
        back_populates="entries",
        lazy="select",
        foreign_keys=[site_id],
    )
    qr_code: Mapped["SiteQrCode"] = relationship(
        "SiteQrCode",
        back_populates="entries",
        lazy="select",
        foreign_keys=[qr_code_id],
    )
    approver: Mapped["AdminUser | None"] = relationship(
        "AdminUser",
        back_populates="approved_entries",
        lazy="select",
        foreign_keys=[approved_by],
    )
    approval_logs: Mapped[list["ApprovalLog"]] = relationship(
        "ApprovalLog",
        back_populates="entry",
        lazy="select",
        foreign_keys="ApprovalLog.entry_id",
        order_by="ApprovalLog.created_at",
    )

    def __repr__(self) -> str:
        return (
            f"<WorkerSiteEntry id={self.id!r} "
            f"receipt={self.receipt_number!r} status={self.status!r}>"
        )
