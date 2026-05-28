"""Draft entry columns

Revision ID: 0003
Revises: 0002
Create Date: 2024-01-03 00:00:00.000000

変更内容:
  [worker_site_entries]
  - draft_started_at  : draft 生成日時（NULL = draft 以前の旧データ）
  - last_saved_at     : 最終自動保存日時（PATCH ごとに更新）
  - submitted_at      : NOT NULL → nullable に変更（draft 段階は NULL）

  [workers]
  - birth_date        : NOT NULL → nullable に変更（draft 段階は未入力を許容）
  - job_title         : NOT NULL → nullable に変更（draft 段階は未入力を許容）

設計理由:
  draft-first フローでは作業員は段階的に情報を入力する。
  submit 時に必須チェックを行うため、draft 段階では nullable を許容する。
  既存データへの影響はなし（既存行は submitted_at / birth_date / job_title がすべて
  設定済みのため、nullable 変更は後方互換）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # worker_site_entries: draft 用カラム追加
    # ------------------------------------------------------------------
    op.add_column(
        "worker_site_entries",
        sa.Column(
            "draft_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="draft ステータスで生成された日時",
        ),
    )
    op.add_column(
        "worker_site_entries",
        sa.Column(
            "last_saved_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最終自動保存日時（PATCH ごとに更新）",
        ),
    )

    # submitted_at を nullable に変更（draft 段階は未送信）
    # server_default も除去して明示的な設定のみに変更
    op.alter_column(
        "worker_site_entries",
        "submitted_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        server_default=None,
    )

    # ------------------------------------------------------------------
    # workers: draft-first フローで段階入力を許容するため nullable 化
    # ------------------------------------------------------------------
    op.alter_column(
        "workers",
        "birth_date",
        existing_type=sa.Date(),
        nullable=True,
    )
    op.alter_column(
        "workers",
        "job_title",
        existing_type=sa.String(100),
        nullable=True,
    )

    # draft 高速検索用インデックス（site × status）
    op.create_index(
        "idx_entries_site_status",
        "worker_site_entries",
        ["site_id", "status"],
    )
    op.create_index(
        "idx_entries_draft_saved",
        "worker_site_entries",
        ["last_saved_at"],
        postgresql_where=sa.text("status = 'draft'"),
    )


def downgrade() -> None:
    op.drop_index("idx_entries_draft_saved", table_name="worker_site_entries")
    op.drop_index("idx_entries_site_status", table_name="worker_site_entries")

    # workers: nullable → NOT NULL に戻す（既存データが全て設定済みの前提）
    op.alter_column(
        "workers",
        "job_title",
        existing_type=sa.String(100),
        nullable=False,
    )
    op.alter_column(
        "workers",
        "birth_date",
        existing_type=sa.Date(),
        nullable=False,
    )

    # submitted_at を NOT NULL に戻す（server_default 付き）
    op.alter_column(
        "worker_site_entries",
        "submitted_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    op.drop_column("worker_site_entries", "last_saved_at")
    op.drop_column("worker_site_entries", "draft_started_at")
