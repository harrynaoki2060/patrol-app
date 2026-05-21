"""
運用・UX 改善向け Pydantic スキーマ

Phase 9: 実地運用テスト・UX改善フェーズ

エンドポイント対応:
  GET  /api/admin/badges           → PendingBadgeResponse
  GET  /api/admin/morning-brief    → MorningBriefResponse
  GET  /api/admin/metrics/summary  → MetricsSummaryResponse
  POST /api/admin/feedback         → FeedbackRequest / FeedbackResponse
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


# =============================================================================
# Pending バッジカウント
# =============================================================================

class SiteBadge(BaseModel):
    """現場ごとの pending 件数"""
    site_id: str = Field(..., description="現場 ID")
    site_name: str = Field(..., description="現場名")
    pending_count: int = Field(..., description="承認待ち件数")
    stale_count: int = Field(..., description="30分以上経過している件数（要注意）")


class PendingBadgeResponse(BaseModel):
    """
    GET /api/admin/badges レスポンス

    ヘッダーのバッジ表示に使用する。
    total_pending が 0 の場合はバッジを非表示にする。
    stale_count が 1 以上の場合は警告色を表示する。
    """
    total_pending: int = Field(..., description="スコープ内の承認待ち合計")
    total_stale: int = Field(..., description="30分以上経過している件数（スコープ内合計）")
    sites: list[SiteBadge] = Field(..., description="現場ごとの内訳")


# =============================================================================
# 朝礼モード
# =============================================================================

class MorningEntryItem(BaseModel):
    """朝礼モード: 本日の申請一覧の1件"""
    id: str
    receipt_number: str
    status: str
    site_id: str
    site_name: str
    planned_entry_date: str | None
    submitted_at: str | None
    worker_name: str = Field(..., description="姓名（表示用）")
    worker_type: str
    affiliation_company: str | None
    job_title: str | None
    is_stale: bool = Field(False, description="30分以上経過しているか")


class MorningBriefResponse(BaseModel):
    """
    GET /api/admin/morning-brief レスポンス

    本日の申請一覧。pending が先頭（朝礼で最初に確認できるよう）。
    today は日本時間（JST = UTC+9）のサーバー日付。
    """
    today: str = Field(..., description="本日の日付 YYYY-MM-DD（JST）")
    pending_count: int = Field(..., description="未承認件数")
    approved_count: int = Field(..., description="本日承認済み件数")
    entries: list[MorningEntryItem] = Field(..., description="申請一覧（pending 優先）")


# =============================================================================
# 運用メトリクス
# =============================================================================

class MetricsSummaryResponse(BaseModel):
    """
    GET /api/admin/metrics/summary レスポンス

    過去 30 日間の基本的な運用メトリクス。
    大規模な分析ツールは不要。朝礼確認レベルの指標のみ。
    """
    period_days: int = Field(30, description="集計期間（日数）")
    total_submissions: int = Field(..., description="申請確定数（draft→pending）")
    total_approved: int = Field(..., description="承認数")
    total_rejected: int = Field(..., description="差戻し数")
    avg_approval_minutes: float | None = Field(
        None,
        description="平均承認所要時間（分）。データ不足の場合 null",
    )
    pending_over_30min: int = Field(
        ...,
        description="現在 30 分以上放置されている pending 件数",
    )


# =============================================================================
# UX フィードバック
# =============================================================================

FeedbackCategory = Literal["input_hard", "poor_connection", "unclear", "other"]


class FeedbackRequest(BaseModel):
    """
    POST /api/admin/feedback リクエスト

    category: 「入力しにくい」「接続が悪い」「わかりにくい」「その他」
    detail: 任意の自由記述（最大 500 文字）
    site_id: 関連する現場（任意）
    """
    category: FeedbackCategory = Field(
        ...,
        description="フィードバックカテゴリ",
    )
    detail: str | None = Field(
        None,
        max_length=500,
        description="詳細コメント（任意・最大500文字）",
    )
    site_id: str | None = Field(
        None,
        description="関連する現場 ID（任意）",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "category": "input_hard",
                "detail": "カナ入力が難しい。特に高齢者に辛い",
                "site_id": None,
            }
        }
    }


class FeedbackResponse(BaseModel):
    """POST /api/admin/feedback レスポンス"""
    id: str = Field(..., description="フィードバック ID")
    message: str = "フィードバックを受け付けました"
