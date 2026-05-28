"""
SiteAdminService — 現場・QR コード管理サービス

担当:
  - 現場一覧・詳細（ロールスコープ適用）
  - QR コード 作成・更新・無効化・再有効化
  - スコープ外アクセスは 404（情報漏洩防止）

セキュリティポリシー:
  - SUPER_ADMIN  → 全現場
  - ADMIN        → 自社 (company_id 一致) の現場
  - SUPERVISOR   → 担当 (supervisor_id == user.id) の現場のみ
  - スコープ外のリソースへのアクセスは 403 ではなく 404 で返す
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from math import ceil

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit
from app.core.security import hash_password
from app.models.admin_user import AdminUser
from app.repositories.qr_code import QrCodeRepository
from app.repositories.site import SiteRepository
from app.schemas.site_admin import (
    QrCodeItem,
    QrCreateRequest,
    QrCreateResponse,
    QrStatusResponse,
    QrUpdateRequest,
    SiteDetailResponse,
    SiteListItem,
    SiteListResponse,
)

logger = logging.getLogger(__name__)

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="現場が見つかりません")
_QR_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="QR コードが見つかりません")


class SiteAdminService:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.site_repo = SiteRepository(session)
        self.qr_repo = QrCodeRepository(session)

    # =========================================================================
    # 現場一覧
    # =========================================================================

    async def list_sites(
        self,
        user: AdminUser,
        *,
        page: int = 1,
        per_page: int = 20,
    ) -> SiteListResponse:
        items_raw, total = await self.site_repo.list_sites_for_user(
            user, page=page, per_page=per_page
        )
        items = [SiteListItem(**d) for d in items_raw]
        has_next = (page * per_page) < total
        return SiteListResponse(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            has_next=has_next,
        )

    # =========================================================================
    # 現場詳細
    # =========================================================================

    async def get_detail(
        self,
        site_id: str,
        user: AdminUser,
    ) -> SiteDetailResponse:
        site = await self.site_repo.get_site_with_qr_codes(site_id)
        if site is None:
            raise _NOT_FOUND

        # スコープチェック
        await self._assert_site_access(site_id, user)

        pending_count = await self.site_repo.get_pending_entry_count(site_id)

        qr_items = [self._to_qr_item(qr) for qr in site.qr_codes]
        # 有効なものを先に表示
        qr_items.sort(key=lambda q: (not q.is_active, not q.expires_at or q.expires_at))

        return SiteDetailResponse(
            id=site.id,
            name=site.name,
            address=site.address,
            start_date=site.start_date,
            end_date=site.end_date,
            is_active=site.is_active,
            require_health_check=site.require_health_check,
            require_insurance=site.require_insurance,
            custom_notice=site.custom_notice,
            supervisor_id=site.supervisor_id,
            supervisor_name=site.supervisor.name if site.supervisor else None,
            qr_codes=qr_items,
            pending_entry_count=pending_count,
        )

    # =========================================================================
    # QR 作成
    # =========================================================================

    async def create_qr(
        self,
        site_id: str,
        req: QrCreateRequest,
        user: AdminUser,
    ) -> QrCreateResponse:
        site = await self.site_repo.get_active_by_id(site_id)
        if site is None:
            raise _NOT_FOUND

        await self._assert_site_access(site_id, user)

        pin_hash: str | None = None
        if req.pin_required and req.pin:
            pin_hash = hash_password(req.pin)

        qr = await self.qr_repo.create_qr(
            site_id=site_id,
            pin_hash=pin_hash,
            pin_required=req.pin_required,
            label=req.label,
            expires_at=req.expires_at,
            max_uses=req.max_uses,
            created_by=user.id,
        )
        await self.session.commit()
        await self.session.refresh(qr)

        logger.info(
            "QR created: id=%s site_id=%s by=%s label=%r",
            qr.id, site_id, user.id, qr.label,
        )
        audit.qr_create(user_id=user.id, site_id=site_id, qr_id=qr.id, label=qr.label)

        return QrCreateResponse(
            id=qr.id,
            token=qr.token,
            label=qr.label,
            pin_required=qr.pin_required,
            max_uses=qr.max_uses,
            expires_at=qr.expires_at,
            use_count=qr.use_count,
            blocked_count=qr.blocked_count,
            created_at=qr.created_at,
        )

    # =========================================================================
    # QR 更新（label / expires_at / max_uses）
    # =========================================================================

    async def update_qr(
        self,
        qr_id: str,
        req: QrUpdateRequest,
        user: AdminUser,
    ) -> QrCodeItem:
        qr = await self.qr_repo.get_by_id_with_site(qr_id)
        if qr is None:
            raise _QR_NOT_FOUND

        await self._assert_site_access(qr.site_id, user)

        update: dict = {}
        if req.label is not ...:      # type: ignore[comparison-overlap]
            update["label"] = req.label
        if req.expires_at is not ...: # type: ignore[comparison-overlap]
            update["expires_at"] = req.expires_at
        if req.max_uses is not ...:   # type: ignore[comparison-overlap]
            update["max_uses"] = req.max_uses

        if update:
            await self.qr_repo.update_fields(qr, **update)
            await self.session.commit()
            await self.session.refresh(qr)

        return self._to_qr_item(qr)

    # =========================================================================
    # QR 無効化
    # =========================================================================

    async def deactivate_qr(
        self,
        qr_id: str,
        user: AdminUser,
    ) -> QrStatusResponse:
        qr = await self.qr_repo.get_by_id_with_site(qr_id)
        if qr is None:
            raise _QR_NOT_FOUND

        await self._assert_site_access(qr.site_id, user)

        if not qr.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="この QR コードはすでに無効化されています",
            )

        now = datetime.now(timezone.utc)
        await self.qr_repo.deactivate(qr, deactivated_by=user.id, deactivated_at=now)
        await self.session.commit()

        logger.info("QR deactivated: id=%s by=%s", qr_id, user.id)
        audit.qr_deactivate(user_id=user.id, qr_id=qr.id, site_id=qr.site_id)
        return QrStatusResponse(id=qr.id, is_active=qr.is_active, deactivated_at=qr.deactivated_at)

    # =========================================================================
    # QR 再有効化
    # =========================================================================

    async def activate_qr(
        self,
        qr_id: str,
        user: AdminUser,
    ) -> QrStatusResponse:
        qr = await self.qr_repo.get_by_id_with_site(qr_id)
        if qr is None:
            raise _QR_NOT_FOUND

        await self._assert_site_access(qr.site_id, user)

        if qr.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="この QR コードはすでに有効です",
            )

        await self.qr_repo.activate(qr)
        await self.session.commit()

        logger.info("QR activated: id=%s by=%s", qr_id, user.id)
        audit.qr_activate(user_id=user.id, qr_id=qr.id, site_id=qr.site_id)
        return QrStatusResponse(id=qr.id, is_active=qr.is_active, deactivated_at=qr.deactivated_at)

    # =========================================================================
    # Private helpers
    # =========================================================================

    async def _assert_site_access(self, site_id: str, user: AdminUser) -> None:
        """
        ユーザーが site_id にアクセスできるか検証する。
        スコープ外の場合は 404 を返す（情報漏洩防止）。
        """
        site_ids = await self.site_repo.get_site_ids_for_user(user)
        if site_ids is None:
            return  # SUPER_ADMIN — 全現場アクセス可
        if site_id not in site_ids:
            logger.warning(
                "Site access denied: user=%s role=%s site_id=%s",
                user.id, user.role, site_id,
            )
            raise _NOT_FOUND

    @staticmethod
    def _to_qr_item(qr) -> QrCodeItem:
        return QrCodeItem(
            id=qr.id,
            label=qr.label,
            is_active=qr.is_active,
            pin_required=qr.pin_required,
            max_uses=qr.max_uses,
            use_count=qr.use_count,
            blocked_count=qr.blocked_count,
            expires_at=qr.expires_at,
            last_accessed_at=qr.last_accessed_at,
            failed_attempts=qr.failed_attempts,
            deactivated_at=qr.deactivated_at,
            created_by_name=qr.creator.name if qr.creator else None,
            created_at=qr.created_at,
        )
