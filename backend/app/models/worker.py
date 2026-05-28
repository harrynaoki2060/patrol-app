"""
workers テーブル

作業員マスター。
電話番号を照合キーとして、複数現場への入場申請を再利用する。

設計ポイント:
  - phone_normalized : ハイフン除去・正規化済み（検索・照合用）
  - consent_agreed_at: 個人情報同意日時（同意なし = NULL は申請不可）
  - first_registered_at / last_updated_at : created_at/updated_at の代わりに
    業務的な意味を持つ名前を使用
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
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.entry import WorkerSiteEntry


# =============================================================================
# Enum 定義
# =============================================================================
class WorkerType(str, Enum):
    COMPANY_EMPLOYEE = "company_employee"  # 協力会社社員
    SOLE_PROPRIETOR = "sole_proprietor"    # 一人親方


class BloodType(str, Enum):
    A = "A"
    B = "B"
    O = "O"
    AB = "AB"
    UNKNOWN = "unknown"


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


# =============================================================================
# モデル
# =============================================================================
class Worker(Base):
    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="UUID v4",
    )

    # -------------------------------------------------------------------------
    # 識別・照合キー
    # -------------------------------------------------------------------------
    phone: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="電話番号（表示用）"
    )
    phone_normalized: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="電話番号（正規化済・ハイフン除去 / 半角数字のみ）",
    )

    # -------------------------------------------------------------------------
    # 基本情報
    # -------------------------------------------------------------------------
    last_name: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="姓"
    )
    first_name: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="名"
    )
    last_name_kana: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="姓カナ"
    )
    first_name_kana: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="名カナ"
    )
    birth_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="生年月日（draft 段階は NULL 可。submit 時に必須）"
    )
    gender: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="性別"
    )
    blood_type: Mapped[str | None] = mapped_column(
        String(10), nullable=True, default="unknown", comment="血液型"
    )

    # -------------------------------------------------------------------------
    # 連絡先
    # -------------------------------------------------------------------------
    emergency_contact: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="緊急連絡先電話番号"
    )
    emergency_contact_name: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="緊急連絡先氏名"
    )
    emergency_contact_relation: Mapped[str | None] = mapped_column(
        String(30), nullable=True, comment="緊急連絡先続柄"
    )
    postal_code: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="郵便番号"
    )
    address: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="住所"
    )

    # -------------------------------------------------------------------------
    # 所属・職種
    # -------------------------------------------------------------------------
    worker_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="区分（協力会社社員/一人親方）"
    )
    affiliation_company: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="所属会社名（一人親方の場合 NULL 可）"
    )
    job_title: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="職種・工種（draft 段階は NULL 可。submit 時に必須）"
    )
    experience_years: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="経験年数"
    )

    # -------------------------------------------------------------------------
    # 保険
    # -------------------------------------------------------------------------
    insurance_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="保険の種類"
    )
    insurance_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="保険番号"
    )

    # -------------------------------------------------------------------------
    # 個人情報同意
    # -------------------------------------------------------------------------
    consent_agreed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="個人情報取り扱い同意日時",
    )

    # -------------------------------------------------------------------------
    # 管理
    # -------------------------------------------------------------------------
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="有効フラグ"
    )
    first_registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="初回登録日時",
    )
    last_updated_at: Mapped[datetime] = mapped_column(
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
        UniqueConstraint("phone_normalized", name="uq_workers_phone"),
        Index("idx_workers_name", "last_name", "first_name"),
        Index("idx_workers_company", "affiliation_company"),
        CheckConstraint(
            "gender IS NULL OR gender IN ('male','female','other','prefer_not_to_say')",
            name="ck_workers_gender",
        ),
        CheckConstraint(
            "blood_type IS NULL OR blood_type IN ('A','B','O','AB','unknown')",
            name="ck_workers_blood_type",
        ),
        CheckConstraint(
            "worker_type IN ('company_employee','sole_proprietor')",
            name="ck_workers_type",
        ),
        CheckConstraint(
            "experience_years IS NULL OR experience_years >= 0",
            name="ck_workers_experience",
        ),
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    entries: Mapped[list["WorkerSiteEntry"]] = relationship(
        "WorkerSiteEntry",
        back_populates="worker",
        lazy="select",
        foreign_keys="WorkerSiteEntry.worker_id",
    )

    def __repr__(self) -> str:
        return (
            f"<Worker id={self.id!r} "
            f"name={self.last_name}{self.first_name!r}>"
        )
