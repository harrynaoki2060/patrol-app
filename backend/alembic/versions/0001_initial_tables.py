"""initial tables

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

6テーブルを一括作成:
  companies, admin_users, sites, site_qr_codes, workers, worker_site_entries
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # companies
    # ------------------------------------------------------------------
    op.create_table(
        "companies",
        sa.Column("id", sa.String(36), nullable=False, comment="UUID v4"),
        sa.Column("name", sa.String(200), nullable=False, comment="会社名"),
        sa.Column("name_kana", sa.String(200), nullable=True, comment="会社名カナ"),
        sa.Column("postal_code", sa.String(8), nullable=True, comment="郵便番号"),
        sa.Column("address", sa.Text(), nullable=True, comment="住所"),
        sa.Column("phone", sa.String(20), nullable=True, comment="電話番号"),
        sa.Column("representative", sa.String(100), nullable=True, comment="代表者名"),
        sa.Column("is_active", sa.Boolean(), nullable=False, comment="有効フラグ"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="作成日時",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="更新日時",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_companies_name", "companies", ["name"])

    # ------------------------------------------------------------------
    # admin_users
    # ------------------------------------------------------------------
    op.create_table(
        "admin_users",
        sa.Column("id", sa.String(36), nullable=False, comment="UUID v4"),
        sa.Column("company_id", sa.String(36), nullable=False, comment="所属会社 FK"),
        sa.Column("email", sa.String(254), nullable=False, comment="メールアドレス"),
        sa.Column("password_hash", sa.String(255), nullable=False, comment="bcrypt ハッシュ"),
        sa.Column("name", sa.String(100), nullable=False, comment="表示名"),
        sa.Column("role", sa.String(20), nullable=False, comment="権限ロール"),
        sa.Column("is_active", sa.Boolean(), nullable=False, comment="有効フラグ"),
        sa.Column("login_failure_count", sa.Integer(), nullable=False, comment="ログイン失敗回数"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True, comment="ロック解除日時"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True, comment="最終ログイン日時"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_admin_users_email"),
        sa.CheckConstraint(
            "role IN ('super_admin', 'admin', 'supervisor')",
            name="ck_admin_users_role",
        ),
    )
    op.create_index("idx_admin_users_company", "admin_users", ["company_id"])

    # ------------------------------------------------------------------
    # sites
    # ------------------------------------------------------------------
    op.create_table(
        "sites",
        sa.Column("id", sa.String(36), nullable=False, comment="UUID v4"),
        sa.Column("company_id", sa.String(36), nullable=False, comment="所属会社 FK"),
        sa.Column("name", sa.String(200), nullable=False, comment="現場名"),
        sa.Column("address", sa.Text(), nullable=True, comment="現場住所"),
        sa.Column("start_date", sa.Date(), nullable=True, comment="工期開始日"),
        sa.Column("end_date", sa.Date(), nullable=True, comment="工期終了日"),
        sa.Column("supervisor_id", sa.String(36), nullable=True, comment="担当監督 FK"),
        sa.Column("require_health_check", sa.Boolean(), nullable=False, comment="健康診断必須"),
        sa.Column("require_insurance", sa.Boolean(), nullable=False, comment="保険情報必須"),
        sa.Column("custom_notice", sa.Text(), nullable=True, comment="QR ランディング注意事項"),
        sa.Column("is_active", sa.Boolean(), nullable=False, comment="有効フラグ"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="ck_sites_date_range",
        ),
    )
    op.create_index("idx_sites_company", "sites", ["company_id"])
    op.create_index("idx_sites_supervisor", "sites", ["supervisor_id"])
    op.create_index("idx_sites_active", "sites", ["is_active", "end_date"])

    # ------------------------------------------------------------------
    # site_qr_codes
    # ------------------------------------------------------------------
    op.create_table(
        "site_qr_codes",
        sa.Column("id", sa.String(36), nullable=False, comment="UUID v4"),
        sa.Column("site_id", sa.String(36), nullable=False, comment="現場 FK"),
        sa.Column("token", sa.String(64), nullable=False, comment="QR トークン"),
        sa.Column("pin_hash", sa.String(255), nullable=True, comment="PIN bcrypt ハッシュ"),
        sa.Column("pin_required", sa.Boolean(), nullable=False, comment="PIN 必須フラグ"),
        sa.Column("label", sa.String(100), nullable=True, comment="管理用ラベル"),
        sa.Column("qr_image_path", sa.String(500), nullable=True, comment="MinIO パス"),
        sa.Column("is_active", sa.Boolean(), nullable=False, comment="有効フラグ"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True, comment="有効期限"),
        sa.Column("created_by", sa.String(36), nullable=True, comment="発行管理者 FK"),
        sa.Column("deactivated_by", sa.String(36), nullable=True, comment="無効化管理者 FK"),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True, comment="無効化日時"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="発行日時",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_qr_codes_token"),
    )
    op.create_index("idx_qr_codes_site", "site_qr_codes", ["site_id"])
    op.create_index("idx_qr_codes_active", "site_qr_codes", ["is_active", "expires_at"])

    # ------------------------------------------------------------------
    # workers
    # ------------------------------------------------------------------
    op.create_table(
        "workers",
        sa.Column("id", sa.String(36), nullable=False, comment="UUID v4"),
        sa.Column("phone", sa.String(20), nullable=False, comment="電話番号（表示用）"),
        sa.Column("phone_normalized", sa.String(20), nullable=False, comment="電話番号（正規化済）"),
        sa.Column("last_name", sa.String(50), nullable=False, comment="姓"),
        sa.Column("first_name", sa.String(50), nullable=False, comment="名"),
        sa.Column("last_name_kana", sa.String(50), nullable=True, comment="姓カナ"),
        sa.Column("first_name_kana", sa.String(50), nullable=True, comment="名カナ"),
        sa.Column("birth_date", sa.Date(), nullable=False, comment="生年月日"),
        sa.Column("gender", sa.String(20), nullable=True, comment="性別"),
        sa.Column("blood_type", sa.String(10), nullable=True, comment="血液型"),
        sa.Column("emergency_contact", sa.String(20), nullable=True, comment="緊急連絡先"),
        sa.Column("emergency_contact_name", sa.String(50), nullable=True, comment="緊急連絡先氏名"),
        sa.Column("emergency_contact_relation", sa.String(30), nullable=True, comment="緊急連絡先続柄"),
        sa.Column("postal_code", sa.String(8), nullable=True, comment="郵便番号"),
        sa.Column("address", sa.Text(), nullable=True, comment="住所"),
        sa.Column("worker_type", sa.String(20), nullable=False, comment="区分"),
        sa.Column("affiliation_company", sa.String(200), nullable=True, comment="所属会社名"),
        sa.Column("job_title", sa.String(100), nullable=False, comment="職種・工種"),
        sa.Column("experience_years", sa.Integer(), nullable=True, comment="経験年数"),
        sa.Column("insurance_type", sa.String(100), nullable=True, comment="保険の種類"),
        sa.Column("insurance_number", sa.String(100), nullable=True, comment="保険番号"),
        sa.Column("consent_agreed_at", sa.DateTime(timezone=True), nullable=True, comment="個人情報同意日時"),
        sa.Column("is_active", sa.Boolean(), nullable=False, comment="有効フラグ"),
        sa.Column(
            "first_registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="初回登録日時",
        ),
        sa.Column(
            "last_updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="最終更新日時",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone_normalized", name="uq_workers_phone"),
        sa.CheckConstraint(
            "gender IS NULL OR gender IN ('male','female','other','prefer_not_to_say')",
            name="ck_workers_gender",
        ),
        sa.CheckConstraint(
            "blood_type IS NULL OR blood_type IN ('A','B','O','AB','unknown')",
            name="ck_workers_blood_type",
        ),
        sa.CheckConstraint(
            "worker_type IN ('company_employee','sole_proprietor')",
            name="ck_workers_type",
        ),
        sa.CheckConstraint(
            "experience_years IS NULL OR experience_years >= 0",
            name="ck_workers_experience",
        ),
    )
    op.create_index("idx_workers_name", "workers", ["last_name", "first_name"])
    op.create_index("idx_workers_company", "workers", ["affiliation_company"])

    # ------------------------------------------------------------------
    # worker_site_entries
    # ------------------------------------------------------------------
    op.create_table(
        "worker_site_entries",
        sa.Column("id", sa.String(36), nullable=False, comment="UUID v4"),
        sa.Column("worker_id", sa.String(36), nullable=False, comment="作業員 FK"),
        sa.Column("site_id", sa.String(36), nullable=False, comment="現場 FK"),
        sa.Column("qr_code_id", sa.String(36), nullable=False, comment="QR コード FK"),
        sa.Column("receipt_number", sa.String(8), nullable=False, comment="受付番号"),
        sa.Column("status", sa.String(20), nullable=False, comment="申請ステータス"),
        sa.Column("rejection_reason", sa.Text(), nullable=True, comment="差戻し理由"),
        sa.Column("planned_entry_date", sa.Date(), nullable=True, comment="入場予定日"),
        sa.Column("has_health_check", sa.Boolean(), nullable=False, comment="健康診断受診済み"),
        sa.Column("health_check_date", sa.Date(), nullable=True, comment="健康診断実施日"),
        sa.Column("approved_by", sa.String(36), nullable=True, comment="承認管理者 FK"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True, comment="承認日時"),
        sa.Column("submit_ip_hash", sa.String(64), nullable=True, comment="送信元 IP SHA256"),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="申請日時",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="最終更新日時",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("receipt_number", name="uq_entries_receipt"),
        sa.CheckConstraint(
            "status IN ('draft','pending','approved','rejected','withdrawn')",
            name="ck_entries_status",
        ),
    )
    op.create_index("idx_entries_site", "worker_site_entries", ["site_id"])
    op.create_index("idx_entries_worker", "worker_site_entries", ["worker_id"])
    op.create_index("idx_entries_status", "worker_site_entries", ["status"])
    op.create_index("idx_entries_submitted", "worker_site_entries", ["submitted_at"])
    # 同一 worker × site の有効申請重複を防ぐ部分ユニークインデックス
    op.create_index(
        "uq_entries_worker_site_active",
        "worker_site_entries",
        ["worker_id", "site_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('draft', 'pending', 'approved')"),
    )


def downgrade() -> None:
    op.drop_table("worker_site_entries")
    op.drop_table("workers")
    op.drop_table("site_qr_codes")
    op.drop_table("sites")
    op.drop_table("admin_users")
    op.drop_table("companies")
