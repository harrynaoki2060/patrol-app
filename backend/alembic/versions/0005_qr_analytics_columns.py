"""add QR analytics columns (max_uses, use_count, blocked_count)

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-20
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # site_qr_codes — アナリティクス・使用制限カラム追加
    # -------------------------------------------------------------------------
    op.add_column(
        "site_qr_codes",
        sa.Column(
            "max_uses",
            sa.Integer(),
            nullable=True,
            comment="最大使用回数（NULL = 無制限）",
        ),
    )
    op.add_column(
        "site_qr_codes",
        sa.Column(
            "use_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="QR 認証成功回数",
        ),
    )
    op.add_column(
        "site_qr_codes",
        sa.Column(
            "blocked_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="PIN ブロック発生回数（累積）",
        ),
    )

    # 管理画面での ID 直接ルックアップ用インデックス
    op.create_index(
        "idx_qr_codes_created_by",
        "site_qr_codes",
        ["created_by"],
    )


def downgrade() -> None:
    op.drop_index("idx_qr_codes_created_by", table_name="site_qr_codes")
    op.drop_column("site_qr_codes", "blocked_count")
    op.drop_column("site_qr_codes", "use_count")
    op.drop_column("site_qr_codes", "max_uses")
