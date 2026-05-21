"""
Entry Repository

worker_site_entries の CRUD と draft / approval ライフサイクル操作を提供する。

設計方針:
  - draft の取得は必ず site_id を検証してクロスサイトアクセスを防ぐ
  - autosave (PATCH) は last_saved_at だけを更新するためのメソッドを持つ
  - submit 操作（status → pending）は Repository でなくサービス層が決定する
    → Repository は flush のみ提供
  - worker の eager load が必要な場面は selectinload を使用
  - 管理者向けの pending 一覧は site_ids でスコープを絞る（クロスサイト禁止）
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.sql.functions import coalesce
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval_log import ApprovalLog
from app.models.entry import EntryStatus, WorkerSiteEntry
from app.models.site import Site
from app.models.worker import Worker
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class EntryRepository(BaseRepository[WorkerSiteEntry]):
    model = WorkerSiteEntry

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    # -------------------------------------------------------------------------
    # 検索
    # -------------------------------------------------------------------------

    async def get_draft_by_id_and_site(
        self,
        entry_id: str,
        site_id: str,
    ) -> WorkerSiteEntry | None:
        """
        ID × site_id でドラフトを取得（クロスサイト hijack 防止）。

        site_id が entry の site_id と一致しない場合は None を返す。
        status チェックは行わない（呼び出し元でチェック）。
        """
        result = await self.session.execute(
            select(WorkerSiteEntry)
            .options(selectinload(WorkerSiteEntry.worker))
            .where(
                WorkerSiteEntry.id == entry_id,
                WorkerSiteEntry.site_id == site_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_active_by_worker_and_site(
        self,
        worker_id: str,
        site_id: str,
    ) -> WorkerSiteEntry | None:
        """
        同一作業員 × 同一現場の有効な申請（draft/pending/approved）を取得。
        重複申請チェックに使用する。
        """
        active_statuses = [
            EntryStatus.DRAFT.value,
            EntryStatus.PENDING.value,
            EntryStatus.APPROVED.value,
        ]
        result = await self.session.execute(
            select(WorkerSiteEntry).where(
                WorkerSiteEntry.worker_id == worker_id,
                WorkerSiteEntry.site_id == site_id,
                WorkerSiteEntry.status.in_(active_statuses),
            )
        )
        return result.scalar_one_or_none()

    # -------------------------------------------------------------------------
    # 作成
    # -------------------------------------------------------------------------

    async def create_draft(
        self,
        *,
        worker_id: str,
        site_id: str,
        qr_code_id: str,
        receipt_number: str,
        now: datetime,
    ) -> WorkerSiteEntry:
        """
        draft ステータスの入場申請を作成する。

        submitted_at は NULL（pending 遷移時に設定する）。
        draft_started_at と last_saved_at を now に設定する。

        注意: flush のみ実行。
        """
        entry = WorkerSiteEntry(
            worker_id=worker_id,
            site_id=site_id,
            qr_code_id=qr_code_id,
            receipt_number=receipt_number,
            status=EntryStatus.DRAFT.value,
            draft_started_at=now,
            last_saved_at=now,
            submitted_at=None,
        )
        self.session.add(entry)
        await self.session.flush()
        await self.session.refresh(entry)
        logger.info(
            "Draft created: entry_id=%s worker_id=%s site_id=%s receipt=%s",
            entry.id,
            worker_id,
            site_id,
            receipt_number,
        )
        return entry

    # -------------------------------------------------------------------------
    # 更新（autosave）
    # -------------------------------------------------------------------------

    async def update_entry_fields(
        self,
        entry: WorkerSiteEntry,
        updates: dict[str, object],
        now: datetime,
    ) -> WorkerSiteEntry:
        """
        入場申請のフィールドを部分更新し、last_saved_at を更新する。

        updates: フィールド名 → 値 のマッピング
        呼び出し後に flush を実行する。
        """
        for field, value in updates.items():
            setattr(entry, field, value)
        entry.last_saved_at = now
        await self.session.flush()
        logger.debug(
            "Entry autosaved: entry_id=%s fields=%s",
            entry.id,
            list(updates.keys()),
        )
        return entry

    # -------------------------------------------------------------------------
    # ステータス遷移
    # -------------------------------------------------------------------------

    async def submit(
        self,
        entry: WorkerSiteEntry,
        submitted_at: datetime,
        submit_ip_hash: str,
    ) -> WorkerSiteEntry:
        """
        draft → pending へ遷移させる。

        submitted_at と submit_ip_hash を設定する。
        注意: 呼び出し前に必須フィールドの検証を行うこと（サービス層の責務）。
        """
        entry.status = EntryStatus.PENDING.value
        entry.submitted_at = submitted_at
        entry.submit_ip_hash = submit_ip_hash
        await self.session.flush()
        logger.info(
            "Entry submitted: entry_id=%s receipt=%s",
            entry.id,
            entry.receipt_number,
        )
        return entry

    # -------------------------------------------------------------------------
    # 管理者向けクエリ
    # -------------------------------------------------------------------------

    async def get_pending_entries(
        self,
        *,
        site_ids: list[str] | None,
        page: int = 1,
        per_page: int = 20,
        keyword: str | None = None,
        site_id_filter: str | None = None,
    ) -> tuple[list[WorkerSiteEntry], int]:
        """
        pending 申請の一覧を取得する（ページネーション付き）。

        Args:
            site_ids:        閲覧可能な現場 ID リスト。None = 全現場（SUPER_ADMIN）
            page:            ページ番号（1始まり）
            per_page:        1ページあたりの件数
            keyword:         氏名 / 受付番号 / カナ の部分一致検索
            site_id_filter:  特定現場に絞り込む（UI のフィルタ用）

        Returns:
            (items, total) のタプル
        """
        base_q = (
            select(WorkerSiteEntry)
            .join(Worker, WorkerSiteEntry.worker_id == Worker.id)
            .join(Site, WorkerSiteEntry.site_id == Site.id)
            .where(WorkerSiteEntry.status == EntryStatus.PENDING.value)
            .options(
                selectinload(WorkerSiteEntry.worker),
                selectinload(WorkerSiteEntry.site),
            )
        )

        # ロールスコープ絞り込み
        if site_ids is not None:
            base_q = base_q.where(WorkerSiteEntry.site_id.in_(site_ids))

        # 現場フィルタ（UI からの絞り込み）
        if site_id_filter:
            base_q = base_q.where(WorkerSiteEntry.site_id == site_id_filter)

        # キーワード検索（氏名・カナ・受付番号）
        if keyword:
            like = f"%{keyword}%"
            base_q = base_q.where(
                or_(
                    (Worker.last_name + Worker.first_name).ilike(like),
                    (
                        coalesce(Worker.last_name_kana, "")
                        + coalesce(Worker.first_name_kana, "")
                    ).ilike(like),
                    WorkerSiteEntry.receipt_number.ilike(like),
                )
            )

        # 総件数
        count_q = select(func.count()).select_from(base_q.subquery())
        total_result = await self.session.execute(count_q)
        total = total_result.scalar_one()

        # ページネーション
        offset = (page - 1) * per_page
        items_q = (
            base_q
            .order_by(WorkerSiteEntry.submitted_at.asc())
            .offset(offset)
            .limit(per_page)
        )
        result = await self.session.execute(items_q)
        items = list(result.scalars().all())

        return items, total

    async def get_entry_detail(
        self,
        entry_id: str,
        *,
        site_ids: list[str] | None,
    ) -> WorkerSiteEntry | None:
        """
        申請詳細を取得する（承認ログ込み）。

        site_ids が None でなければ、申請の site_id がリストに含まれる場合のみ返す。
        含まれない場合は None を返す（クロスサイト禁止）。
        """
        q = (
            select(WorkerSiteEntry)
            .where(WorkerSiteEntry.id == entry_id)
            .options(
                selectinload(WorkerSiteEntry.worker),
                selectinload(WorkerSiteEntry.site),
                selectinload(WorkerSiteEntry.approval_logs).selectinload(
                    ApprovalLog.actor
                ),
            )
        )
        if site_ids is not None:
            q = q.where(WorkerSiteEntry.site_id.in_(site_ids))

        result = await self.session.execute(q)
        return result.scalar_one_or_none()

    async def approve(
        self,
        entry: WorkerSiteEntry,
        *,
        approved_by: str,
        approved_at: datetime,
    ) -> WorkerSiteEntry:
        """
        pending → approved へ遷移させる。

        注意: ステータス遷移チェックはサービス層（state_machine）の責務。
        """
        entry.status = EntryStatus.APPROVED.value
        entry.approved_by = approved_by
        entry.approved_at = approved_at
        await self.session.flush()
        logger.info(
            "Entry approved: entry_id=%s by=%s",
            entry.id,
            approved_by,
        )
        return entry

    # -------------------------------------------------------------------------
    # 運用ダッシュボード クエリ
    # -------------------------------------------------------------------------

    async def get_pending_badge_counts(
        self,
        *,
        site_ids: list[str] | None,
        stale_threshold_minutes: int = 30,
    ) -> list[dict]:
        """
        現場ごとの pending 件数 + 30 分超過件数を返す。

        Args:
            site_ids: None = 全現場（SUPER_ADMIN）/ list = スコープ内
            stale_threshold_minutes: 「古い」とみなす分数（デフォルト 30 分）

        Returns:
            [{"site_id": ..., "site_name": ..., "pending_count": ..., "stale_count": ...}]
        """
        from datetime import timezone
        now = datetime.now(tz=timezone.utc)
        stale_cutoff = now - timedelta(minutes=stale_threshold_minutes)

        q = (
            select(
                Site.id.label("site_id"),
                Site.name.label("site_name"),
                func.count(WorkerSiteEntry.id).label("pending_count"),
                func.sum(
                    case(
                        (WorkerSiteEntry.submitted_at < stale_cutoff, 1),
                        else_=0,
                    )
                ).label("stale_count"),
            )
            .join(WorkerSiteEntry, WorkerSiteEntry.site_id == Site.id)
            .where(WorkerSiteEntry.status == EntryStatus.PENDING.value)
            .group_by(Site.id, Site.name)
            .order_by(func.count(WorkerSiteEntry.id).desc())
        )

        if site_ids is not None:
            q = q.where(Site.id.in_(site_ids))

        result = await self.session.execute(q)
        rows = result.mappings().all()
        return [dict(r) for r in rows]

    async def get_morning_brief_entries(
        self,
        *,
        site_ids: list[str] | None,
        today_jst: date,
        stale_threshold_minutes: int = 30,
    ) -> list[WorkerSiteEntry]:
        """
        朝礼モード用: 本日の申請一覧（pending 優先）。

        対象:
          - planned_entry_date = today OR submitted_at の日付 = today
          - status IN (pending, approved)
          - ロールスコープに従う

        Returns:
            pending が先頭、その後 approved（どちらも submitted_at 昇順）
        """
        from datetime import timezone
        now = datetime.now(tz=timezone.utc)
        stale_cutoff = now - timedelta(minutes=stale_threshold_minutes)

        q = (
            select(WorkerSiteEntry)
            .join(Worker, WorkerSiteEntry.worker_id == Worker.id)
            .join(Site, WorkerSiteEntry.site_id == Site.id)
            .where(
                WorkerSiteEntry.status.in_([
                    EntryStatus.PENDING.value,
                    EntryStatus.APPROVED.value,
                ]),
                or_(
                    WorkerSiteEntry.planned_entry_date == today_jst,
                    func.date(WorkerSiteEntry.submitted_at) == today_jst,
                ),
            )
            .options(
                selectinload(WorkerSiteEntry.worker),
                selectinload(WorkerSiteEntry.site),
            )
            .order_by(
                # pending が先頭
                case(
                    (WorkerSiteEntry.status == EntryStatus.PENDING.value, 0),
                    else_=1,
                ),
                WorkerSiteEntry.submitted_at.asc(),
            )
        )

        if site_ids is not None:
            q = q.where(WorkerSiteEntry.site_id.in_(site_ids))

        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def get_metrics(
        self,
        *,
        site_ids: list[str] | None,
        since: datetime,
    ) -> dict:
        """
        運用メトリクスを集計する。

        Returns:
            {
              total_submissions: int,
              total_approved: int,
              total_rejected: int,
              avg_approval_minutes: float | None,
              pending_over_30min: int,
            }
        """
        from datetime import timezone
        now = datetime.now(tz=timezone.utc)
        stale_cutoff = now - timedelta(minutes=30)

        # 期間内の申請集計
        base_q = (
            select(
                func.count(WorkerSiteEntry.id).label("total"),
                func.sum(
                    case((WorkerSiteEntry.status == EntryStatus.APPROVED.value, 1), else_=0)
                ).label("approved"),
                func.sum(
                    case((WorkerSiteEntry.status == EntryStatus.REJECTED.value, 1), else_=0)
                ).label("rejected"),
                func.avg(
                    case(
                        (
                            and_(
                                WorkerSiteEntry.status == EntryStatus.APPROVED.value,
                                WorkerSiteEntry.approved_at.is_not(None),
                                WorkerSiteEntry.submitted_at.is_not(None),
                            ),
                            func.extract(
                                "epoch",
                                WorkerSiteEntry.approved_at - WorkerSiteEntry.submitted_at,
                            ) / 60.0,
                        ),
                        else_=None,
                    )
                ).label("avg_minutes"),
            )
            .where(WorkerSiteEntry.submitted_at >= since)
        )

        if site_ids is not None:
            base_q = base_q.where(WorkerSiteEntry.site_id.in_(site_ids))

        res = await self.session.execute(base_q)
        row = res.mappings().one()

        # 現在 pending で 30 分超過の件数
        stale_q = select(func.count(WorkerSiteEntry.id)).where(
            WorkerSiteEntry.status == EntryStatus.PENDING.value,
            WorkerSiteEntry.submitted_at < stale_cutoff,
        )
        if site_ids is not None:
            stale_q = stale_q.where(WorkerSiteEntry.site_id.in_(site_ids))
        stale_res = await self.session.execute(stale_q)
        stale_count = stale_res.scalar_one()

        return {
            "total_submissions": row["total"] or 0,
            "total_approved": row["approved"] or 0,
            "total_rejected": row["rejected"] or 0,
            "avg_approval_minutes": float(row["avg_minutes"]) if row["avg_minutes"] else None,
            "pending_over_30min": stale_count,
        }

    async def reject(
        self,
        entry: WorkerSiteEntry,
        *,
        rejection_reason: str,
    ) -> WorkerSiteEntry:
        """
        pending → rejected へ遷移させる。

        注意: ステータス遷移チェックはサービス層（state_machine）の責務。
        """
        entry.status = EntryStatus.REJECTED.value
        entry.rejection_reason = rejection_reason
        await self.session.flush()
        logger.info(
            "Entry rejected: entry_id=%s reason=%r",
            entry.id,
            rejection_reason[:50] if rejection_reason else None,
        )
        return entry
