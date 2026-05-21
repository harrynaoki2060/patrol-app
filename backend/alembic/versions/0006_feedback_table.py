"""add ux_feedback table

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # ux_feedback — 現場スタッフからの UX フィードバック
    # -------------------------------------------------------------------------
    op.create_table(
        "ux_feedback",
        sa.Column("id", sa.String(36), primary_key=True, comment="UUID v4"),
        sa.Column(
            "category",
            sa.String(50),
            nullable=False,
            comment="カテゴリ（input_hard / poor_connection / unclear / other）",
        ),
        sa.Column(
            "detail",
            sa.Text,
            nullable=True,
            comment="詳細コメント（任意・最大 500 文字）",
        ),
        sa.Column(
            "reporter_id",
            sa.String(36),
            nullable=True,
            comment="報告した管理ユーザー ID（NULL = 匿名）",
        ),
        sa.Column(
            "site_id",
            sa.String(36),
            nullable=True,
            comment="関連する現場 ID（任意）",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="フィードバック送信日時",
        ),
    )

    op.create_index(
        "idx_ux_feedback_category",
        "ux_feedback",
        ["category"],
    )
    op.create_index(
        "idx_ux_feedback_created_at",
        "ux_feedback",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_ux_feedback_created_at", table_name="ux_feedback")
    op.drop_index("idx_ux_feedback_category", table_name="ux_feedback")
    op.drop_table("ux_feedback")
