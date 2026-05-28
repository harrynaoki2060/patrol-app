"""
管理者向け 現場管理 API

全エンドポイントは require_supervisor 以上（SUPERVISOR / ADMIN / SUPER_ADMIN）。
実際のデータスコープはサービス層でロールに基づいて絞り込む。

Routes:
  GET  /api/admin/sites          現場一覧（ロールスコープ済み）
  GET  /api/admin/sites/{id}     現場詳細 + QR 一覧
  POST /api/admin/sites/{id}/qr  QR コード新規発行
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_supervisor
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.site_admin import (
    QrCreateRequest,
    QrCreateResponse,
    SiteDetailResponse,
    SiteListResponse,
)
from app.services.site_admin import SiteAdminService

router = APIRouter(prefix="/sites", tags=["admin-sites"])


@router.get(
    "",
    response_model=SiteListResponse,
    summary="現場一覧（ロールスコープ）",
    description=(
        "ログイン中のユーザーのロールに応じて閲覧可能な現場を返す。\n\n"
        "- SUPER_ADMIN: 全現場\n"
        "- ADMIN: 自社 (company_id) の現場\n"
        "- SUPERVISOR: 担当 (supervisor_id == 自分) の現場のみ"
    ),
)
async def list_sites(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user: AdminUser = Depends(require_supervisor),
    db: AsyncSession = Depends(get_db),
) -> SiteListResponse:
    svc = SiteAdminService(db)
    return await svc.list_sites(user, page=page, per_page=per_page)


@router.get(
    "/{site_id}",
    response_model=SiteDetailResponse,
    summary="現場詳細 + QR コード一覧",
)
async def get_site_detail(
    site_id: str,
    user: AdminUser = Depends(require_supervisor),
    db: AsyncSession = Depends(get_db),
) -> SiteDetailResponse:
    svc = SiteAdminService(db)
    return await svc.get_detail(site_id, user)


@router.post(
    "/{site_id}/qr",
    response_model=QrCreateResponse,
    status_code=201,
    summary="QR コード新規発行",
    description=(
        "指定した現場の QR コードを新規発行する。\n\n"
        "**注意**: `pin_required=true` の場合は `pin` フィールドも必須。\n"
        "`token` フィールドを使って、フロントエンド側で QR 画像を生成してください。\n"
        "QR URL 形式: `<frontend-origin>/entry/<token>`"
    ),
)
async def create_qr(
    site_id: str,
    req: QrCreateRequest,
    user: AdminUser = Depends(require_supervisor),
    db: AsyncSession = Depends(get_db),
) -> QrCreateResponse:
    svc = SiteAdminService(db)
    return await svc.create_qr(site_id, req, user)
