"""
site_qr_codes テーブル

現場ごとに発行する QR コード。

セキュリティ設計:
  - token       : 64 文字のランダム文字列（secrets.token_urlsafe(32)）
  - pin_hash    : bcrypt ハッシュ化した PIN（pin_required=True の場合）
  - expires_at / is_active で有効期限・無効化を管理

ブルートフォース保護（migration 0002 で追加）:
  - failed_attempts  : PIN 失敗連続回数
  - blocked_until    : ブロック解除日時（NULL = ブロックなし）
  - max_attempts     : ブロックまでの最大失敗回数（デフォルト 3）
  - last_accessed_at : 最終アクセス日時（監査ログ用）

設計ポリシー:
  - QR コードは更新せず無効化（deactivate）で対応するため updated_at は持たない
  - BaseModel ではなく Base を直接継承する
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.admin_user import AdminUser
    from app.models.entry import WorkerSiteEntry
    from app.models.site import Site


class SiteQrCode(Base):
    """
    site_qr_codes は更新操作を行わず無効化で対応するため、
    updated_at は持たない。BaseModel ではなく Base を直接継承する。
    """

    __tablename__ = "site_qr_codes"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="UUID v4",
    )
    site_id: Mapped[str] = mapped_column(
        String(36), nullable=False, comment="現場 FK"
    )
    token: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="QR URL に埋め込むランダムトークン（64文字）",
    )
    pin_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="PIN の bcrypt ハッシュ（pin_required=True の場合のみ）",
    )
    pin_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="PIN 入力を要求するか"
    )
    label: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="管理用ラベル（例: 北ゲート用）"
    )
    qr_image_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="MinIO 上の QR 画像パス"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="有効フラグ"
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="有効期限（NULL = 無期限）",
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="発行した管理者 FK"
    )
    deactivated_by: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="無効化した管理者 FK"
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="無効化日時"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="発行日時",
    )

    # -------------------------------------------------------------------------
    # 使用制限・アナリティクスカラム（migration 0005 で追加）
    # -------------------------------------------------------------------------
    max_uses: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="最大使用回数（NULL = 無制限）",
    )
    use_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="QR 認証成功回数",
    )
    blocked_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="PIN ブロック発生回数（累積）",
    )

    # -------------------------------------------------------------------------
    # ブルートフォース保護カラム（migration 0002 で追加）
    # -------------------------------------------------------------------------
    failed_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="PIN 失敗連続回数",
    )
    blocked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="ブロック解除日時（NULL = ブロックなし）",
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        server_default="3",
        comment="ブロックまでの最大 PIN 失敗回数",
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最終アクセス日時（監査ログ用）",
    )

    # -------------------------------------------------------------------------
    # テーブル制約・インデックス
    # -------------------------------------------------------------------------
    __table_args__ = (
        UniqueConstraint("token", name="uq_qr_codes_token"),
        Index("idx_qr_codes_site", "site_id"),
        Index("idx_qr_codes_active", "is_active", "expires_at"),
        Index("idx_qr_codes_blocked", "blocked_until"),
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    site: Mapped["Site"] = relationship(
        "Site",
        back_populates="qr_codes",
        lazy="select",
        foreign_keys=[site_id],
    )
    creator: Mapped["AdminUser | None"] = relationship(
        "AdminUser",
        lazy="select",
        foreign_keys=[created_by],
    )
    entries: Mapped[list["WorkerSiteEntry"]] = relationship(
        "WorkerSiteEntry",
        back_populates="qr_code",
        lazy="select",
        foreign_keys="WorkerSiteEntry.qr_code_id",
    )

    def __repr__(self) -> str:
        return (
            f"<SiteQrCode id={self.id!r} token={self.token[:8]!r}... "
            f"active={self.is_active} attempts={self.failed_attempts}>"
        )
