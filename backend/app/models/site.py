"""
sites テーブル

現場情報。
QR コード・入場申請の親テーブルとなる。
"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.admin_user import AdminUser
    from app.models.qr_code import SiteQrCode
    from app.models.entry import WorkerSiteEntry


class Site(BaseModel):
    __tablename__ = "sites"

    company_id: Mapped[str] = mapped_column(
        String(36), nullable=False, comment="所属会社 FK"
    )
    name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="現場名"
    )
    address: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="現場住所"
    )
    start_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="工期開始日"
    )
    end_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="工期終了日"
    )
    supervisor_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="担当監督 FK"
    )
    # 入場フォーム設定
    require_health_check: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="健康診断を必須とするか"
    )
    require_insurance: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="保険情報を必須とするか"
    )
    custom_notice: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="QR ランディングページに表示する注意事項"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="有効フラグ"
    )

    # -------------------------------------------------------------------------
    # テーブル制約・インデックス
    # -------------------------------------------------------------------------
    __table_args__ = (
        Index("idx_sites_company", "company_id"),
        Index("idx_sites_supervisor", "supervisor_id"),
        Index("idx_sites_active", "is_active", "end_date"),
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="ck_sites_date_range",
        ),
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    company: Mapped["Company"] = relationship(
        "Company",
        back_populates="sites",
        lazy="select",
        foreign_keys=[company_id],
    )
    supervisor: Mapped["AdminUser | None"] = relationship(
        "AdminUser",
        back_populates="supervised_sites",
        lazy="select",
        foreign_keys=[supervisor_id],
    )
    qr_codes: Mapped[list["SiteQrCode"]] = relationship(
        "SiteQrCode",
        back_populates="site",
        lazy="select",
        foreign_keys="SiteQrCode.site_id",
    )
    entries: Mapped[list["WorkerSiteEntry"]] = relationship(
        "WorkerSiteEntry",
        back_populates="site",
        lazy="select",
        foreign_keys="WorkerSiteEntry.site_id",
    )
