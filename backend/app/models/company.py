"""
companies テーブル

管理側の会社情報マスター。
admin_users・sites の親テーブルとなる。
"""
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel

if TYPE_CHECKING:
    from app.models.admin_user import AdminUser
    from app.models.site import Site


class Company(BaseModel):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="会社名"
    )
    name_kana: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="会社名カナ"
    )
    postal_code: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="郵便番号"
    )
    address: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="住所"
    )
    phone: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="電話番号"
    )
    representative: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="代表者名"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="有効フラグ"
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    admin_users: Mapped[list["AdminUser"]] = relationship(
        "AdminUser",
        back_populates="company",
        lazy="select",
    )
    sites: Mapped[list["Site"]] = relationship(
        "Site",
        back_populates="company",
        lazy="select",
    )
