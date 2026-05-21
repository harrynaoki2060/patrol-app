"""
管理者向け 運用・UX 改善 API (Phase 9)

エンドポイント:
    GET  /api/admin/badges           → pending バッジカウント
    GET  /api/admin/morning-brief    → 朝礼モード（本日の申請一覧）
    GET  /api/admin/metrics/summary  → 運用メトリクス（過去30日）
    POST /api/admin/feedback         → UX フィードバック送信

認証:
    全エンドポイント require_supervisor 以上
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_supervisor
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.models.feedback import UxFeedback
from app.repositories.entry import EntryRepository
from app.schemas.ops import (
    FeedbackRequest,
    FeedbackResponse,
    MetricsSummaryResponse,
    MorningBriefResponse,
    MorningEntryItem,
    PendingBadgeResponse,
    SiteBadge,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-ops"])

# 朝礼モードの対象日数: 今日のみ（JST）
_JST = timezone(timedelta(hours=9))


async def _get_site_ids_for_user(
    user: AdminUser, db: AsyncSession
) -> list[str] | None:
    """ロールスコープに基づく現場 ID リストを取得する"""
    from app.repositories.site import SiteRepository
    site_repo = SiteRepository(db)
    return await site_repo.get_site_ids_for_user(user)


# =============================================================================
# Pending バッジ
# =============================================================================

@router.get(
    "/badges",
    response_model=PendingBadgeResponse,
    summary="pending バッジカウント",
    description=(
        "ヘッダーのバッジ表示用。承認待ち件数 + 30 分超過件数を返す。\n\n"
        "- `total_stale >= 1` の場合は警告色で表示する\n"
        "- ロールスコープに従いフィルタリング\n"
        "- ポーリング間隔: 1〜2 分推奨"
    ),
)
async def get_badges(
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(require_supervisor),
) -> PendingBadgeResponse:
    site_ids = await _get_site_ids_for_user(current_user, db)
    repo = EntryRepository(db)
    rows = await repo.get_pending_badge_counts(site_ids=site_ids)

    sites = [
        SiteBadge(
            site_id=r["site_id"],
            site_name=r["site_name"],
            pending_count=r["pending_count"],
            stale_count=int(r["stale_count"] or 0),
        )
        for r in rows
    ]
    total_pending = sum(s.pending_count for s in sites)
    total_stale = sum(s.stale_count for s in sites)

    return PendingBadgeResponse(
        total_pending=total_pending,
        total_stale=total_stale,
        sites=sites,
    )


# =============================================================================
# 朝礼モード
# =============================================================================

@router.get(
    "/morning-brief",
    response_model=MorningBriefResponse,
    summary="朝礼モード — 本日の申請一覧",
    description=(
        "本日の入場申請一覧（pending 優先）。朝礼での確認に使用する。\n\n"
        "- `today` は JST (UTC+9) で計算する\n"
        "- pending が先頭、approved が後続\n"
        "- `is_stale=true` の申請は 30 分以上未承認"
    ),
)
async def get_morning_brief(
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(require_supervisor),
) -> MorningBriefResponse:
    now_jst = datetime.now(tz=_JST)
    today_jst: date = now_jst.date()
    stale_cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=30)

    site_ids = await _get_site_ids_for_user(current_user, db)
    repo = EntryRepository(db)
    entries = await repo.get_morning_brief_entries(
        site_ids=site_ids,
        today_jst=today_jst,
    )

    from app.models.entry import EntryStatus
    items = []
    pending_count = 0
    approved_count = 0

    for e in entries:
        w = e.worker
        s = e.site
        is_pending = e.status == EntryStatus.PENDING.value
        is_approved = e.status == EntryStatus.APPROVED.value

        if is_pending:
            pending_count += 1
        if is_approved:
            approved_count += 1

        # 30 分超過チェック（pending のみ意味がある）
        is_stale = False
        if is_pending and e.submitted_at:
            is_stale = e.submitted_at < stale_cutoff

        items.append(
            MorningEntryItem(
                id=e.id,
                receipt_number=e.receipt_number,
                status=e.status,
                site_id=e.site_id,
                site_name=s.name if s else "—",
                planned_entry_date=e.planned_entry_date.isoformat() if e.planned_entry_date else None,
                submitted_at=e.submitted_at.isoformat() if e.submitted_at else None,
                worker_name=f"{w.last_name} {w.first_name}" if w else "—",
                worker_type=w.worker_type if w else "—",
                affiliation_company=w.affiliation_company if w else None,
                job_title=w.job_title if w else None,
                is_stale=is_stale,
            )
        )

    return MorningBriefResponse(
        today=today_jst.isoformat(),
        pending_count=pending_count,
        approved_count=approved_count,
        entries=items,
    )


# =============================================================================
# 運用メトリクス
# =============================================================================

@router.get(
    "/metrics/summary",
    response_model=MetricsSummaryResponse,
    summary="運用メトリクス（過去30日）",
    description=(
        "過去 30 日間の基本的な運用指標を返す。\n\n"
        "- `avg_approval_minutes`: 承認所要時間の平均（分）\n"
        "- `pending_over_30min`: 現在 30 分以上放置されている pending 件数\n"
        "- BI ダッシュボードは不要: 朝礼確認レベルの指標のみ"
    ),
)
async def get_metrics_summary(
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(require_supervisor),
) -> MetricsSummaryResponse:
    period_days = 30
    since = datetime.now(tz=timezone.utc) - timedelta(days=period_days)

    site_ids = await _get_site_ids_for_user(current_user, db)
    repo = EntryRepository(db)
    metrics = await repo.get_metrics(site_ids=site_ids, since=since)

    return MetricsSummaryResponse(
        period_days=period_days,
        total_submissions=metrics["total_submissions"],
        total_approved=metrics["total_approved"],
        total_rejected=metrics["total_rejected"],
        avg_approval_minutes=metrics["avg_approval_minutes"],
        pending_over_30min=metrics["pending_over_30min"],
    )


# =============================================================================
# UX フィードバック
# =============================================================================

@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=201,
    summary="UX フィードバック送信",
    description=(
        "現場スタッフ（管理者）から UX の問題を報告する。\n\n"
        "**カテゴリ**:\n"
        "- `input_hard`: 入力しにくい\n"
        "- `poor_connection`: 接続が悪い\n"
        "- `unclear`: わかりにくい\n"
        "- `other`: その他\n\n"
        "> 「朝の現場で止まらない」ための改善データとして活用します。"
    ),
)
async def submit_feedback(
    body: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = Depends(require_supervisor),
) -> FeedbackResponse:
    feedback = UxFeedback(
        id=str(uuid.uuid4()),
        category=body.category,
        detail=body.detail,
        reporter_id=current_user.id,
        site_id=body.site_id,
    )
    db.add(feedback)
    await db.commit()

    logger.info(
        "UX feedback submitted: category=%s reporter=%s",
        body.category,
        current_user.email,
    )

    return FeedbackResponse(id=feedback.id)
