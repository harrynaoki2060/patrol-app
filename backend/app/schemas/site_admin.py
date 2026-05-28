"""
管理者向け 現場・QR コード管理 スキーマ

エンドポイント:
  GET  /api/admin/sites               → SiteListResponse
  GET  /api/admin/sites/{id}          → SiteDetailResponse
  POST /api/admin/sites/{id}/qr       → QrCreateResponse
  PATCH /api/admin/qr/{id}            → QrCodeItem
  POST /api/admin/qr/{id}/deactivate  → QrStatusResponse
  POST /api/admin/qr/{id}/activate    → QrStatusResponse
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# 現場一覧
# =============================================================================

class SiteListItem(BaseModel):
    id: str
    name: str
    address: str | None
    start_date: date | None
    end_date: date | None
    is_active: bool
    supervisor_id: str | None
    supervisor_name: str | None
    active_qr_count: int
    pending_entry_count: int

    model_config = {"from_attributes": True}


class SiteListResponse(BaseModel):
    items: list[SiteListItem]
    total: int
    page: int
    per_page: int
    has_next: bool


# =============================================================================
# QR コード
# =============================================================================

class QrCodeItem(BaseModel):
    id: str
    label: str | None
    is_active: bool
    pin_required: bool
    max_uses: int | None
    use_count: int
    blocked_count: int
    expires_at: datetime | None
    last_accessed_at: datetime | None
    failed_attempts: int
    deactivated_at: datetime | None
    created_by_name: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# 現場詳細
# =============================================================================

class SiteDetailResponse(BaseModel):
    id: str
    name: str
    address: str | None
    start_date: date | None
    end_date: date | None
    is_active: bool
    require_health_check: bool
    require_insurance: bool
    custom_notice: str | None
    supervisor_id: str | None
    supervisor_name: str | None
    qr_codes: list[QrCodeItem]
    pending_entry_count: int

    model_config = {"from_attributes": True}


# =============================================================================
# QR 作成
# =============================================================================

class QrCreateRequest(BaseModel):
    label: str | None = Field(None, max_length=100, description="管理用ラベル（例: 北ゲート用）")
    pin_required: bool = Field(False, description="PIN 入力を要求するか")
    pin: str | None = Field(None, description="4 桁の数字（pin_required=True の場合は必須）")
    expires_at: datetime | None = Field(None, description="有効期限（NULL = 無期限）")
    max_uses: int | None = Field(None, ge=1, description="最大使用回数（NULL = 無制限）")

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.isdigit():
            raise ValueError("PIN は数字のみで入力してください")
        if len(v) < 4 or len(v) > 8:
            raise ValueError("PIN は 4〜8 桁で入力してください")
        return v

    @field_validator("pin_required")
    @classmethod
    def validate_pin_required_with_pin(cls, v: bool) -> bool:
        return v

    def model_post_init(self, __context: object) -> None:
        if self.pin_required and not self.pin:
            raise ValueError("PIN 必須の QR コードには PIN を指定してください")


class QrCreateResponse(BaseModel):
    """
    QR 作成レスポンス。

    `token` はフロントエンドが QR 画像を生成する際に使用する。
    QR URL 形式: `<frontend-origin>/entry/<token>`
    """
    id: str
    token: str
    label: str | None
    pin_required: bool
    max_uses: int | None
    expires_at: datetime | None
    use_count: int
    blocked_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# QR 更新（PATCH）
# =============================================================================

class QrUpdateRequest(BaseModel):
    """
    部分更新リクエスト。送ったフィールドのみ更新する。
    None を明示的に送ることで expires_at や max_uses を「無制限」に戻せる。
    """
    label: str | None = Field(default=..., max_length=100)
    expires_at: datetime | None = Field(default=...)
    max_uses: int | None = Field(default=..., ge=1)

    model_config = {"populate_by_name": True}


# =============================================================================
# QR 状態変更レスポンス（deactivate / activate 共通）
# =============================================================================

class QrStatusResponse(BaseModel):
    id: str
    is_active: bool
    deactivated_at: datetime | None

    model_config = {"from_attributes": True}
