"""
管理者向け QR コード操作 API

全エンドポイントは require_supervisor 以上。
スコープチェック（担当現場かどうか）はサービス層で行い、
スコープ外は 404 で返す（情報漏洩防止）。

Routes:
  PATCH /api/admin/qr/{id}            ラベル・有効期限・最大使用回数の更新
  POST  /api/admin/qr/{id}/deactivate QR コードを即時無効化
  POST  /api/admin/qr/{id}/activate   QR コードを再有効化
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_supervisor
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.site_admin import (
    QrCodeItem,
    QrStatusResponse,
    QrUpdateRequest,
)
from app.services.site_admin import SiteAdminService

router = APIRouter(prefix="/qr", tags=["admin-qr"])


@router.patch(
    "/{qr_id}",
    response_model=QrCodeItem,
    summary="QR コード情報更新",
    description=(
        "ラベル・有効期限・最大使用回数を更新する。\n"
        "`null` を送るとフィールドをリセット（例: `expires_at: null` で無期限に変更）。"
    ),
)
async def update_qr(
    qr_id: str,
    req: QrUpdateRequest,
    user: AdminUser = Depends(require_supervisor),
    db: AsyncSession = Depends(get_db),
) -> QrCodeItem:
    svc = SiteAdminService(db)
    return await svc.update_qr(qr_id, req, user)


@router.post(
    "/{qr_id}/deactivate",
    response_model=QrStatusResponse,
    summary="QR コードを即時無効化",
    description="この QR コードを使った新規 verify を即時遮断する。操作は取り消し可能（activate で再有効化）。",
)
async def deactivate_qr(
    qr_id: str,
    user: AdminUser = Depends(require_supervisor),
    db: AsyncSession = Depends(get_db),
) -> QrStatusResponse:
    svc = SiteAdminService(db)
    return await svc.deactivate_qr(qr_id, user)


@router.post(
    "/{qr_id}/activate",
    response_model=QrStatusResponse,
    summary="QR コードを再有効化",
    description="無効化されていた QR コードを再び有効化する。",
)
async def activate_qr(
    qr_id: str,
    user: AdminUser = Depends(require_supervisor),
    db: AsyncSession = Depends(get_db),
) -> QrStatusResponse:
    svc = SiteAdminService(db)
    return await svc.activate_qr(qr_id, user)
