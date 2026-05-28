"""Approval logs table

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-20 00:00:00.000000

変更内容:
  [approval_logs] (新規テーブル)
  - id          : UUID v4 (PK)
  - entry_id    : 対象申請 FK
  - actor_id    : 操作した管理者 FK
  - action      : 操作種別 (approved / rejected / withdrawn)
  - reason      : 理由（差戻し時に設定）
  - request_id  : X-Request-ID トレーシング用
  - created_at  : 操作日時

設計理由:
  承認・差戻し操作の完全な監査証跡を残す。
  actor_id / entry_id / created_at にインデックスを張り、
  「誰が・いつ・どの申請を・どう処理したか」を高速に検索できるようにする。
  FK 制約は意図的に省略（TECH_DEBT.md §6 参照）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "approval_logs",
        sa.Column(
            "id",
            sa.String(36),
            primary_key=True,
            comment="UUID v4",
        ),
        sa.Column(
            "entry_id",
            sa.String(36),
            nullable=False,
            comment="対象申請 FK (worker_site_entries.id)",
        ),
        sa.Column(
            "actor_id",
            sa.String(36),
            nullable=False,
            comment="操作した管理者 FK (admin_users.id)",
        ),
        sa.Column(
            "action",
            sa.String(20),
            nullable=False,
            comment="操作種別: approved / rejected / withdrawn",
        ),
        sa.Column(
            "reason",
            sa.Text,
            nullable=True,
            comment="理由（差戻し時に必須）",
        ),
        sa.Column(
            "request_id",
            sa.String(64),
            nullable=True,
            comment="X-Request-ID トレーシング用",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="操作日時",
        ),
        sa.CheckConstraint(
            "action IN ('approved', 'rejected', 'withdrawn')",
            name="ck_approval_logs_action",
        ),
    )

    # インデックス
    op.create_index(
        "idx_approval_logs_entry",
        "approval_logs",
        ["entry_id"],
    )
    op.create_index(
        "idx_approval_logs_actor",
        "approval_logs",
        ["actor_id"],
    )
    op.create_index(
        "idx_approval_logs_created",
        "approval_logs",
        ["created_at"],
    )
    # 申請 × 日時の複合インデックス（申請履歴の時系列取得用）
    op.create_index(
        "idx_approval_logs_entry_created",
        "approval_logs",
        ["entry_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_approval_logs_entry_created", table_name="approval_logs")
    op.drop_index("idx_approval_logs_created", table_name="approval_logs")
    op.drop_index("idx_approval_logs_actor", table_name="approval_logs")
    op.drop_index("idx_approval_logs_entry", table_name="approval_logs")
    op.drop_table("approval_logs")
