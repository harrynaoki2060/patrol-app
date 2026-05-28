"""
ApprovalService — 管理者側 承認・差戻しフロー

担当:
  - pending 申請一覧（ロールスコープ付きページネーション）
  - 申請詳細取得
  - 承認（pending → approved）
  - 差戻し（pending → rejected）

セキュリティ方針:
  - cross-site access禁止: site_ids で必ずスコープを絞る
  - pending 以外への approve / reject は 409
  - 承認ログは必ず作成する（ログなし承認を許さない）
  - role bypass禁止: site_ids は SiteRepository 経由で決定（ユーザー入力を信用しない）
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, Request, status

from app.core import audit
from app.core.state_machine import assert_can_transition
from app.models.admin_user import AdminUser
from app.models.approval_log import ApprovalAction
from app.models.entry import EntryStatus
from app.repositories.approval_log import ApprovalLogRepository
from app.repositories.entry import EntryRepository
from app.repositories.site import SiteRepository
from app.schemas.admin_entry import (
    ApprovalLogItem,
    ApprovalResultResponse,
    ApproveRequest,
    EntryDetailResponse,
    EntryListItem,
    PendingListResponse,
    RejectRequest,
    WorkerDetailInEntry,
    WorkerSummaryInList,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 共通エラー
_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="申請が見つかりません",
)


class ApprovalService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._entry_repo = EntryRepository(session)
        self._log_repo = ApprovalLogRepository(session)
        self._site_repo = SiteRepository(session)

    # =========================================================================
    # 申請一覧（pending）
    # =========================================================================

    async def list_pending(
        self,
        user: AdminUser,
        *,
        page: int = 1,
        per_page: int = 20,
        keyword: str | None = None,
        site_id_filter: str | None = None,
    ) -> PendingListResponse:
        """
        ロールスコープに応じた pending 申請一覧を返す。

        SUPER_ADMIN: 全現場
        ADMIN      : 自社の現場
        SUPERVISOR : 担当現場のみ
        """
        site_ids = await self._site_repo.get_site_ids_for_user(user)

        # SUPERVISOR が担当現場ゼロの場合は空リスト
        if site_ids is not None and len(site_ids) == 0:
            return PendingListResponse(
                items=[],
                total=0,
                page=page,
                per_page=per_page,
                has_next=False,
            )

        # site_id_filter がスコープ外なら 403
        if site_id_filter and site_ids is not None:
            if site_id_filter not in site_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="指定した現場へのアクセス権がありません",
                )

        entries, total = await self._entry_repo.get_pending_entries(
            site_ids=site_ids,
            page=page,
            per_page=per_page,
            keyword=keyword,
            site_id_filter=site_id_filter,
        )

        items = [_to_list_item(e) for e in entries]
        return PendingListResponse(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            has_next=(page * per_page) < total,
        )

    # =========================================================================
    # 申請詳細
    # =========================================================================

    async def get_detail(
        self,
        user: AdminUser,
        entry_id: str,
    ) -> EntryDetailResponse:
        """
        申請詳細を返す（承認ログ込み）。

        アクセス権のない現場の申請は 404 を返す（403 より情報漏洩が少ない）。
        """
        site_ids = await self._site_repo.get_site_ids_for_user(user)
        entry = await self._entry_repo.get_entry_detail(entry_id, site_ids=site_ids)
        if entry is None:
            raise _NOT_FOUND

        return _to_detail_response(entry)

    # =========================================================================
    # 承認
    # =========================================================================

    async def approve(
        self,
        user: AdminUser,
        entry_id: str,
        req: ApproveRequest,
        request: Request | None = None,
    ) -> ApprovalResultResponse:
        """
        pending → approved へ遷移させる。

        ステータスが pending 以外なら 409。
        承認後に approval_logs へ記録する。
        """
        site_ids = await self._site_repo.get_site_ids_for_user(user)
        entry = await self._entry_repo.get_entry_detail(entry_id, site_ids=site_ids)
        if entry is None:
            raise _NOT_FOUND

        # ステータス遷移チェック（pending 以外は 409）
        assert_can_transition(entry.status, EntryStatus.APPROVED.value)

        now = datetime.now(timezone.utc)
        request_id = request.headers.get("x-request-id") if request else None

        # 遷移
        await self._entry_repo.approve(
            entry,
            approved_by=user.id,
            approved_at=now,
        )

        # 承認ログ作成（必須）
        await self._log_repo.create_log(
            entry_id=entry.id,
            actor_id=user.id,
            action=ApprovalAction.APPROVED.value,
            reason=req.reason,
            request_id=request_id,
            created_at=now,
        )

        await self._session.commit()
        await self._session.refresh(entry)

        logger.info(
            "Approved: entry_id=%s by=%s [req=%s]",
            entry_id,
            user.email,
            request_id,
        )
        audit.entry_approve(user_id=user.id, entry_id=entry.id, site_id=entry.site_id)

        return ApprovalResultResponse(
            id=entry.id,
            receipt_number=entry.receipt_number,
            status=entry.status,
            approved_by=entry.approved_by,
            approved_at=entry.approved_at,
            rejection_reason=entry.rejection_reason,
        )

    # =========================================================================
    # 差戻し
    # =========================================================================

    async def reject(
        self,
        user: AdminUser,
        entry_id: str,
        req: RejectRequest,
        request: Request | None = None,
    ) -> ApprovalResultResponse:
        """
        pending → rejected へ遷移させる。

        ステータスが pending 以外なら 409。
        差戻し後に approval_logs へ記録する。
        """
        site_ids = await self._site_repo.get_site_ids_for_user(user)
        entry = await self._entry_repo.get_entry_detail(entry_id, site_ids=site_ids)
        if entry is None:
            raise _NOT_FOUND

        # ステータス遷移チェック
        assert_can_transition(entry.status, EntryStatus.REJECTED.value)

        now = datetime.now(timezone.utc)
        request_id = request.headers.get("x-request-id") if request else None

        # 遷移
        await self._entry_repo.reject(
            entry,
            rejection_reason=req.reason,
        )

        # 差戻しログ作成（必須）
        await self._log_repo.create_log(
            entry_id=entry.id,
            actor_id=user.id,
            action=ApprovalAction.REJECTED.value,
            reason=req.reason,
            request_id=request_id,
            created_at=now,
        )

        await self._session.commit()
        await self._session.refresh(entry)

        logger.info(
            "Rejected: entry_id=%s by=%s reason=%r [req=%s]",
            entry_id,
            user.email,
            req.reason[:50],
            request_id,
        )
        audit.entry_reject(
            user_id=user.id,
            entry_id=entry.id,
            site_id=entry.site_id,
            reason=req.reason[:200] if req.reason else None,
        )

        return ApprovalResultResponse(
            id=entry.id,
            receipt_number=entry.receipt_number,
            status=entry.status,
            approved_by=entry.approved_by,
            approved_at=entry.approved_at,
            rejection_reason=entry.rejection_reason,
        )


# =============================================================================
# 内部ヘルパー
# =============================================================================

def _to_list_item(entry) -> EntryListItem:
    w = entry.worker
    return EntryListItem(
        id=entry.id,
        receipt_number=entry.receipt_number,
        status=entry.status,
        site_id=entry.site_id,
        site_name=entry.site.name if entry.site else "",
        planned_entry_date=entry.planned_entry_date,
        submitted_at=entry.submitted_at,
        worker=WorkerSummaryInList(
            id=w.id,
            last_name=w.last_name,
            first_name=w.first_name,
            last_name_kana=w.last_name_kana,
            first_name_kana=w.first_name_kana,
            worker_type=w.worker_type,
            affiliation_company=w.affiliation_company,
            job_title=w.job_title,
        ),
    )


def _to_detail_response(entry) -> EntryDetailResponse:
    w = entry.worker

    logs = []
    for log in (entry.approval_logs or []):
        logs.append(
            ApprovalLogItem(
                id=log.id,
                actor_id=log.actor_id,
                actor_name=log.actor.name if log.actor else None,
                action=log.action,
                reason=log.reason,
                created_at=log.created_at,
            )
        )

    return EntryDetailResponse(
        id=entry.id,
        receipt_number=entry.receipt_number,
        status=entry.status,
        site_id=entry.site_id,
        site_name=entry.site.name if entry.site else "",
        qr_code_id=entry.qr_code_id,
        planned_entry_date=entry.planned_entry_date,
        has_health_check=entry.has_health_check,
        health_check_date=entry.health_check_date,
        approved_by=entry.approved_by,
        approved_at=entry.approved_at,
        rejection_reason=entry.rejection_reason,
        draft_started_at=entry.draft_started_at,
        submitted_at=entry.submitted_at,
        worker=WorkerDetailInEntry(
            id=w.id,
            last_name=w.last_name,
            first_name=w.first_name,
            last_name_kana=w.last_name_kana,
            first_name_kana=w.first_name_kana,
            phone=w.phone,
            birth_date=w.birth_date,
            gender=w.gender,
            blood_type=w.blood_type,
            worker_type=w.worker_type,
            affiliation_company=w.affiliation_company,
            job_title=w.job_title,
            postal_code=w.postal_code,
            address=w.address,
            emergency_contact=w.emergency_contact,
            emergency_contact_name=getattr(w, "emergency_contact_name", None),
            emergency_contact_relation=getattr(w, "emergency_contact_relation", None),
            insurance_type=w.insurance_type,
            insurance_number=w.insurance_number,
            consent_agreed_at=w.consent_agreed_at,
        ),
        approval_logs=logs,
    )
