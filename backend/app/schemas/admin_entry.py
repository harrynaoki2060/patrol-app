"""
管理者向け入場申請スキーマ

使用箇所: GET /api/admin/entries/pending, GET /api/admin/entries/{id},
          POST /api/admin/entries/{id}/approve, POST /api/admin/entries/{id}/reject

セキュリティ方針:
  - EntryListItem は最小限のフィールドのみ（worker の個人詳細は含まない）
  - EntryDetailResponse は管理者が審査に必要な全情報を返す
  - 他現場情報は含まない（サービス層でフィルタ済みの前提）
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


# =============================================================================
# 申請一覧アイテム（pending リスト用 — 最小限のフィールド）
# =============================================================================

class WorkerSummaryInList(BaseModel):
    """申請一覧に表示する作業員の最小情報"""
    id: str
    last_name: str
    first_name: str
    last_name_kana: str | None = None
    first_name_kana: str | None = None
    worker_type: str
    affiliation_company: str | None = None
    job_title: str | None = None

    model_config = {"from_attributes": True}


class EntryListItem(BaseModel):
    """申請一覧の1行分"""
    id: str
    receipt_number: str
    status: str
    site_id: str
    site_name: str
    planned_entry_date: date | None = None
    submitted_at: datetime | None = None
    worker: WorkerSummaryInList

    model_config = {"from_attributes": True}


class PendingListResponse(BaseModel):
    """ページネーション付き pending 申請一覧"""
    items: list[EntryListItem]
    total: int
    page: int
    per_page: int
    has_next: bool


# =============================================================================
# 申請詳細（審査画面用 — 全情報）
# =============================================================================

class WorkerDetailInEntry(BaseModel):
    """審査画面で表示する作業員の詳細情報"""
    id: str
    last_name: str
    first_name: str
    last_name_kana: str | None = None
    first_name_kana: str | None = None
    phone: str | None = None            # 管理者には表示する（審査に必要）
    birth_date: date | None = None
    gender: str | None = None
    blood_type: str | None = None
    worker_type: str
    affiliation_company: str | None = None
    job_title: str | None = None
    postal_code: str | None = None
    address: str | None = None
    emergency_contact: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_relation: str | None = None
    insurance_type: str | None = None
    insurance_number: str | None = None
    consent_agreed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ApprovalLogItem(BaseModel):
    """承認・差戻し履歴の1件分"""
    id: str
    actor_id: str
    actor_name: str | None = None   # JOIN でセット（actor.name）
    action: str
    reason: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EntryDetailResponse(BaseModel):
    """申請詳細（審査画面）"""
    id: str
    receipt_number: str
    status: str
    site_id: str
    site_name: str
    qr_code_id: str

    # 入場情報
    planned_entry_date: date | None = None
    has_health_check: bool
    health_check_date: date | None = None

    # 承認情報
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None

    # タイムスタンプ
    draft_started_at: datetime | None = None
    submitted_at: datetime | None = None

    # リレーション
    worker: WorkerDetailInEntry
    approval_logs: list[ApprovalLogItem] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# =============================================================================
# 承認リクエスト
# =============================================================================

class ApproveRequest(BaseModel):
    """
    承認リクエスト。
    理由は任意（承認コメントとして残せる）。
    """
    reason: str | None = Field(
        default=None,
        max_length=500,
        description="承認コメント（任意）",
    )


# =============================================================================
# 差戻しリクエスト
# =============================================================================

class RejectRequest(BaseModel):
    """
    差戻しリクエスト。
    理由は必須（作業員へのフィードバックとして使用）。
    """
    reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="差戻し理由（必須）",
    )


# =============================================================================
# 承認・差戻し結果
# =============================================================================

class ApprovalResultResponse(BaseModel):
    """承認・差戻し操作の結果"""
    id: str
    receipt_number: str
    status: str
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None
