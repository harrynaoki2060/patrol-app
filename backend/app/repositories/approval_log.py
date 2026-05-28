"""
ApprovalLog Repository

承認ログの作成・参照を提供する。
ログレコードは INSERT のみ（UPDATE / DELETE は行わない）。
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval_log import ApprovalLog
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ApprovalLogRepository(BaseRepository[ApprovalLog]):
    model = ApprovalLog

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create_log(
        self,
        *,
        entry_id: str,
        actor_id: str,
        action: str,
        reason: str | None = None,
        request_id: str | None = None,
        created_at: datetime,
    ) -> ApprovalLog:
        """
        承認ログを1件作成する（flush のみ。commit は呼び出し元が行う）。

        Args:
            entry_id:   対象申請 ID
            actor_id:   操作した管理者 ID
            action:     ApprovalAction の value ('approved' / 'rejected' / 'withdrawn')
            reason:     理由（差戻し時に必須、承認時は任意）
            request_id: X-Request-ID（トレーサビリティ用）
            created_at: 操作日時（呼び出し元で UTC now を渡す）
        """
        log = ApprovalLog(
            entry_id=entry_id,
            actor_id=actor_id,
            action=action,
            reason=reason,
            request_id=request_id,
            created_at=created_at,
        )
        self.session.add(log)
        await self.session.flush()
        logger.info(
            "ApprovalLog created: log_id=%s entry_id=%s actor_id=%s action=%s",
            log.id,
            entry_id,
            actor_id,
            action,
        )
        return log

    async def get_by_entry(self, entry_id: str) -> list[ApprovalLog]:
        """
        指定申請の承認ログを時系列で返す（actor を eager load）。
        """
        result = await self.session.execute(
            select(ApprovalLog)
            .where(ApprovalLog.entry_id == entry_id)
            .options(selectinload(ApprovalLog.actor))
            .order_by(ApprovalLog.created_at.asc())
        )
        return list(result.scalars().all())
