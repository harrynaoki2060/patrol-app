"""
Site Repository

現場テーブルの参照・ロールスコープ管理を提供する。

ロールスコープ:
  SUPER_ADMIN → 全現場（None を返す = フィルタなし）
  ADMIN       → 自社の現場（company_id でフィルタ）
  SUPERVISOR  → 担当現場のみ（supervisor_id でフィルタ）
"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_user import AdminRole, AdminUser
from app.models.entry import WorkerSiteEntry, EntryStatus
from app.models.qr_code import SiteQrCode
from app.models.site import Site
from app.repositories.base import BaseRepository


class SiteRepository(BaseRepository[Site]):
    model = Site

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    # -------------------------------------------------------------------------
    # 公開側（QR verify から使用）
    # -------------------------------------------------------------------------

    async def get_active_by_company(self, company_id: str) -> list[Site]:
        result = await self.session.execute(
            select(Site).where(
                Site.company_id == company_id,
                Site.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    async def get_active_by_id(self, site_id: str) -> Site | None:
        result = await self.session.execute(
            select(Site).where(
                Site.id == site_id,
                Site.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    # -------------------------------------------------------------------------
    # ロールスコープ解決
    # -------------------------------------------------------------------------

    async def get_site_ids_for_user(self, user: AdminUser) -> list[str] | None:
        """
        ユーザーのロールに応じて閲覧可能な現場 ID リストを返す。

        Returns:
            None             → SUPER_ADMIN（全現場、フィルタ不要）
            list[str]        → ADMIN / SUPERVISOR（対象現場 ID のリスト）
            []（空リスト）    → 担当現場がゼロの SUPERVISOR

        Usage:
            site_ids = await site_repo.get_site_ids_for_user(user)
            # EntryRepository に渡す:
            entries, total = await entry_repo.get_pending_entries(site_ids=site_ids, ...)
        """
        role = user.role

        if role == AdminRole.SUPER_ADMIN.value:
            return None

        if role == AdminRole.ADMIN.value:
            result = await self.session.execute(
                select(Site.id).where(Site.company_id == user.company_id)
            )
            return [row[0] for row in result.all()]

        if role == AdminRole.SUPERVISOR.value:
            result = await self.session.execute(
                select(Site.id).where(Site.supervisor_id == user.id)
            )
            return [row[0] for row in result.all()]

        return []

    # -------------------------------------------------------------------------
    # 管理側：現場一覧
    # -------------------------------------------------------------------------

    async def list_sites_for_user(
        self,
        user: AdminUser,
        *,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[dict], int]:
        """
        ロールスコープに従い現場一覧を返す。
        各行に active_qr_count・pending_entry_count を付加する。

        Returns: (items, total)
            items は dict のリスト: Site の全カラム + active_qr_count + pending_entry_count + supervisor_name
        """
        site_ids = await self.get_site_ids_for_user(user)

        # -- base query (Site + supervisor name) ---
        base_q = select(Site).options(selectinload(Site.supervisor))

        if site_ids is not None:
            if len(site_ids) == 0:
                return [], 0
            base_q = base_q.where(Site.id.in_(site_ids))

        # total
        count_q = select(func.count()).select_from(base_q.subquery())
        total_result = await self.session.execute(count_q)
        total: int = total_result.scalar_one()

        # paginate
        sites_result = await self.session.execute(
            base_q.order_by(Site.name).offset((page - 1) * per_page).limit(per_page)
        )
        sites = list(sites_result.scalars().all())

        if not sites:
            return [], total

        site_id_list = [s.id for s in sites]

        # -- active QR count per site --
        qr_count_rows = await self.session.execute(
            select(SiteQrCode.site_id, func.count(SiteQrCode.id).label("cnt"))
            .where(
                SiteQrCode.site_id.in_(site_id_list),
                SiteQrCode.is_active.is_(True),
            )
            .group_by(SiteQrCode.site_id)
        )
        qr_counts: dict[str, int] = {row.site_id: row.cnt for row in qr_count_rows}

        # -- pending entry count per site --
        pending_count_rows = await self.session.execute(
            select(WorkerSiteEntry.site_id, func.count(WorkerSiteEntry.id).label("cnt"))
            .where(
                WorkerSiteEntry.site_id.in_(site_id_list),
                WorkerSiteEntry.status == EntryStatus.PENDING.value,
            )
            .group_by(WorkerSiteEntry.site_id)
        )
        pending_counts: dict[str, int] = {row.site_id: row.cnt for row in pending_count_rows}

        items = [
            {
                "id": s.id,
                "name": s.name,
                "address": s.address,
                "start_date": s.start_date,
                "end_date": s.end_date,
                "is_active": s.is_active,
                "supervisor_id": s.supervisor_id,
                "supervisor_name": s.supervisor.name if s.supervisor else None,
                "active_qr_count": qr_counts.get(s.id, 0),
                "pending_entry_count": pending_counts.get(s.id, 0),
            }
            for s in sites
        ]
        return items, total

    # -------------------------------------------------------------------------
    # 管理側：現場詳細
    # -------------------------------------------------------------------------

    async def get_site_with_qr_codes(self, site_id: str) -> Site | None:
        """
        現場詳細を取得。supervisor と qr_codes（+ creator）を eager load する。
        """
        result = await self.session.execute(
            select(Site)
            .options(
                selectinload(Site.supervisor),
                selectinload(Site.qr_codes).selectinload(SiteQrCode.creator),
            )
            .where(Site.id == site_id)
        )
        return result.scalar_one_or_none()

    async def get_pending_entry_count(self, site_id: str) -> int:
        """現場の pending 申請数を返す"""
        result = await self.session.execute(
            select(func.count(WorkerSiteEntry.id)).where(
                WorkerSiteEntry.site_id == site_id,
                WorkerSiteEntry.status == EntryStatus.PENDING.value,
            )
        )
        return result.scalar_one()
