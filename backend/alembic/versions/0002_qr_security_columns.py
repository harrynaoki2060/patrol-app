"""QR security columns

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-02 00:00:00.000000

site_qr_codes にブルートフォース保護用カラムを追加:
  - failed_attempts  : PIN 失敗連続回数（デフォルト 0）
  - blocked_until    : ブロック解除日時（NULL = ブロックなし）
  - max_attempts     : 最大失敗回数（デフォルト 3）
  - last_accessed_at : 最終アクセス日時

また監査用インデックス idx_qr_codes_blocked を追加する。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ブルートフォース保護カラムを追加
    op.add_column(
        "site_qr_codes",
        sa.Column(
            "failed_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="PIN 失敗連続回数",
        ),
    )
    op.add_column(
        "site_qr_codes",
        sa.Column(
            "blocked_until",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="ブロック解除日時（NULL = ブロックなし）",
        ),
    )
    op.add_column(
        "site_qr_codes",
        sa.Column(
            "max_attempts",
            sa.Integer(),
            nullable=False,
            server_default="3",
            comment="ブロックまでの最大 PIN 失敗回数",
        ),
    )
    op.add_column(
        "site_qr_codes",
        sa.Column(
            "last_accessed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最終アクセス日時（監査ログ用）",
        ),
    )
    # 監査・ブロック確認用インデックス
    op.create_index("idx_qr_codes_blocked", "site_qr_codes", ["blocked_until"])


def downgrade() -> None:
    op.drop_index("idx_qr_codes_blocked", table_name="site_qr_codes")
    op.drop_column("site_qr_codes", "last_accessed_at")
    op.drop_column("site_qr_codes", "max_attempts")
    op.drop_column("site_qr_codes", "blocked_until")
    op.drop_column("site_qr_codes", "failed_attempts")
