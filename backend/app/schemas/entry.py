"""
入場申請 Pydantic スキーマ

draft lifecycle の全スキーマを定義する。

draft フロー:
  DraftCreateRequest
      ↓ POST /api/public/entries/draft
  DraftEntryResponse (status=draft)
      ↓ PATCH /api/public/entries/{id}  (autosave, 複数回可)
  DraftEntryResponse (status=draft, last_saved_at 更新)
      ↓ POST /api/public/entries/{id}/submit
  SubmitResponse (status=pending, receipt_number)

セキュリティ設計:
  - submit_ip_hash はレスポンスに含めない（サーバー内部情報）
  - worker の birth_date / insurance_number はレスポンスに含める
    （本人が入力・確認した情報のため）
  - entry_session の site_id と entry.site_id が一致しないと 403
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.validators import (
    normalize_phone,
    validate_birth_date,
    validate_health_check_date,
    validate_kana,
    validate_planned_entry_date,
    normalize_postal_code,
    validate_emergency_contact,
)


# =============================================================================
# Draft Create
# =============================================================================

class DraftCreateRequest(BaseModel):
    """
    POST /api/public/entries/draft のリクエストボディ。

    パターン A（既存作業員の再利用）:
        worker_id を指定。phone もあわせて送ることで一致チェックを行う。

    パターン B（新規作業員）:
        worker_id = None、phone + last_name + first_name は必須。
        その他は PATCH で後から入力可能。

    バリデーション:
        - worker_id が None の場合 → phone / last_name / first_name は必須
        - worker_id がある場合 → phone は任意（不一致時はサービス層で 400）
    """

    phone: str = Field(
        ...,
        min_length=10,
        max_length=15,
        description="電話番号（ハイフンあり・なし両方可）",
    )
    worker_id: str | None = Field(
        None,
        description="既存作業員の ID（lookup で取得した値。再利用時に指定）",
    )
    last_name: str | None = Field(
        None, max_length=50, description="姓（新規作業員の場合は必須）"
    )
    first_name: str | None = Field(
        None, max_length=50, description="名（新規作業員の場合は必須）"
    )

    @field_validator("phone")
    @classmethod
    def phone_normalized(cls, v: str) -> str:
        return normalize_phone(v)

    @model_validator(mode="after")
    def require_name_for_new_worker(self) -> "DraftCreateRequest":
        """既存作業員の再利用でない場合は氏名が必須"""
        if self.worker_id is None:
            if not self.last_name:
                raise ValueError("新規作業員の場合は last_name（姓）が必須です")
            if not self.first_name:
                raise ValueError("新規作業員の場合は first_name（名）が必須です")
        return self

    model_config = {
        "json_schema_extra": {
            "examples": {
                "new_worker": {
                    "summary": "新規作業員",
                    "value": {
                        "phone": "090-1234-5678",
                        "last_name": "田中",
                        "first_name": "太郎",
                    },
                },
                "existing_worker": {
                    "summary": "既存作業員の再利用",
                    "value": {
                        "phone": "090-1234-5678",
                        "worker_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                    },
                },
            }
        }
    }


# =============================================================================
# Draft Update (PATCH)
# =============================================================================

class DraftUpdateRequest(BaseModel):
    """
    PATCH /api/public/entries/{id} のリクエストボディ（autosave 用）。

    全フィールドが optional。送られたフィールドだけが更新される。
    フィールドが None の場合:
      - 「フィールドを NULL に更新する」場合は明示的な None 値が必要だが、
        JSON では区別できないため、省略 = 更新しない、null = NULL に設定、とする。
      - Pydantic v2 では model_fields_set で送信されたフィールドを判別できる。

    作業員情報（workers テーブル）と入場固有情報（worker_site_entries テーブル）
    の両方を一括で更新できる。
    """

    # ------------------------------------------------------------------
    # 作業員情報（workers テーブル）
    # ------------------------------------------------------------------
    last_name: str | None = Field(None, max_length=50, description="姓")
    first_name: str | None = Field(None, max_length=50, description="名")
    last_name_kana: str | None = Field(None, max_length=50, description="姓カナ")
    first_name_kana: str | None = Field(None, max_length=50, description="名カナ")
    birth_date: date | None = Field(None, description="生年月日（YYYY-MM-DD）")
    gender: str | None = Field(
        None,
        description="性別（male / female / other / prefer_not_to_say）",
    )
    blood_type: str | None = Field(
        None,
        description="血液型（A / B / O / AB / unknown）",
    )
    emergency_contact: str | None = Field(
        None, max_length=20, description="緊急連絡先電話番号"
    )
    emergency_contact_name: str | None = Field(
        None, max_length=50, description="緊急連絡先氏名"
    )
    emergency_contact_relation: str | None = Field(
        None, max_length=30, description="緊急連絡先続柄"
    )
    postal_code: str | None = Field(
        None, max_length=8, description="郵便番号（ハイフンあり・なし両方可）"
    )
    address: str | None = Field(None, description="住所")
    worker_type: str | None = Field(
        None,
        description="区分（company_employee / sole_proprietor）",
    )
    affiliation_company: str | None = Field(
        None, max_length=200, description="所属会社名"
    )
    job_title: str | None = Field(None, max_length=100, description="職種・工種")
    experience_years: int | None = Field(
        None, ge=0, le=70, description="経験年数（0〜70）"
    )
    insurance_type: str | None = Field(
        None, max_length=100, description="保険の種類"
    )
    insurance_number: str | None = Field(
        None, max_length=100, description="保険番号"
    )
    consent_agreed: bool | None = Field(
        None,
        description="個人情報取り扱いへの同意（True で同意日時を設定）",
    )

    # ------------------------------------------------------------------
    # 入場固有情報（worker_site_entries テーブル）
    # ------------------------------------------------------------------
    planned_entry_date: date | None = Field(
        None, description="入場予定日（YYYY-MM-DD）"
    )
    has_health_check: bool | None = Field(
        None, description="健康診断受診済みか"
    )
    health_check_date: date | None = Field(
        None, description="健康診断実施日（YYYY-MM-DD）"
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("last_name_kana")
    @classmethod
    def validate_last_name_kana(cls, v: str | None) -> str | None:
        if v is not None:
            return validate_kana(v, "姓カナ")
        return v

    @field_validator("first_name_kana")
    @classmethod
    def validate_first_name_kana(cls, v: str | None) -> str | None:
        if v is not None:
            return validate_kana(v, "名カナ")
        return v

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date_field(cls, v: date | None) -> date | None:
        if v is not None:
            return validate_birth_date(v)
        return v

    @field_validator("emergency_contact")
    @classmethod
    def validate_emergency_contact_field(cls, v: str | None) -> str | None:
        if v is not None:
            return validate_emergency_contact(v)
        return v

    @field_validator("postal_code")
    @classmethod
    def validate_postal_code_field(cls, v: str | None) -> str | None:
        if v is not None:
            return normalize_postal_code(v)
        return v

    @field_validator("planned_entry_date")
    @classmethod
    def validate_planned_entry_date_field(cls, v: date | None) -> date | None:
        if v is not None:
            return validate_planned_entry_date(v)
        return v

    @field_validator("health_check_date")
    @classmethod
    def validate_health_check_date_field(cls, v: date | None) -> date | None:
        if v is not None:
            return validate_health_check_date(v)
        return v

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str | None) -> str | None:
        allowed = {"male", "female", "other", "prefer_not_to_say"}
        if v is not None and v not in allowed:
            raise ValueError(f"gender は {allowed} のいずれかを指定してください")
        return v

    @field_validator("worker_type")
    @classmethod
    def validate_worker_type(cls, v: str | None) -> str | None:
        allowed = {"company_employee", "sole_proprietor"}
        if v is not None and v not in allowed:
            raise ValueError(f"worker_type は {allowed} のいずれかを指定してください")
        return v

    @field_validator("blood_type")
    @classmethod
    def validate_blood_type(cls, v: str | None) -> str | None:
        allowed = {"A", "B", "O", "AB", "unknown"}
        if v is not None and v not in allowed:
            raise ValueError(f"blood_type は {allowed} のいずれかを指定してください")
        return v


# =============================================================================
# Responses
# =============================================================================

class WorkerInEntry(BaseModel):
    """DraftEntryResponse に埋め込む作業員情報（本人確認用）"""

    id: str
    last_name: str
    first_name: str
    last_name_kana: str | None = None
    first_name_kana: str | None = None
    birth_date: date | None = None
    gender: str | None = None
    blood_type: str | None = None
    emergency_contact: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_relation: str | None = None
    postal_code: str | None = None
    address: str | None = None
    worker_type: str
    affiliation_company: str | None = None
    job_title: str | None = None
    experience_years: int | None = None
    insurance_type: str | None = None
    insurance_number: str | None = None
    consent_agreed_at: datetime | None = None
    # phone は含めない（作業員本人が既知のため）


class DraftEntryResponse(BaseModel):
    """
    Draft Create / Draft Update のレスポンス。

    draft の現在状態を返す。autosave の完了確認にも使用する。
    """

    id: str = Field(..., description="entry ID")
    receipt_number: str = Field(..., description="受付番号（8 文字）")
    status: str = Field(..., description="ステータス（draft）")
    site_id: str = Field(..., description="現場 ID")
    qr_code_id: str = Field(..., description="QR コード ID")
    planned_entry_date: date | None = None
    has_health_check: bool
    health_check_date: date | None = None
    draft_started_at: datetime | None = None
    last_saved_at: datetime | None = None
    worker: WorkerInEntry = Field(..., description="作業員情報（入力中の状態）")
    # autosave 時の警告（フロント表示用）
    warnings: list[str] = Field(
        default_factory=list,
        description="年齢・健康診断期限等の警告メッセージ（エラーではない）",
    )


class SubmitResponse(BaseModel):
    """
    POST /api/public/entries/{id}/submit のレスポンス。

    申請完了の確認に必要な最小情報を返す。
    """

    id: str = Field(..., description="entry ID")
    receipt_number: str = Field(
        ..., description="受付番号（申請確認画面で表示。記録を推奨）"
    )
    status: str = Field(..., description="ステータス（pending）")
    submitted_at: datetime = Field(..., description="申請日時")
    site_name: str = Field(..., description="現場名（確認表示用）")
