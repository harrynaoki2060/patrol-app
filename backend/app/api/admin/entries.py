"""
管理者向け 入場申請 API

GET  /api/admin/entries/pending      → pending 申請一覧（ページネーション・フィルタ対応）
GET  /api/admin/entries/{entry_id}   → 申請詳細（承認ログ付き）
POST /api/admin/entries/{entry_id}/approve → 承認
POST /api/admin/entries/{entry_id}/reject  → 差戻し

セキュリティ方針:
  - 全エンドポイントは require_supervisor 以上（Depends で強制）
  - クロスサイトアクセス禁止: サービス層がロールスコープを検証
  - pending 以外の承認は 409（state_machine で強制）
  - 承認ログは必ず作成（サービス層の責務）
"""
import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_supervisor
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.admin_entry import (
    ApprovalResultResponse,
    ApproveRequest,
    EntryDetailResponse,
    PendingListResponse,
    RejectRequest,
)
from app.services.approval import ApprovalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/entries", tags=["admin-entries"])


@router.get(
    "/pending",
    response_model=PendingListResponse,
    summary="pending 申請一覧",
    description=(
        "承認待ち（pending）申請をロールスコープでフィルタして返す。\n\n"
        "- SUPER_ADMIN: 全現場\n"
        "- ADMIN: 自社の現場\n"
        "- SUPERVISOR: 担当現場のみ\n\n"
        "`keyword` は氏名・カナ・受付番号の部分一致検索。\n"
        "`site_id` で特定現場に絞り込み可能（スコープ外は 403）。"
    ),
)
async def list_pending(
    page: int = Query(default=1, ge=1, description="ページ番号（1始まり）"),
    per_page: int = Query(default=20, ge=1, le=100, description="1ページの件数"),
    keyword: str | None = Query(default=None, max_length=100, description="氏名・受付番号の部分一致"),
    site_id: str | None = Query(default=None, description="現場 ID で絞り込み"),
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(require_supervisor),
) -> PendingListResponse:
    req_id = ""  # ログ用（リクエストオブジェクトが不要な一覧では省略）
    logger.info(
        "list_pending: user=%s role=%s page=%d keyword=%r site_id=%r",
        current_user.email, current_user.role, page, keyword, site_id,
    )
    service = ApprovalService(db)
    return await service.list_pending(
        current_user,
        page=page,
        per_page=per_page,
        keyword=keyword,
        site_id_filter=site_id,
    )


@router.get(
    "/{entry_id}",
    response_model=EntryDetailResponse,
    summary="申請詳細",
    description=(
        "申請の詳細情報を返す（承認ログ付き）。\n\n"
        "ロールスコープ外の申請は 404 を返す（403 より情報漏洩が少ない）。"
    ),
)
async def get_entry_detail(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(require_supervisor),
) -> EntryDetailResponse:
    logger.info(
        "get_entry_detail: user=%s entry_id=%s",
        current_user.email, entry_id,
    )
    service = ApprovalService(db)
    return await service.get_detail(current_user, entry_id)


@router.post(
    "/{entry_id}/approve",
    response_model=ApprovalResultResponse,
    summary="申請を承認",
    description=(
        "pending 申請を approved に遷移させる。\n\n"
        "- pending 以外のステータスは 409\n"
        "- 承認と同時に approval_logs へ記録\n"
        "- ロールスコープ外は 404"
    ),
)
async def approve_entry(
    entry_id: str,
    body: ApproveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(require_supervisor),
) -> ApprovalResultResponse:
    req_id = request.headers.get("x-request-id", "")
    logger.info(
        "approve: user=%s entry_id=%s [req=%s]",
        current_user.email, entry_id, req_id,
    )
    service = ApprovalService(db)
    return await service.approve(current_user, entry_id, body, request=request)


@router.post(
    "/{entry_id}/reject",
    response_model=ApprovalResultResponse,
    summary="申請を差戻し",
    description=(
        "pending 申請を rejected に遷移させる。\n\n"
        "- `reason` は必須（1〜500文字）\n"
        "- pending 以外のステータスは 409\n"
        "- 差戻しと同時に approval_logs へ記録\n"
        "- ロールスコープ外は 404"
    ),
)
async def reject_entry(
    entry_id: str,
    body: RejectRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(require_supervisor),
) -> ApprovalResultResponse:
    req_id = request.headers.get("x-request-id", "")
    logger.info(
        "reject: user=%s entry_id=%s [req=%s]",
        current_user.email, entry_id, req_id,
    )
    service = ApprovalService(db)
    return await service.reject(current_user, entry_id, body, request=request)
